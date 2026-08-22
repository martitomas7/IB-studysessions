# -*- coding: utf-8 -*-
"""D8.4, paso 8a: bot/bucle_del_dia.py en modo REPLAY (fuente_barras con
direccion forzada) -- comparación mini contra orquestador.corre_replay()
sobre los mismos N días, antes de intentar los 504 completos (Puerta
Grande, ORDEN_DE_TRABAJO_D8.md §4). Reconciliación de arranque incluida
de verdad (no se salta) -- con estado.json en frío (sin nada abierto),
tiene que ver PLANO y dejar operar."""
import json
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import bucle_del_dia as BDD
from bot import config, estado as E, orquestador as O, seguridad as SEG
from bot.adaptador_falso import AdaptadorFalso
from bot.fuente_barras import FuenteDeReplay

_, checksum = config.cargar()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


DIR = "/tmp/prueba_bucle_del_dia_replay"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)

N_DIAS = 10
RUTA_PACK = os.path.join(ING, "tests", "replay_v10.json")
pack = json.load(open(RUTA_PACK))
pack_recortado = os.path.join(DIR, "pack.json")
json.dump(dict(pack, dias=pack["dias"][:N_DIAS]), open(pack_recortado, 'w'))

print(f"=== referencia: orquestador.corre_replay() sobre los mismos {N_DIAS} días ===")
fines_ref, diarios_ref, st_ref = O.corre_replay(pack_recortado)
print(f"  caja final de referencia: {st_ref['caja']}")

print(f"\n=== bot/bucle_del_dia.py, alimentado por FuenteDeReplay, mismos {N_DIAS} días ===")
ruta_estado = os.path.join(DIR, "estado.json")
E_inicial = E.nuevo("v10", checksum)
E.guardar(E_inicial, ruta_estado)

pack_dias_reflejar = json.load(open(pack_recortado))["dias"]
fuente = FuenteDeReplay(pack_dias_reflejar)
adaptador = AdaptadorFalso()   # nunca se toca en modo replay salvo por la reconciliación inicial

st_final = BDD.bucle_del_dia(
    fuente, adaptador,
    cuenta_hedge_eval="CH-EVAL", cuenta_prop_eval="CP-EVAL",
    cuenta_hedge_funded="CH-FUN", cuenta_prop_funded="CP-FUN",
    instrumento_prop="MES",
    ruta_estado=ruta_estado, ruta_nivel=os.path.join(DIR, "nivel.json"),
    ruta_ordenes=os.path.join(DIR, "ordenes"), ruta_lock=os.path.join(DIR, "bot.lock"),
    dir_instantaneas=os.path.join(DIR, "instantaneas"), dias_retenidos=5,
    ruta_diario=os.path.join(DIR, "diario.jsonl"), fase='plena')

ok("bucle_del_dia() no devolvió None (estado.json cargó y validó bien)", st_final is not None)
ok(f"{N_DIAS} días procesados (dia_negociacion coincide)",
   st_final['dia_negociacion'] == st_ref['dia_negociacion'], st_final['dia_negociacion'])
ok("caja final IDÉNTICA a orquestador.corre_replay() sobre el mismo pack",
   abs(st_final['caja'] - st_ref['caja']) < 1e-9, (st_final['caja'], st_ref['caja']))
ok("degradado coincide", st_final['degradado'] == st_ref['degradado'])
ok("el nivel de seguridad se queda en N0 -- un replay limpio no degrada nada",
   SEG.nivel_actual(os.path.join(DIR, "nivel.json")) == 'N0')

print("\n=== el diario escrito línea a línea coincide con el diario del corre_replay() ===")
diario_leido = [json.loads(l) for l in open(os.path.join(DIR, "diario.jsonl"))]
ok(f"{N_DIAS} líneas de diario escritas", len(diario_leido) == N_DIAS, len(diario_leido))
ok("el diario completo coincide día a día (fin_de_dia incluido)",
   diario_leido == diarios_ref, "coincide" if diario_leido == diarios_ref else "DIFIERE")

print("\n=== las instantáneas diarias se escribieron de verdad ===")
instantaneas = sorted(os.listdir(os.path.join(DIR, "instantaneas")))
ok(f"quedan como mucho 5 instantáneas (dias_retenidos=5) de {N_DIAS} días procesados",
   len(instantaneas) == 5, instantaneas)

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
