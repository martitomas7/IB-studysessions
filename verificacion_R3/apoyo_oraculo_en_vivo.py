# -*- coding: utf-8 -*-
"""apoyo_oraculo_en_vivo.py · SOLO verificacion_R3/, NUNCA bot/ (R1/R6)

Arnés de prueba para comparar `bot.resolucion_en_vivo.ResuelveDiaEnVivo`
contra `sesion.resolver_dia` como oráculo: un `AdaptadorFalso` que resuelve
un bracket EXACTAMENTE en la barra/pierna que un camino ya conocido dicta
(porque en la prueba SÍ conocemos el día entero de antemano -- eso es
justo lo que hace posible comparar contra el oráculo). Se usa tanto en
`prueba_resuelve_dia_en_vivo.py` (un día suelto) como, más adelante, en la
Puerta Grande (504 días completos, ORDEN_DE_TRABAJO_D8.md §4)."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
if ING not in sys.path:
    sys.path.insert(0, ING)

from bot.adaptador_falso import AdaptadorFalso


def escanea_resolucion(ph, pl, pc, b0, ndn, nu):
    """Replica el barrido de R-3.2/R-3.3 de `sesion.resolver_dia` -- SOLO
    para saber qué fabricar en la prueba (qué pierna, en qué barra); NUNCA
    para decidir dx/negocio -- eso lo hace `resolver_dia`, el oráculo
    real, y por separado `ResuelveDiaEnVivo`, ambos comparados aquí, no
    sustituidos. Devuelve `('stop'|'limite'|'campana', barra)`."""
    NB = len(pc)
    p0 = pc[min(b0, NB - 1)]
    iD = iU = NB + 1
    for b in range(b0 + 1, NB):
        if iD > NB and (pl[b] - p0) <= -ndn:
            iD = b
        if iU > NB and (ph[b] - p0) >= nu:
            iU = b
        if iD <= NB and iU <= NB:
            break
    low = iD <= NB and iD <= iU
    tgt = iU <= NB and iU < iD
    if low:
        return 'stop', iD
    if tgt:
        return 'limite', iU
    return 'campana', NB - 1


class AdaptadorOraculoSobreCamino(AdaptadorFalso):
    """`AdaptadorFalso` con dos ganchos SOLO de prueba: resolver un
    bracket en la barra exacta que se le arme (`arma_resolucion` +
    `notifica_barra`, coordinado por `FuenteConNotificacion` de abajo), y
    fijar el precio de un cierre a mercado (`arma_cierre_campana`) -- sin
    lo segundo, `AdaptadorFalso.aplanar()` llenaría al precio de prueba
    fijo (100.0), que no tiene por qué coincidir con `pc[NB-1]` (el cierre
    real que `sesion.resolver_dia` asume en su rama de campana). Ninguno
    de los dos cambia `bot/adaptador_falso.py` -- viven aquí, en el
    arnés."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.ultimo_grupo_oco = None
        self._disparador = None    # (b_disparo, pierna, precio_fill) | None
        self._campana = None       # (cuenta, instrumento, precio_cierre) | None

    def coloca_bracket(self, *a, **kw):
        r = super().coloca_bracket(*a, **kw)
        self.ultimo_grupo_oco = r['id_grupo_oco']
        return r

    def arma_resolucion(self, b_disparo, pierna, precio_fill=None):
        self._disparador = (b_disparo, pierna, precio_fill)

    def arma_cierre_campana(self, cuenta, instrumento, precio_cierre):
        self._campana = (cuenta, instrumento, precio_cierre)

    def notifica_barra(self, b):
        """Llamada por `FuenteConNotificacion` tras servir la barra `b` --
        si coincide con el disparador armado, resuelve el bracket AHORA
        MISMO, así `ResuelveDiaEnVivo` lo ve en la vuelta de sondeo que
        corresponde a esa barra real."""
        if self._disparador is not None:
            b_disparo, pierna, precio_fill = self._disparador
            if b == b_disparo:
                self.fabrica_resolucion_bracket(self.ultimo_grupo_oco, pierna,
                                                 precio_fill=precio_fill)
                self._disparador = None

    def aplanar(self, cuenta, instrumento, comportamiento=None):
        if self._campana is not None and (cuenta, instrumento) == self._campana[:2]:
            comportamiento = dict(comportamiento or {}, precio_fill=self._campana[2])
        return super().aplanar(cuenta, instrumento, comportamiento)


class FuenteConNotificacion:
    """Envuelve cualquier `FuenteDeBarras` para avisar al
    `AdaptadorOraculoSobreCamino` de cada barra servida -- la coordinación
    que hace posible "resuelve el bracket EXACTAMENTE en esta barra"."""

    def __init__(self, fuente_interna, adaptador):
        self._fuente = fuente_interna
        self._adaptador = adaptador

    def dia_disponible(self):
        return self._fuente.dia_disponible()

    def abre_dia(self):
        return self._fuente.abre_dia()

    def cierra_dia(self):
        return self._fuente.cierra_dia()

    def siguiente_barra(self):
        barra = self._fuente.siguiente_barra()
        if barra is not None:
            self._adaptador.notifica_barra(barra.b)
        return barra
