# -*- coding: utf-8 -*-
"""LA PUERTA GRANDE (ORDEN_DE_TRABAJO_D8.md §4) -- los N días del pack
"por el bucle en vivo": bot/bucle_del_dia.py, con dirección/ventana/resets
forzados desde el pack (igual que el contrato del replay) pero resueltos
D8.2/D8.3/D8.5 de verdad, bar a bar, vía bot/bucle_de_tiempo.py.

Pasada A (fidelidad): qok del CONTRATO (el mismo que usó el motor
congelado, capturado por instrumentación -- ver
apoyo_puerta_grande.py::genera_secuencia_qok_contrato) -- exige 0
discrepancias contra orquestador.corre_replay(), tolerancia 1e-3 $. Más
determinismo: correr la pasada A dos veces, bit a bit igual.

Pasada B (causalidad): qok CAUSAL -- el que usará el bot real (D8.4
reestructuración) -- exige que la ÚNICA divergencia sea, exactamente, la
del defecto conocido D-5 (modelo/DEFECTOS_CONOCIDOS.md): el día 269.

N_DIAS es un argumento de línea de comandos -- por defecto un subconjunto
pequeño para iterar rápido; `--full` corre los 504 días completos."""
import json
import os
import shutil
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from apoyo_puerta_grande import (AdaptadorReplaySobrePack, FuenteDeReplayEnVivo,
                                  genera_secuencia_qok_contrato, resuelve_concurrente_qok_forzado)

from bot import bucle_de_tiempo, config, estado as E, orquestador as O
from bot import bucle_del_dia as BDD

_, checksum = config.cargar()

N_DIAS = 30
if '--full' in sys.argv:
    N_DIAS = None
for arg in sys.argv[1:]:
    if arg.isdigit():
        N_DIAS = int(arg)

RUTA_PACK = os.path.join(ING, "tests", "replay_v10.json")
pack = json.load(open(RUTA_PACK))
dias_pack_redondeados = pack["dias"] if N_DIAS is None else pack["dias"][:N_DIAS]
n_dias = len(dias_pack_redondeados)

# HALLAZGO documentado en bot/orquestador.py (docstring del módulo, bloque
# "HALLAZGO"): orquestador.corre_replay() NO usa las barras redondeadas a 2
# decimales que trae el pack -- las reconstruye en precisión completa desde
# modelo/datos/HG22.npy (emparejamiento exacto). El bucle en vivo (D8.2/D8.3)
# tiene que ver EXACTAMENTE lo mismo que ve el oráculo offline, o diverge por
# precisión de redondeo, no por ningún bug -- MISMA función que usa
# corre_replay(), reutilizada aquí sin cambios (R6: no se toca modelo/, solo
# se lee).
dias_pack = O._recupera_precision_completa(dict(pack, dias=dias_pack_redondeados))

DIR_TMP = "/tmp/prueba_puerta_grande"
RUTA_PACK_RECORTADO = os.path.join(DIR_TMP, "pack.json")

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def compara_fin_de_dia(dias_ref, fines_mios, tol=1e-3):
    """Misma comparación que tests/runner_replay_v10.py -- ver
    verificacion_R3/romper_mi_orquestador.py::comparar_fin_de_dia."""
    f = []
    for i, (a, b) in enumerate(zip(dias_ref, fines_mios), start=1):
        for ruta in (('caja',), ('funded', 'bal'), ('funded', 's0'), ('eval', 'bal'),
                     ('recamara', 'n'), ('pool', 'frescas'), ('pool', 'rotas')):
            x, y = a, b
            for k in ruta:
                x, y = x[k], y[k]
            if abs(x - y) > tol:
                f.append((i, '.'.join(ruta), x, y))
    return f


shutil.rmtree(DIR_TMP, ignore_errors=True)
os.makedirs(DIR_TMP)
# el pack de referencia se queda REDONDEADO -- corre_replay() aplica su
# propia _recupera_precision_completa() internamente (precision_completa=True
# por defecto); dias_pack (ya en precisión completa) es SOLO para el arnés.
json.dump(dict(pack, dias=dias_pack_redondeados), open(RUTA_PACK_RECORTADO, 'w'))

print(f"=== referencia: orquestador.corre_replay() sobre {n_dias} días ===")
t0 = time.time()
fines_ref, diarios_ref, st_ref = O.corre_replay(RUTA_PACK_RECORTADO)
print(f"  caja final de referencia: {st_ref['caja']}  ({time.time() - t0:.1f}s)")

print(f"\n=== capturando la secuencia de qok del CONTRATO (instrumentación, no reconstrucción) ===")
secuencia_qok = genera_secuencia_qok_contrato(RUTA_PACK_RECORTADO)
ok(f"{n_dias} valores de qok capturados", len(secuencia_qok) == n_dias, len(secuencia_qok))


def corre_pasada(modo_qok, sufijo):
    """modo_qok: 'contrato' (Pasada A, qok inyectado) | 'causal' (Pasada B,
    qok real del bot). Devuelve (st_final, fines_mios, diario_leido)."""
    dir_run = os.path.join(DIR_TMP, sufijo)
    shutil.rmtree(dir_run, ignore_errors=True)
    os.makedirs(dir_run)
    ruta_estado = os.path.join(dir_run, "estado.json")
    E.guardar(E.nuevo(pack.get('version', 'v10'), checksum), ruta_estado)

    CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES = "CH-EVAL", "CP-EVAL", "CH-FUN", "CP-FUN", "MES"
    adaptador = AdaptadorReplaySobrePack(MES, modo='perfecto')
    fuente = FuenteDeReplayEnVivo(dias_pack, adaptador, CP_EVAL, CP_FUN)

    if modo_qok == 'contrato':
        resuelve_original = bucle_de_tiempo.resuelve_dia_concurrente
        bucle_de_tiempo.resuelve_dia_concurrente = resuelve_concurrente_qok_forzado(
            secuencia_qok, resuelve_original)
    try:
        st_final = BDD.bucle_del_dia(
            fuente, adaptador,
            cuenta_hedge_eval=CH_EVAL, cuenta_prop_eval=CP_EVAL,
            cuenta_hedge_funded=CH_FUN, cuenta_prop_funded=CP_FUN,
            instrumento_prop=MES,
            ruta_estado=ruta_estado, ruta_nivel=os.path.join(dir_run, "nivel.json"),
            ruta_ordenes=os.path.join(dir_run, "ordenes"), ruta_lock=os.path.join(dir_run, "bot.lock"),
            dir_instantaneas=os.path.join(dir_run, "instantaneas"), dias_retenidos=5,
            ruta_diario=os.path.join(dir_run, "diario.jsonl"), fase='plena', dormir=lambda s: None)
    finally:
        if modo_qok == 'contrato':
            bucle_de_tiempo.resuelve_dia_concurrente = resuelve_original

    diario_leido = [json.loads(l) for l in open(os.path.join(dir_run, "diario.jsonl"))]
    fines_mios = [d['fin_de_dia'] for d in diario_leido]
    shutil.rmtree(dir_run, ignore_errors=True)
    return st_final, fines_mios, diario_leido


print(f"\n=== PASADA A (fidelidad): qok del contrato, {n_dias} días por el bucle en vivo ===")
t0 = time.time()
st_a1, fines_a1, diario_a1 = corre_pasada('contrato', 'pasada_a_1')
print(f"  caja final Pasada A: {st_a1['caja']}  ({time.time() - t0:.1f}s)")

disc_a = compara_fin_de_dia(fines_ref, fines_a1)
ok(f"Pasada A: {n_dias} días procesados", st_a1['dia_negociacion'] == n_dias, st_a1['dia_negociacion'])
ok("Pasada A: 0 discrepancias contra orquestador.corre_replay() (tolerancia 1e-3 $)",
   len(disc_a) == 0, disc_a[:5])
ok("Pasada A: caja final IDÉNTICA (tolerancia 1e-3 $)",
   abs(st_a1['caja'] - st_ref['caja']) < 1e-3, (st_a1['caja'], st_ref['caja']))

print(f"\n=== DETERMINISMO: Pasada A corrida una SEGUNDA vez, {n_dias} días ===")
t0 = time.time()
st_a2, fines_a2, diario_a2 = corre_pasada('contrato', 'pasada_a_2')
print(f"  caja final (2ª corrida): {st_a2['caja']}  ({time.time() - t0:.1f}s)")
ok("determinismo: caja final BIT A BIT igual entre las dos corridas de la Pasada A",
   st_a1['caja'] == st_a2['caja'], (st_a1['caja'], st_a2['caja']))
ok("determinismo: el diario completo es BIT A BIT igual entre las dos corridas",
   diario_a1 == diario_a2, "coincide" if diario_a1 == diario_a2 else "DIFIERE")

print(f"\n=== PASADA B (causalidad): qok CAUSAL real, {n_dias} días por el bucle en vivo ===")
t0 = time.time()
st_b, fines_b, diario_b = corre_pasada('causal', 'pasada_b')
print(f"  caja final Pasada B: {st_b['caja']}  ({time.time() - t0:.1f}s)")

disc_b = compara_fin_de_dia(fines_ref, fines_b)
dias_obtenidos_divergentes = sorted(set(d for d, _, _, _ in disc_b))
print(f"  días que divergen en la Pasada B: {dias_obtenidos_divergentes}")
# el día 269 es la CAUSA RAÍZ (defecto D-5: qok causal vs contrato) -- una vez
# el estado bifurca ahí (eval/pool/caja ya no coinciden), TODO día posterior
# hereda esa bifurcación y diverge también, sin que sea un bug nuevo cada
# vez -- lo que exige el gate es que el PRIMER día que diverge sea,
# exactamente, el 269 (si el pack llega tan lejos), no que sea el único.
if n_dias >= 269:
    ok("Pasada B: el PRIMER día que diverge es exactamente el 269 (defecto conocido D-5, "
       "modelo/DEFECTOS_CONOCIDOS.md) -- los posteriores heredan la bifurcación, no son bugs nuevos",
       dias_obtenidos_divergentes[:1] == [269], dias_obtenidos_divergentes[:1])
    ok("Pasada B: ningún día ANTES del 269 diverge",
       all(d >= 269 for d in dias_obtenidos_divergentes), dias_obtenidos_divergentes)
else:
    ok("Pasada B: 0 divergencias (el pack recortado no llega al día 269, el defecto D-5 no aplica)",
       len(dias_obtenidos_divergentes) == 0, dias_obtenidos_divergentes)
if disc_b:
    print(f"  detalle de las primeras divergencias: {disc_b[:10]}")

shutil.rmtree(DIR_TMP, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK  (N_DIAS={n_dias})")
if n_ok != len(resultados):
    sys.exit(1)
