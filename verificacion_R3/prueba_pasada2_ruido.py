# -*- coding: utf-8 -*-
"""PASADA 2 de LA PUERTA GRANDE (ANALISIS_PUERTA_GRANDE.md §4) -- el ruido
de ejecución, anclado y barrido, nunca inventado (§4b, "no se ancla se
inventa -- se ancla y se barre").

Reutiliza el MISMO arnés "por el bucle en vivo" de `prueba_puerta_grande.py`
(bot/bucle_del_dia.py, D8.2/D8.3/D8.5 de verdad, bar a bar) -- la Pasada 2
recorre el MISMO camino ya validado por la Puerta Grande de hoy (Pasada A/B),
con más fricción. Ver `apoyo_pasada2.py` para el porqué del mecanismo
(generaliza el MISMO canal aislado que ya usa `slip_usd_micro` -- nunca
toca `dx_puntos`/`bal`/`pool`/`muere`, solo el `$` que ya fluye hacia
`caja`) y el diseño descartado antes de llegar a este (fabricar la
desviación en el precio de fill del adaptador, que SÍ contamina `bal`).

Tres partes:

0. Ancla (§4b): `con_ruido_ejecucion(ruido_normal_ticks=0, ruido_muerte_ticks=2)`
   debe reproducir EXACTAMENTE (bit a bit) la corrida SIN el gestor -- 2
   ticks * 1,25 $/tick = 2,50 $/micro = `slip_usd_micro` de
   `03_CONFIG.yaml`. Si esto no cuadra bit a bit, el arnés está mal, no
   el mercado (mismo principio que la Pasada A de la Puerta Grande).

1. Barrido de fills normales (0 / 0,25 / 0,5 / 1 tick), `ruido_muerte_ticks`
   fijo en el ancla (2) -- "lo que hoy NO está modelado". Se comprueba
   aislamiento (eval.bal/funded.bal IDÉNTICOS día a día en las 4 corridas
   -- el ruido normal NUNCA debe tocar la cuenta del proveedor, solo la
   caja del hedge) y monotonía (más ruido, caja igual o menor).

2. Barrido de sensibilidad de la salida por muerte (1 / 2 / 5 / 10 ticks
   -- verde/ámbar/rojo de la norma), `ruido_normal_ticks=0`. Mismo
   aislamiento + monotonía, MÁS el criterio pre-registrado (§4, "el
   entregable no es un número, es una curva"): la caja debe caer
   LINEALMENTE con pendiente EXACTA = -(muertes_eval·m_eval +
   muertes_funded·m_fun) -- el pendiente NUNCA se inventa: se cuenta
   directamente de `eventos.muertes_eval`/`muertes_funded` acumulados del
   propio diario de ESTA corrida (para N_DIAS=504 son 150 y 94 -- 676
   micro-muertes, la cifra que predice `ANALISIS_PUERTA_GRANDE.md` -- pero
   el test nunca hardcodea 676: lo deriva, para que siga siendo válido
   sobre cualquier subconjunto usado en iteración rápida).

N_DIAS es un argumento de línea de comandos -- por defecto un subconjunto
pequeño para iterar rápido; `--full` corre los 504 días completos (la
única corrida que reproduce el pendiente EXACTO de 676 que predice el
operador)."""
import json
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)
sys.path.insert(0, AQUI)

from apoyo_puerta_grande import AdaptadorReplaySobrePack, FuenteDeReplayEnVivo
from apoyo_pasada2 import con_ruido_ejecucion

from bot import bucle_del_dia as BDD
from bot import config, estado as E, orquestador as O

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
# ver prueba_puerta_grande.py -- mismo HALLAZGO documentado en bot/orquestador.py
dias_pack = O._recupera_precision_completa(dict(pack, dias=dias_pack_redondeados))

cfg = config.obtener()
TICK_USD = cfg.hedge_broker.tick_usd.valor()
VALOR_PUNTO_USD = cfg.hedge_broker.valor_punto_usd.valor()
SLIP_USD_MICRO = cfg.hedge_broker.slip_usd_micro.valor()
M_EVAL = cfg.sizing.m_eval.valor()
M_FUN = cfg.sizing.m_fun.valor()
ANCLA_TICKS = SLIP_USD_MICRO / TICK_USD   # 2,50/1,25 = 2 -- §4b, nunca inventado

DIR_TMP = "/tmp/prueba_pasada2_ruido"

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def corre(sufijo, gestor=None):
    dir_run = os.path.join(DIR_TMP, sufijo)
    shutil.rmtree(dir_run, ignore_errors=True)
    os.makedirs(dir_run)
    ruta_estado = os.path.join(dir_run, "estado.json")
    E.guardar(E.nuevo(pack.get('version', 'v10'), checksum), ruta_estado)

    CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES = "CH-EVAL", "CP-EVAL", "CH-FUN", "CP-FUN", "MES"
    adaptador = AdaptadorReplaySobrePack(MES, modo='perfecto')   # SIEMPRE perfecto -- el ruido
    fuente = FuenteDeReplayEnVivo(dias_pack, adaptador, CP_EVAL, CP_FUN)   # va por con_ruido_ejecucion

    def _corre():
        return BDD.bucle_del_dia(
            fuente, adaptador,
            cuenta_hedge_eval=CH_EVAL, cuenta_prop_eval=CP_EVAL,
            cuenta_hedge_funded=CH_FUN, cuenta_prop_funded=CP_FUN,
            instrumento_prop=MES,
            ruta_estado=ruta_estado, ruta_nivel=os.path.join(dir_run, "nivel.json"),
            ruta_ordenes=os.path.join(dir_run, "ordenes"), ruta_lock=os.path.join(dir_run, "bot.lock"),
            dir_instantaneas=os.path.join(dir_run, "instantaneas"), dias_retenidos=5,
            ruta_diario=os.path.join(dir_run, "diario.jsonl"), dormir=lambda s: None)

    if gestor is not None:
        with gestor:
            st_final = _corre()
    else:
        st_final = _corre()

    diario_leido = [json.loads(l) for l in open(os.path.join(dir_run, "diario.jsonl"))]
    shutil.rmtree(dir_run, ignore_errors=True)
    return st_final, diario_leido


def serie_bal(diario, cuenta):
    return [d['fin_de_dia'][cuenta]['bal'] for d in diario]


def totales_muertes(diario):
    me = sum(d['eventos']['muertes_eval'] for d in diario)
    mf = sum(d['eventos']['muertes_funded'] for d in diario)
    return me, mf


shutil.rmtree(DIR_TMP, ignore_errors=True)
os.makedirs(DIR_TMP)

print(f"=== PASADA 2 -- {n_dias} días, ancla = {SLIP_USD_MICRO}/{TICK_USD} = {ANCLA_TICKS} ticks ===\n")

print("--- Parte 0: ancla -- con_ruido_ejecucion(0, ancla) debe == baseline SIN gestor ---")
st_base, diario_base = corre('base')
st_ancla, diario_ancla = corre(
    'ancla', con_ruido_ejecucion(ruido_normal_ticks=0.0, ruido_muerte_ticks=ANCLA_TICKS))
ok("ancla: caja IDÉNTICA bit a bit vs baseline (reproduce slip_usd_micro por construcción)",
   st_base['caja'] == st_ancla['caja'], (st_base['caja'], st_ancla['caja']))
ok("ancla: diario COMPLETO idéntico bit a bit vs baseline",
   diario_base == diario_ancla)

me_total, mf_total = totales_muertes(diario_base)
pendiente_predicha = -(me_total * M_EVAL + mf_total * M_FUN)
print(f"\n  censo de muertes en esta corrida: {me_total} eval (m={M_EVAL}) + {mf_total} funded (m={M_FUN}) "
      f"= {me_total*M_EVAL + mf_total*M_FUN} micro-muertes -> pendiente predicha = {pendiente_predicha} "
      f"$ por 1 $/micro")

print("\n--- Parte 1: barrido de fills normales (0/0,25/0,5/1 tick), muerte fija en el ancla ---")
puntos_normal = (0.0, 0.25, 0.5, 1.0)
filas_normal = []
bal_eval_ancla = serie_bal(diario_ancla, 'eval')
bal_fun_ancla = serie_bal(diario_ancla, 'funded')
caja_prev = None
for rn in puntos_normal:
    st, diario = corre(f'normal_{rn}',
                        con_ruido_ejecucion(ruido_normal_ticks=rn, ruido_muerte_ticks=ANCLA_TICKS))
    bal_eval = serie_bal(diario, 'eval')
    bal_fun = serie_bal(diario, 'funded')
    ok(f"normal={rn} tick: eval.bal IDÉNTICO día a día vs el ancla (aislamiento -- nunca toca la cuenta)",
       bal_eval == bal_eval_ancla)
    ok(f"normal={rn} tick: funded.bal IDÉNTICO día a día vs el ancla (aislamiento)",
       bal_fun == bal_fun_ancla)
    if caja_prev is not None:
        ok(f"normal={rn} tick: caja NO aumenta vs el punto anterior (monotonía adversa)",
           st['caja'] <= caja_prev + 1e-9, (caja_prev, st['caja']))
    caja_prev = st['caja']
    filas_normal.append((rn, st['caja']))

print("\n--- Parte 2: barrido de sensibilidad de la salida por muerte (1/2/5/10 ticks) ---")
puntos_muerte = (1.0, 2.0, 5.0, 10.0)
filas_muerte = []
diario_m1 = None
caja_prev = None
for rm in puntos_muerte:
    st, diario = corre(f'muerte_{rm}', con_ruido_ejecucion(ruido_normal_ticks=0.0, ruido_muerte_ticks=rm))
    if diario_m1 is None:
        diario_m1 = diario
        bal_eval_m1 = serie_bal(diario, 'eval')
        bal_fun_m1 = serie_bal(diario, 'funded')
    else:
        ok(f"muerte={rm} ticks: eval.bal IDÉNTICO día a día vs muerte=1 (aislamiento)",
           serie_bal(diario, 'eval') == bal_eval_m1)
        ok(f"muerte={rm} ticks: funded.bal IDÉNTICO día a día vs muerte=1 (aislamiento)",
           serie_bal(diario, 'funded') == bal_fun_m1)
    if caja_prev is not None:
        ok(f"muerte={rm} ticks: caja NO aumenta vs el punto anterior (monotonía adversa)",
           st['caja'] <= caja_prev + 1e-9, (caja_prev, st['caja']))
    caja_prev = st['caja']
    filas_muerte.append((rm * TICK_USD, st['caja']))   # eje x en $/micro, no en ticks

print(f"\n  {'$/micro':>10} {'caja':>16}")
for dpm, caja in filas_muerte:
    print(f"  {dpm:>10} {caja:>16.6f}")

pendientes = [(filas_muerte[i][1] - filas_muerte[i-1][1]) / (filas_muerte[i][0] - filas_muerte[i-1][0])
              for i in range(1, len(filas_muerte))]
print(f"\n  pendientes entre puntos consecutivos: {pendientes}")
ok("linealidad: TODAS las pendientes consecutivas son iguales entre sí (tolerancia 1e-6)",
   max(pendientes) - min(pendientes) < 1e-6, pendientes)
ok(f"linealidad: la pendiente medida == la predicha por el censo de muertes ({pendiente_predicha} "
   f"$ por 1 $/micro) -- tolerancia 1e-6",
   abs(pendientes[0] - pendiente_predicha) < 1e-6, (pendientes[0], pendiente_predicha))

# --- entregable: el censo de cobertura pide una CURVA, no un número (§4) -------
RUTA_MD = os.path.join(AQUI, "PASADA_2_RUIDO.md")
with open(RUTA_MD, 'w') as fh:
    fh.write(f"# Pasada 2 de LA PUERTA GRANDE -- ruido de ejecución ({n_dias} días)\n\n")
    fh.write(f"Ancla: `slip_usd_micro`={SLIP_USD_MICRO} $/micro ÷ `tick_usd`={TICK_USD} $/tick = "
             f"**{ANCLA_TICKS} ticks**. Censo de esta corrida: {me_total} muertes eval (m={M_EVAL}) + "
             f"{mf_total} muertes funded (m={M_FUN}) = {me_total*M_EVAL + mf_total*M_FUN} micro-muertes.\n\n")
    fh.write("## Barrido de sensibilidad de la salida por muerte (ruido_normal=0)\n\n")
    fh.write("| ticks | $/micro | caja final | banda |\n|---|---|---|---|\n")
    bandas = {2.5: "verde", 6.25: "ámbar", 12.5: "rojo"}
    for (rm, (dpm, caja)) in zip(puntos_muerte, filas_muerte):
        fh.write(f"| {rm} | {dpm} | {caja:.6f} | {bandas.get(dpm, '')} |\n")
    fh.write(f"\nPendiente medida: **{pendientes[0]:.6f} $** por cada 1 $/micro de deslizamiento extra "
             f"(predicha: {pendiente_predicha}).\n\n")
    fh.write("## Barrido de fills normales -- entrada/objetivo/campana (muerte fija en el ancla)\n\n")
    fh.write("Lo que hoy NO está modelado en `bot/` -- sin predicción pre-registrada (no hay dato "
             "análogo en `03_CONFIG.yaml` que anclarlo); se reporta la curva, no un gate numérico.\n\n")
    fh.write("| ticks | caja final |\n|---|---|\n")
    for rn, caja in filas_normal:
        fh.write(f"| {rn} | {caja:.6f} |\n")
print(f"\n  informe escrito: {RUTA_MD}")

shutil.rmtree(DIR_TMP, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK  (N_DIAS={n_dias})")
if n_ok != len(resultados):
    sys.exit(1)
