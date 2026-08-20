# -*- coding: utf-8 -*-
"""R3 (04_GUARDARRAILES): `bot/detector_en_vivo.py::DetectorEnVivo` es la
traducción incremental (barra a barra) de `bot/sesion.py::resolver_dia`
(que resuelve el día entero de golpe) -- imprescindible para D8 (en papel,
las barras llegan una a una en tiempo real, no como un array completo).

Esta comprobación INTERCEPTA cada llamada real a `sesion.resolver_dia`
durante el replay de 504 días (parcheando el atributo del módulo, sin
tocar `tests/`/`modelo/`, R6) y, para cada una, calcula también el
resultado del detector incremental con los MISMOS argumentos -- comparando
los dos resultado a resultado, campo a campo, con tolerancia numérica.

R3: no se acepta el detector como correcto por parecerlo -- se exige
0 discrepancias sobre TODAS las llamadas reales de los 504 días (eval,
empalme, funded), no una muestra."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import sesion as sesion_mod
from bot import orquestador as orq_mod
from bot.detector_en_vivo import resuelve_dia_incremental

llamadas = []
_original = sesion_mod.resolver_dia


def _envuelto(ph, pl, pc, barra_inicio, plan_resultado, m, fric, deslizamiento=0.0, redondea=False):
    resultado_real = _original(ph, pl, pc, barra_inicio, plan_resultado, m, fric,
                                deslizamiento, redondea)
    if not redondea:
        # redondea=True solo lo usa adaptador_goldens.py (D1) -- la orquestación real
        # (ciclo_vida.py, este replay) siempre llama con el valor por defecto (False).
        resultado_incremental = resuelve_dia_incremental(
            ph, pl, pc, barra_inicio, plan_resultado, m, fric, deslizamiento)
        llamadas.append((dict(resultado_real), resultado_incremental,
                          dict(barra_inicio=barra_inicio, m=m, fric=fric)))
    return resultado_real


# Parcheo del ATRIBUTO del módulo, no una copia -- ciclo_vida.py hace
# "from bot import ... sesion ..." y llama "sesion.resolver_dia(...)": como
# los módulos de Python son objetos compartidos por referencia, reasignar
# sesion_mod.resolver_dia aquí lo cambia también para ciclo_vida.py, sin
# tocar ni un carácter de ese fichero.
sesion_mod.resolver_dia = _envuelto
try:
    fines, diarios, st_final = orq_mod.corre_replay(os.path.join(ING, 'tests', 'replay_v10.json'))
finally:
    sesion_mod.resolver_dia = _original  # restaurado SIEMPRE, incluso si algo revienta arriba

CAMPOS = ('dx_puntos', 'hedge_dolares', 'comision', 'muere', 'pausa', 'objetivo', 'barra_evento')
discrepancias = []
for resultado_real, resultado_incremental, contexto in llamadas:
    for campo in CAMPOS:
        a, b = resultado_real[campo], resultado_incremental[campo]
        if isinstance(a, float):
            if abs(a - b) > 1e-9:
                discrepancias.append((campo, a, b, contexto))
        elif a != b:
            discrepancias.append((campo, a, b, contexto))

print(f"dias del replay: {len(fines)} · estados comparados: {len(llamadas)}")
print(f"discrepancias detector-en-vivo vs resolver_dia (oraculo): {len(discrepancias)}")
if discrepancias:
    print("primeras discrepancias:")
    for campo, a, b, ctx in discrepancias[:20]:
        print(f"  {campo}: real={a!r} incremental={b!r}  contexto={ctx}")
    print("RESULTADO: DIVERGEN -- el detector NO es fiel a resolver_dia")
    sys.exit(1)
print(f"caja final del replay (control, debe seguir siendo 29134.87): {st_final['caja']:.2f}")
print("RESULTADO: IDENTICOS")
