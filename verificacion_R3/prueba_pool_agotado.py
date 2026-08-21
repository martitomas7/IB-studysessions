# -*- coding: utf-8 -*-
"""D8 §5.3 (ANALISIS_PUERTA_GRANDE.md §5): pool agotado sin sub disponible --
cobertura 0 en la Puerta Grande (en 504 días el pack nunca lo toca -- ver
`verificacion_R3/CENSO_COBERTURA.md`). El pedido: "Forzar frescas=0,
rotas=0, comprobar que el slot queda vacío limpio, sin hedge abierto a
medias."

Una nota honesta ANTES de fabricar el escenario (R1/R3): con
`orquestacion.pool_subs=2` (03_CONFIG.yaml) y la invariante #3 de
`bot/estado.py::validar` (`pool.frescas + pool.rotas + (1 si eval.activa)
== pool_subs`), `frescas=0 Y rotas=0` con eval INACTIVA es un estado que
esa invariante nunca permitiría llegar a ver en un `estado.json` guardado
-- con solo 2 subs en total, si eval no tiene ninguna, las OTRAS DOS
tienen que estar en frescas/rotas. La única forma real de agotar el pool
del todo, con la config de hoy, es `frescas=0, rotas=2` Y la palanca de
Clase B `emergencia` desactivada por el operador (si no, `toma_sub` SIEMPRE
puede recomprar una rota -- eso NO es agotamiento, es el camino normal de
emergencia, R-4.5).

Este test hace las DOS cosas, por separado y con el rótulo correcto:

1. `frescas=0, rotas=0` EXACTAMENTE como lo pide el operador -- sobre las
   funciones puras (`ciclo_vida.toma_sub`/`arma_intento_eval`) en
   aislamiento, sin necesidad de que sea un estado global "guardable" --
   es la prueba de robustez más dura posible sobre esas dos funciones:
   ni siquiera la emergencia tiene nada que recomprar.
2. El estado REAL, guardable, consistente con la invariante #3 --
   `frescas=0, rotas=2` con `emergencia` apagada por el operador -- corrido
   varios días seguidos por `orquestador.procesa_dia()` (el mismo bucle de
   producción), confirmando que el slot queda limpio (nunca a medias, nunca
   con hedge abierto), sin invariantes rotos, y que se recupera solo en
   cuanto una sub vuelve a estar disponible."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import ciclo_vida as CV, config, estado as E, orquestador as O

_, checksum = config.cargar()
cfg = config.obtener()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


VACIO = dict(desviaciones_activas=[])
EV0 = dict(activa=False, bal=0.0, pico=0.0, H=0.0, s0=0.0, k=0.0, m=0.0,
           aprobada_provisional=False, aprobada_confirmada=False)
EVENTOS0 = dict(intentos=0, aprobaciones=0, muertes_funded=0, muertes_eval=0,
                resets=0, emergencias=0, recompras=0, cuotas_dia=0.0)

# =============================================================================
# 1. frescas=0, rotas=0 -- EXACTAMENTE como lo pide el operador, sobre las
#    funciones puras, en aislamiento (sin necesidad de un estado global
#    "guardable" -- ver la nota del docstring del módulo).
# =============================================================================
print("=== 1. frescas=0, rotas=0 -- ni la emergencia tiene nada que recomprar ===")

r_emergencia_on = CV.toma_sub(0, 0, estado=VACIO, dia_actual=1)
ok("toma_sub(frescas=0, rotas=0), emergencia ON por defecto: NO hay sub, en NINGÚN camino "
   "(ni fresca ni de emergencia)", r_emergencia_on == (False, False, 0.0, 0, 0), r_emergencia_on)

pool_agotado = dict(frescas=0, rotas=0, subs=[])
r_arma = CV.arma_intento_eval(EV0, pool_agotado, caja_delta=0.0, eventos=dict(EVENTOS0),
                               qok=True, intentos_nuevos_ok=True, estado=VACIO, dia_actual=1)
ok("arma_intento_eval con pool agotado (y qok=True, intentos_nuevos_ok=True -- las DOS "
   "condiciones que SÍ dejarían arrancar si hubiera sub): arranca=False",
   r_arma['arranca'] is False, r_arma['arranca'])
ok("el slot queda LIMPIO -- eval_estado exactamente igual que antes (nunca 'a medias', "
   "nunca con activa=True sin plan)", r_arma['eval_estado'] == EV0, r_arma['eval_estado'])
ok("el pool NO se toca (sigue frescas=0, rotas=0 -- no hay un descuento fantasma)",
   r_arma['pool_estado'] == pool_agotado, r_arma['pool_estado'])
ok("caja_delta se queda en 0.0 -- ningún coste de sub fantasma (ni cuota, ni comisión de "
   "emergencia)", r_arma['caja_delta'] == 0.0, r_arma['caja_delta'])
ok("eventos no cuenta NINGÚN intento/aprobación/emergencia que no ocurrió",
   r_arma['eventos'] == EVENTOS0, r_arma['eventos'])

# =============================================================================
# 2. El estado REAL, consistente con la invariante #3 de estado.py: sin
#    fresca Y con la emergencia apagada por el operador -- corrido varios
#    días por el bucle REAL de producción (orquestador.procesa_dia()).
# =============================================================================
print("\n=== 2. frescas=0, rotas=2, emergencia apagada por el operador -- N días "
      "seguidos, por el bucle real ===")

NB = 86
P0 = 5000.0
ph = [P0] * NB
pl = [P0] * NB
pc = [P0] * NB

DIR = "/tmp/prueba_pool_agotado"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)

st = E.nuevo('v10', checksum)
st['pool'] = dict(frescas=0, rotas=2, subs=[])
DESVIACION_EMERGENCIA_OFF = dict(palanca='emergencia', desde_dia=1, hasta_dia=100,
                                  quien='prueba_pool_agotado', ts_pared='2026-08-21T00:00:00Z')
st['desviaciones_activas'] = [DESVIACION_EMERGENCIA_OFF]

cfg_emerg_default = cfg.orquestacion.emergencia.valor()
ok("(control) 'emergencia' SIGUE en True en 03_CONFIG.yaml -- la desactivación de arriba "
   "es una desviación del OPERADOR (Clase B), no un cambio de la config congelada",
   cfg_emerg_default is True, cfg_emerg_default)

N_DIAS = 7
caja_esperada_por_dia = CV.coste_diario_pool()
trayectoria = []
for dia in range(1, N_DIAS + 1):
    st, fin_de_dia, diario = O.procesa_dia(st, direccion=1, ventana_txt='22h', ph=ph, pl=pl, pc=pc,
                                            b0v=0, n_resets_hoy=0)
    fallos = E.validar(st, checksum)
    trayectoria.append(dict(dia=dia, eval_activa=st['eval']['activa'], pool=dict(st['pool']),
                             caja=st['caja'], fallos=fallos,
                             emergencias=diario['eventos']['emergencias'],
                             intentos=diario['eventos']['intentos']))

for snap in trayectoria:
    ok(f"día {snap['dia']}: 0 invariantes rotos (estado.validar limpio, sin crash)",
       len(snap['fallos']) == 0, snap['fallos'])
    ok(f"día {snap['dia']}: eval sigue INACTIVA -- el slot queda vacío limpio, {snap['dia']} "
       f"días seguidos sin hedge abierto a medias", snap['eval_activa'] is False,
       snap['eval_activa'])
    ok(f"día {snap['dia']}: pool sigue exactamente frescas=0, rotas=2 -- ni un descuento "
       f"fantasma, ni la emergencia coló una recompra que no tocaba",
       snap['pool'] == dict(frescas=0, rotas=2, subs=[]), snap['pool'])
    ok(f"día {snap['dia']}: 0 emergencias, 0 intentos -- el gate qok/pool/emergencia bloqueó "
       f"de verdad, no silenciosamente a medias",
       snap['emergencias'] == 0 and snap['intentos'] == 0,
       (snap['emergencias'], snap['intentos']))

caja_esperada = -caja_esperada_por_dia * N_DIAS
ok(f"tras {N_DIAS} días, la caja solo bajó por el coste FIJO del pool "
   f"({caja_esperada_por_dia:.4f} $/día, mismo con pool agotado que con pool lleno -- "
   f"se paga por las suscripciones tenidas, no por las usadas) -- nada más",
   abs(st['caja'] - caja_esperada) < 1e-6, (st['caja'], caja_esperada))

# --- recuperación limpia: en cuanto un reset de verdad libera una sub, eval
#     arranca al día siguiente sin rastro del agotamiento previo -----------
print("\n=== recuperación: un reset real (rotas->frescas) libera el slot, sin intervención ===")
st['pool']['frescas'] = 1
st['pool']['rotas'] = 1   # mismo total (2) -- un reset de verdad, no una sub nueva de la nada
st, fin_de_dia, diario = O.procesa_dia(st, direccion=1, ventana_txt='22h', ph=ph, pl=pl, pc=pc,
                                        b0v=0, n_resets_hoy=0)
fallos_recuperacion = E.validar(st, checksum)
ok("0 invariantes rotos tras la recuperación", len(fallos_recuperacion) == 0, fallos_recuperacion)
ok("eval arranca LIMPIO el mismo día que hay una fresca -- el agotamiento previo no deja "
   "ningún rastro ni penalización", st['eval']['activa'] is True, st['eval']['activa'])

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
