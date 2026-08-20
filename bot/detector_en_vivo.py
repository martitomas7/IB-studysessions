# -*- coding: utf-8 -*-
"""detector_en_vivo.py · D8 · 05_ORDEN_DE_CONSTRUCCION.md

`bot/sesion.py::resolver_dia` recibe las barras del DÍA ENTERO y resuelve de
golpe (R-3.1 a R-3.7) -- perfecto para el replay (Fase 1, 504 días) pero
irreproducible en papel/vivo: ahí las barras llegan UNA A UNA, en tiempo
real, y D8 tiene que saber en el INSTANTE en que una barra confirma el
suelo o el objetivo, no después.

`DetectorEnVivo` resuelve exactamente lo mismo que `resolver_dia`, barra a
barra, según llegan -- MISMA fórmula, MISMO desempate (R-3.3: el suelo gana
el empate), MISMA regla de muerte EOD (R-3.4). No reimplementa la
aritmética con una interpretación propia: es la traducción incremental,
verificada bit a bit contra `resolver_dia` como oráculo sobre los 504 días
del replay (`verificacion_R3/prueba_detector_en_vivo.py`, 0 discrepancias
sobre 1.512 estados) -- nunca se acepta como correcta por parecerlo, se
demuestra idéntica a la que ya está verificada.

REGLA DE DEPENDENCIAS (igual que sesion.py, 02_ARQUITECTURA.md §2): puro,
sin red, sin reloj de pared propio (el reloj lo lleva quien alimenta las
barras), sin conocer cuentas/pool/tesorería. Solo sabe resolver UN día de
UNA sesión ya abierta, barra a barra.

PROHIBIDO (mismo principio que sesion.py): esto NO decide cuándo abrir ni
cuánto -- `p0`, `ndn`, `nu`, `m`, `fric`, `Mm`, `pv` ya vienen resueltos
por `sizing.py`/`calendario.py` antes de construir el detector."""
from bot import config


class DetectorEnVivo:
    """Consume barras del camino YA REFLEJADO (mismo `ph`/`pl`/`pc` que ve
    `sesion.resolver_dia` -- si la dirección es corta, quien llama ya aplicó
    `calendario.refleja_camino` antes de alimentar barras aquí, exactamente
    igual que antes de llamar a `resolver_dia`).

    Uso:
        det = DetectorEnVivo(p0=pc[b0], ndn=plan['ndn'], nu=plan['nu'],
                              m=m, fric=fric, deslizamiento=deslizamiento,
                              valor_punto=valor_punto, k=plan['k'],
                              cst=plan['comision'], Mm=plan['Mm'],
                              bloqueado=plan['bloqueo'])
        for b in range(b0 + 1, NB):
            det.alimenta_barra(b, ph[b], pl[b], pc[b], es_ultima_barra_operable=(b == NB - 1))
            if det.resuelto:
                break
        # det.resultado tiene EXACTAMENTE la forma de resolver_dia(...):
        # {dx_puntos, hedge_dolares, comision, muere, pausa, objetivo, barra_evento}
    """

    def __init__(self, p0, ndn, nu, m, fric, deslizamiento, valor_punto, k, cst, Mm,
                 bloqueado=False):
        self.p0 = p0
        self.ndn = ndn
        self.nu = nu
        self.m = m
        self.fric = fric
        self.deslizamiento = deslizamiento
        self.valor_punto = valor_punto
        self.pv = valor_punto * k   # R-2.5, misma fórmula que sesion.py::resolver_dia
        self.cst = cst
        self.Mm = Mm
        self._iD = None
        self._iU = None
        self.resultado = None
        # R-2.4 (revisión R3: FALLO REAL cazado aquí -- ver verificacion_R3/
        # prueba_detector_en_vivo.py). El primer intento de este constructor
        # cortocircuitaba de inmediato con barra_evento=None para una cuenta
        # bloqueada -- pero resolver_dia NO hace eso: su override de `bloq`
        # (aplicado AL FINAL, después del barrido) solo pone a cero
        # dx/comisión/hedge/muere/pausa/objetivo -- deja `ib` (barra_evento)
        # tal cual salió del barrido de precio, aunque ese barrido ya no
        # tenga efecto de negocio. Cortarlo aquí producía una divergencia
        # real contra el oráculo (barra_evento=85 en resolver_dia,
        # barra_evento=None en el detector, para la MISMA sesión bloqueada).
        # Corregido: el barrido sigue corriendo normal incluso bloqueado, y
        # el cero se aplica en _cierra(), en el mismo punto que resolver_dia.
        self.bloqueado = bloqueado

    @property
    def resuelto(self):
        return self.resultado is not None

    def alimenta_barra(self, b, ph_b, pl_b, pc_b, es_ultima_barra_operable):
        """Llamar EN ORDEN CRECIENTE de `b`, empezando en `b0+1` (nunca la
        propia barra de entrada -- R-3.2, el look-ahead que costó el 13,6 %
        del titular en v8). No hace nada si ya está resuelto -- llamar de
        más tras resolverse es inofensivo, no un error."""
        if self.resuelto:
            return
        if self._iD is None and (pl_b - self.p0) <= -self.ndn:
            self._iD = b
        if self._iU is None and (ph_b - self.p0) >= self.nu:
            self._iU = b
        if self._iD is not None or self._iU is not None:
            self._resuelve_por_evento(b)
        elif es_ultima_barra_operable:
            self._resuelve_por_campana(b, pc_b)

    def _resuelve_por_evento(self, b):
        # R-3.3: el suelo gana el empate -- misma comparación que resolver_dia
        # (`low = iD<=NB and iD<=iU`), reescrita sin el centinela NB+1 porque
        # aquí "no encontrado" ya es None, no un número grande.
        low = self._iD is not None and (self._iU is None or self._iD <= self._iU)
        tgt = self._iU is not None and (self._iD is None or self._iU < self._iD)
        dx = -self.ndn if low else self.nu
        self._cierra(dx, low, tgt, b)

    def _resuelve_por_campana(self, b, pc_b):
        # Ninguna de las dos se disparó en toda la sesión -- cierre al
        # precio de cierre de la última barra operable (R-3.3, caso "ninguno").
        dx = pc_b - self.p0
        self._cierra(dx, low=False, tgt=False, barra_evento=b)

    def _cierra(self, dx, low, tgt, barra_evento):
        # R-3.4: la salida de suelo es siempre al DLL -- la cuenta solo
        # muere si la pérdida REALIZADA perfora el suelo vivo.
        muere = (dx * self.pv - self.cst <= -(self.Mm - 1e-9))
        pausa = low and not muere
        # R-3.5: P&L del hedge -- el deslizamiento SOLO en la salida de muerte.
        h = -self.valor_punto * self.m * dx - self.fric
        if muere:
            h -= self.deslizamiento
        cst = self.cst
        # R-2.4, aplicado AL FINAL -- igual orden que resolver_dia: el barrido
        # (y por tanto barra_evento) ya se calculó arriba con normalidad; el
        # bloqueo solo apaga el EFECTO de negocio, nunca el dato de qué barra
        # habría disparado el evento.
        if self.bloqueado:
            dx, cst, h, muere, pausa, tgt = 0.0, 0.0, 0.0, False, False, False
        self.resultado = dict(dx_puntos=dx, hedge_dolares=h, comision=cst,
                               muere=muere, pausa=pausa, objetivo=tgt, barra_evento=barra_evento)


def resuelve_dia_incremental(ph, pl, pc, barra_inicio, plan_resultado, m, fric, deslizamiento=0.0):
    """Envoltorio de conveniencia que alimenta TODAS las barras de golpe --
    usado SOLO por el oráculo de verificación (verificacion_R3/
    prueba_detector_en_vivo.py), para poder comparar contra
    `sesion.resolver_dia` sobre un array completo sin tener que simular un
    bucle barra a barra en el propio test. D8 (en vivo) NUNCA llama a esto
    -- llama a `DetectorEnVivo.alimenta_barra()` una vez por barra, según
    van llegando de verdad."""
    NB = len(pc)
    b0 = barra_inicio
    p0 = pc[min(b0, NB - 1)]
    valor_punto = config.obtener().hedge_broker.valor_punto_usd.valor()
    det = DetectorEnVivo(p0=p0, ndn=plan_resultado['ndn'], nu=plan_resultado['nu'],
                          m=m, fric=fric, deslizamiento=deslizamiento,
                          valor_punto=valor_punto, k=plan_resultado['k'],
                          cst=plan_resultado['comision'], Mm=plan_resultado['Mm'],
                          bloqueado=plan_resultado['bloqueo'])
    for b in range(b0 + 1, NB):
        det.alimenta_barra(b, ph[b], pl[b], pc[b], es_ultima_barra_operable=(b == NB - 1))
        if det.resuelto:
            break
    if not det.resuelto:
        # NB podría ser <= b0+1 (sesión sin barras que barrer) -- mismo caso
        # límite que resolver_dia resuelve con su propio bucle vacío: dx al
        # cierre de la última barra disponible.
        det._resuelve_por_campana(NB - 1, pc[NB - 1])
    return det.resultado
