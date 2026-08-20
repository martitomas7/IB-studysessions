# -*- coding: utf-8 -*-
"""resolucion_en_vivo.py · D8.4 · ORDEN_DE_TRABAJO_D8.md §0-§1 · diseño
arquitectónico grounded (panel de ángulos + síntesis, 20-08-2026)

La pieza que sustituye a `sesion.resolver_dia` en el camino EN VIVO,
inyectada vía el parámetro `resuelve_dia` que ganaron
`ciclo_vida.procesa_dia_eval`/`procesa_dia_funded`. `bot/sesion.py` NO se
toca (R6) -- esto es una reimplementación INDEPENDIENTE, verificada por
equivalencia contra el oráculo, mismo patrón que
`bot/detector_en_vivo.py` (0 discrepancias sobre 902 estados reales +
1.500 sintéticos).

Este fichero, en su primera pieza (la única construida hasta ahora), solo
contiene la aritmética de reflexión dirección-corta -- réplica ESCALAR de
`calendario.refleja_camino` pero anclada en `p0_real` (el precio de fill
real de la entrada) en vez de `pc_crudo[0]` (el cierre crudo de la barra
0, que en vivo no existe como tal sin una llamada extra al adaptador).

Verificado matemáticamente (la síntesis del diseño, y el test de
equivalencia de abajo): la reflexión es afín (`x -> 2*A - x`), y TODA la
aritmética de R-3/`DetectorEnVivo` solo usa diferencias respecto al
ancla -- nunca el valor absoluto -- así que cualquier ancla sirve; usar
`p0_real` (que YA se tiene, sin llamada adicional al adaptador) es
estrictamente más simple."""


def _refleja_escalar(x, p0_real, direccion):
    """Réplica ESCALAR, a propósito, de `calendario.refleja_camino`
    (mismo `x -> 2*A - x` si la dirección es corta, identidad si es
    larga) pero con `A = p0_real` en vez de `pc_crudo[0]` -- verificado
    matemáticamente equivalente para toda diferencia respecto a `p0`
    (que es todo lo que R-3/`DetectorEnVivo` usan; ver
    `verificacion_R3/prueba_reflexion_en_vivo.py`)."""
    return x if direccion >= 0 else 2.0 * p0_real - x


def _refleja_bar(ph_b, pl_b, pc_b, p0_real, direccion):
    """Réplica de `calendario.refleja_camino` aplicada a UNA barra --
    incluido el intercambio alto↔bajo que la reflexión exige (el máximo
    reflejado sale del MÍNIMO crudo, y viceversa): imprescindible para
    alimentar `DetectorEnVivo`, que espera el camino YA reflejado, tal
    como lo ve `sesion.resolver_dia` en el camino de replay."""
    if direccion >= 0:
        return ph_b, pl_b, pc_b
    return (2.0 * p0_real - pl_b,   # el máximo reflejado sale del MÍNIMO crudo
            2.0 * p0_real - ph_b,   # y viceversa
            2.0 * p0_real - pc_b)


class _CentinelaCaminoNoUsado:
    """Se pasa como `ph`/`pl`/`pc` a `procesa_dia_eval`/`procesa_dia_funded`
    cuando `resuelve_dia` es un `ResuelveDiaEnVivo` -- `ciclo_vida.py`
    NUNCA debería indexar `ph`/`pl`/`pc` en modo vivo (es el único módulo
    del repo donde esos tres nombres aparecen exclusivamente como
    argumentos de reenvío hacia `resuelve_dia`, nunca indexados
    directamente). Si algún cambio futuro a `ciclo_vida.py` empezara a
    indexarlos, esto falla RUIDOSO (`AssertionError` nombrando la
    invariante rota) en vez de silenciosamente (un `TypeError` genérico
    sobre `None`, o peor, un `IndexError` sin contexto)."""

    def __len__(self):
        raise AssertionError(
            "ciclo_vida.py indexó ph/pl/pc en modo vivo -- invariante rota, ese módulo "
            "solo debe REENVIAR estos argumentos a resuelve_dia, nunca leerlos (D8.4)")

    def __getitem__(self, i):
        raise AssertionError(
            "ciclo_vida.py indexó ph/pl/pc en modo vivo -- invariante rota, ese módulo "
            "solo debe REENVIAR estos argumentos a resuelve_dia, nunca leerlos (D8.4)")

    def __repr__(self):
        return "CAMINO_NO_USADO_EN_VIVO"


CAMINO_NO_USADO_EN_VIVO = _CentinelaCaminoNoUsado()
