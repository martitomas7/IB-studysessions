# -*- coding: utf-8 -*-
"""apoyo_puerta_grande.py · SOLO verificacion_R3/, NUNCA bot/ (R1/R6)

Arnés de LA PUERTA GRANDE (ORDEN_DE_TRABAJO_D8.md §4): recorre los 504
días del pack "por el bucle en vivo" (D8.2/D8.3/D8.5 de verdad, bar a
bar, vía `bot/bucle_de_tiempo.py`) en vez del array-de-un-tirón que usa
`sesion.resolver_dia` -- pero fabricando los fills exactamente en la
barra/pierna/precio que el camino YA CONOCIDO del pack dicta (porque en
la Puerta Grande SÍ conocemos el día entero de antemano -- eso es lo que
hace posible comparar contra el oráculo offline).

Reutiliza `escanea_resolucion` de `apoyo_oraculo_en_vivo.py` (el mismo
barrido que ya usan `prueba_resuelve_dia_en_vivo.py`/
`prueba_maquina_en_vivo.py`) -- nada nuevo salvo el pegamento que arma la
resolución de CADA cuenta, para los 504 días, sin intervención manual día
a día."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
if ING not in sys.path:
    sys.path.insert(0, ING)

from apoyo_oraculo_en_vivo import escanea_resolucion

from bot import calendario, ciclo_vida as CV, config, orquestador as O
from bot.adaptador_falso import AdaptadorFalso
from bot.fuente_barras import FuenteDeReplay


class AdaptadorReplaySobrePack(AdaptadorFalso):
    """`AdaptadorFalso` con el oráculo de resolución incorporado -- al
    recibir `coloca_bracket()`, escanea el camino YA CONOCIDO de esa
    cuenta (registrado por `FuenteDeReplayEnVivo.abre_dia()`) y arma su
    propia resolución (`fabrica_resolucion_bracket`), disparada por
    `notifica_barra()` en la barra exacta -- así el bracket "se resuelve
    solo" contra el camino conocido, sin intervención manual.

    `modo='perfecto'` (Pasada A/B, ambas -- LA PUERTA GRANDE de HOY, sin
    deslizamiento de ejecución): llena EXACTO al nivel pedido
    (`precio_fill=None`, ver `AdaptadorFalso.fabrica_resolucion_bracket`).
    `modo='ruido'` queda con el gancho listo (Pasada 2 del §4 original,
    deslizamiento de EJECUCIÓN) -- el valor del ruido NO se decide aquí
    (pendiente del operador, ver RESPUESTA_D8_CONCURRENCIA.md §7)."""

    def __init__(self, instrumento_prop, *a, modo='perfecto', ruido=0.0, rng=None, **kw):
        super().__init__(*a, **kw)
        self.instrumento_prop = instrumento_prop
        self.modo = modo
        self.ruido = ruido
        self.rng = rng
        self._registro = {}       # cuenta_prop -> dict(ph_ref, pl_ref, pc_ref, pc_crudo, b0)
        self._disparadores = {}   # id_grupo_oco -> (b_disparo, pierna, precio_fill)
        self._campanas = {}       # (cuenta, instrumento) -> precio_cierre

    def registra_dia(self, cuenta_prop, ph_ref, pl_ref, pc_ref, pc_crudo, barra_inicio):
        self._registro[cuenta_prop] = dict(ph_ref=ph_ref, pl_ref=pl_ref, pc_ref=pc_ref,
                                            pc_crudo=pc_crudo, b0=barra_inicio)

    def quita_dia(self, cuenta_prop):
        self._registro.pop(cuenta_prop, None)

    def abrir(self, cuenta, instrumento, direccion, cantidad, comportamiento=None):
        reg = self._registro.get(cuenta)
        if reg is not None and instrumento == self.instrumento_prop:
            b0 = min(reg['b0'], len(reg['pc_crudo']) - 1)
            comportamiento = dict(comportamiento or {}, precio_fill=reg['pc_crudo'][b0])
        return super().abrir(cuenta, instrumento, direccion, cantidad, comportamiento)

    def coloca_bracket(self, cuenta, instrumento, direccion_cierre, cantidad, precio_stop,
                        precio_limite):
        r = super().coloca_bracket(cuenta, instrumento, direccion_cierre, cantidad, precio_stop,
                                    precio_limite)
        reg = self._registro.get(cuenta)
        if reg is None or instrumento != self.instrumento_prop:
            return r

        NB = len(reg['pc_crudo'])
        b0 = min(reg['b0'], NB - 1)
        p0_real = reg['pc_crudo'][b0]
        # direction-agnóstico -- ver bot/resolucion_en_vivo.py::MaquinaEnVivo.abre():
        # precio_stop_real/precio_limite_real = _refleja_escalar(p0∓ndn/nu, p0, dir);
        # en LARGO y en CORTO, |precio - p0| == ndn/nu siempre (la reflexión solo
        # cambia el signo de qué lado queda el stop, nunca la magnitud).
        ndn = abs(precio_stop - p0_real)
        nu = abs(precio_limite - p0_real)
        pierna, bevt = escanea_resolucion(reg['ph_ref'], reg['pl_ref'], reg['pc_ref'], reg['b0'],
                                           ndn, nu)
        if pierna == 'campana':
            self._campanas[(cuenta, instrumento)] = reg['pc_crudo'][NB - 1]
        else:
            if self.modo == 'perfecto':
                precio_fill = None
            else:
                nivel = precio_stop if pierna == 'stop' else precio_limite
                ruido = self.rng.uniform(-self.ruido, self.ruido) if self.rng else 0.0
                precio_fill = nivel + ruido
            self._disparadores[r['id_grupo_oco']] = (bevt, pierna, precio_fill)
        reg['b0'] = bevt   # el SIGUIENTE coloca_bracket de esta cuenta (empalme) parte de aquí
        return r

    def notifica_barra(self, b):
        agotados = []
        for grupo, (b_disparo, pierna, precio_fill) in self._disparadores.items():
            if b == b_disparo:
                self.fabrica_resolucion_bracket(grupo, pierna, precio_fill=precio_fill)
                agotados.append(grupo)
        for g in agotados:
            del self._disparadores[g]

    def aplanar(self, cuenta, instrumento, comportamiento=None):
        precio = self._campanas.pop((cuenta, instrumento), None)
        if precio is not None:
            comportamiento = dict(comportamiento or {}, precio_fill=precio)
        return super().aplanar(cuenta, instrumento, comportamiento)


class FuenteDeReplayEnVivo(FuenteDeReplay):
    """`FuenteDeReplay` (fuerza dirección/ventana/resets/barras crudas
    desde el pack, SIN cambios) con `ContextoDia.resolucion_en_vivo=True`
    -- el tercer modo de `bot/fuente_barras.py::ContextoDia` -- y el
    registro automático del día, en cada cuenta prop, contra el
    `AdaptadorReplaySobrePack` que corresponda (para que su oráculo de
    resolución sepa contra qué camino escanear)."""

    def __init__(self, pack_dias, adaptador, cuenta_prop_eval, cuenta_prop_funded):
        super().__init__(pack_dias)
        self._adaptador = adaptador
        self._cuentas_prop = (cuenta_prop_eval, cuenta_prop_funded)

    def abre_dia(self):
        ctx = super().abre_dia()
        ctx.resolucion_en_vivo = True
        cfg = config.obtener()
        b0v = int(cfg.sesion.cal_rth.b0_rth.valor()) if ctx.ventana_txt == "RTH" else 0
        ph_ref, pl_ref, pc_ref = calendario.refleja_camino(ctx.ph, ctx.pl, ctx.pc, ctx.direccion)
        for cuenta_prop in self._cuentas_prop:
            self._adaptador.registra_dia(cuenta_prop, ph_ref, pl_ref, pc_ref, ctx.pc,
                                          barra_inicio=b0v)
        return ctx

    def siguiente_barra(self):
        barra = super().siguiente_barra()
        if barra is not None:
            self._adaptador.notifica_barra(barra.b)
        return barra


def genera_secuencia_qok_contrato(ruta_pack):
    """Instrumenta `orquestador.corre_replay()` para CAPTURAR, día a día,
    el `qok` exacto que usó el motor congelado -- nunca reconstruido a
    mano (R2): un monkeypatch temporal de `CV.qcap_abierto`/
    `qcap_abierto_por_tesoreria` que solo OBSERVA sus argumentos y
    resultados, jamás cambia el cálculo. Necesario porque
    `orquestador.procesa_dia()` usa evaluación perezosa
    (`qcap_abierto(n) or qcap_abierto_por_tesoreria(...)`)  --
    `qcap_abierto_por_tesoreria` NUNCA se llama los días en que
    `qcap_abierto` ya dio `True` (cortocircuito de `or`), así que hay que
    observar los DOS para no perderse ningún día.

    Devuelve la lista de `qok` (uno por día, en orden) -- LA PASADA A de
    LA PUERTA GRANDE la inyecta día a día, para reproducir el contrato del
    motor congelado incluso corriendo por el bucle en vivo concurrente
    (que, por construcción, solo puede calcular `qok` CAUSAL -- ver
    `modelo/DEFECTOS_CONOCIDOS.md` D-5)."""
    secuencia = []
    ultimo_a = [None]
    orig_a = CV.qcap_abierto
    orig_b = CV.qcap_abierto_por_tesoreria

    def _a(n):
        r = orig_a(n)
        ultimo_a[0] = r
        if r:
            secuencia.append(True)   # 'or' cortocircuita -- _b no se llamará hoy
        return r

    def _b(caja, retirado):
        r = orig_b(caja, retirado)
        secuencia.append(bool(ultimo_a[0]) or r)
        return r

    CV.qcap_abierto = _a
    CV.qcap_abierto_por_tesoreria = _b
    try:
        O.corre_replay(ruta_pack)
    finally:
        CV.qcap_abierto = orig_a
        CV.qcap_abierto_por_tesoreria = orig_b
    return secuencia


def resuelve_concurrente_qok_forzado(secuencia_qok, resuelve_dia_concurrente):
    """Envuelve `bucle_de_tiempo.resuelve_dia_concurrente` para IGNORAR el
    `qok` CAUSAL que `orquestador.procesa_dia()` calcula automáticamente
    (ver `bot/orquestador.py::procesa_dia`, camino `resuelve_concurrente`)
    y sustituirlo por el valor pre-registrado del CONTRATO -- SOLO para
    LA PASADA A (fidelidad) de LA PUERTA GRANDE; la Pasada B (causal) usa
    `bucle_de_tiempo.resuelve_dia_concurrente` tal cual, sin este
    envoltorio.

    Devuelve un callable con la MISMA firma que espera
    `orquestador.procesa_dia(..., resuelve_concurrente=...)`."""
    indice = [0]

    def _envoltorio(st, direccion, b0v, qok_causal, modo_auto_confirma, **kwargs):
        qok_contrato = secuencia_qok[indice[0]]
        indice[0] += 1
        return resuelve_dia_concurrente(st, direccion, b0v, qok_contrato, modo_auto_confirma,
                                         **kwargs)

    return _envoltorio
