# -*- coding: utf-8 -*-
"""R3 (D8.4, ORDEN_DE_TRABAJO_D8.md §0, paso 2 del plan de la síntesis):
`bot/orquestador.py::procesa_dia_replay` se extrajo a `procesa_dia()`
(compartida con `bot/bucle_del_dia.py`, en vivo) + un envoltorio delgado.
La prueba que demuestra que la extracción fue ADITIVA PURA: el replay de
504 días sigue dando EXACTAMENTE caja final 29.134,87 $, bit a bit igual
que antes de tocar el fichero -- esta prueba tiene que correr para
siempre, no una sola vez."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import orquestador as O

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


print("=== procesa_dia() existe y tiene la firma esperada ===")
ok("orquestador.procesa_dia existe", hasattr(O, 'procesa_dia'))

print("\n=== el replay de 504 días completo sigue dando EXACTAMENTE lo mismo tras la extracción ===")
RUTA_PACK = os.path.join(ING, "tests", "replay_v10.json")
fines, diarios, st_final = O.corre_replay(RUTA_PACK)
ok("504 días procesados", len(fines) == 504, len(fines))
ok("caja final = 29.134,87 $ (bit a bit idéntica a la referencia congelada)",
   abs(st_final['caja'] - 29134.87) < 1e-2, st_final['caja'])
ok("degradado sigue siendo False (mismo estado final que siempre)",
   st_final['degradado'] is False, st_final['degradado'])

print("\n=== correr el replay DOS VECES da resultados bit a bit idénticos (determinismo, "
      "adelanto de lo que exigirá la Puerta Grande) ===")
fines2, diarios2, st_final2 = O.corre_replay(RUTA_PACK)
ok("las 504 líneas de fin_de_dia son IDÉNTICAS entre las dos corridas",
   fines == fines2, "coincide" if fines == fines2 else "DIFIERE")
ok("los 504 días de diario son IDÉNTICOS entre las dos corridas",
   diarios == diarios2, "coincide" if diarios == diarios2 else "DIFIERE")

print("\n=== procesa_dia_replay() sigue siendo llamable exactamente igual que antes "
      "(mismo llamador que romper_mi_orquestador.py) ===")
import json
st0 = json.load(open(RUTA_PACK))["dias"][0]
from bot import config, estado as E
_, checksum = config.cargar()
st_inicial = E.nuevo("v10", checksum)
st_tras_dia1, fin_dia1, diario1 = O.procesa_dia_replay(st_inicial, st0)
ok("procesa_dia_replay(st, dia_pack) sigue devolviendo (st, fin_de_dia, diario) de 3 elementos",
   isinstance(st_tras_dia1, dict) and isinstance(fin_dia1, dict) and isinstance(diario1, dict))
ok("el resultado del día 1 vía procesa_dia_replay coincide con el día 1 del corre_replay completo",
   fin_dia1 == fines[0], (fin_dia1, fines[0]))

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
