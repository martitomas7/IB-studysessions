# -*- coding: utf-8 -*-
"""D8.4 reestructuración (RESPUESTA_D8_CONCURRENCIA.md §3) -- golden de
`ciclo_vida.procesa_dia_eval` capturado ANTES de partirlo en
`arma_intento_eval`/`arma_empalme_eval`/`cierra_resolucion_eval`, sobre un
día que ejercita el empalme de VERDAD (R-4.3) -- el pack de 504 días
(`tests/replay_v10.json`) no produce NINGÚN empalme (medido: 0/504), así
que ese camino de código nunca lo prueba el gate del replay ni
`romper_mi_orquestador.py`. Sin este test, la extracción del empalme podía
tener un bug real y nada lo habría cazado (R1/R3).

Receta (medida, no adivinada): un intento fresco (bal=0) tocando el suelo
NUNCA muere solo (R-3.4 fija dx=-ndn, y el Mm de un intento fresco es
holgado frente a eso). Pero al día SIGUIENTE, con el bal ya erosionado por
ese primer toque de suelo, `sizing.plan()` encoge Mm lo bastante como para
que un SEGUNDO toque de suelo, en la barra 1, SÍ muera -- con
barra_evento=1 (bien dentro de `empalme_barra_limite=4` de 86 barras),
dispara R-4.3 de verdad.

3 casos, generados en cadena (el 2 y el 2b parten del mismo estado que
deja el día 1):
  1. día 1 -- toque de suelo puro: pausa, sigue activa, sin empalme.
  2. día 2 -- muere en barra 1 -> EMPALME -> el empalme sube hasta tocar
     el objetivo -> aprobación/recompra (ejercita también ESE camino).
  2b. día 2 variante -- muere TARDE (barra 83, fuera de la ventana de
      empalme) -> no empalma -> se desactiva.

Los 3 resultados se comparan bit a bit contra el golden capturado con la
función monolítica original (ver el commit de esta extracción para el
script que lo generó)."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import config, ciclo_vida as CV, estado as E

_, checksum = config.cargar()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


NB = 86
st = E.nuevo('v10', checksum)
st['pool'] = dict(frescas=5, rotas=0, subs=[])


def dia_toque_de_suelo(p0=5000.0, barra_toque=1):
    ph = [p0] * NB
    pl = [p0] * NB
    pc = [p0] * NB
    pl[barra_toque] = p0 - 20.0   # cualquier cosa por debajo de ndn -- R-3.4 fija dx=-ndn
    pc[barra_toque] = pl[barra_toque]
    for b in range(barra_toque + 1, NB):
        ph[b] = pl[b] = pc[b] = pc[barra_toque]
    return ph, pl, pc


# === día 1: toque de suelo puro (pausa) =====================================
ev0 = dict(activa=False, bal=0.0, pico=0.0, H=0.0, s0=0.0, k=0.0, m=0.0,
           aprobada_provisional=False, aprobada_confirmada=False)
pool0 = dict(st['pool'])
ph1, pl1, pc1 = dia_toque_de_suelo()
r1 = CV.procesa_dia_eval(ev0, pool0, [], direccion=1, ph=ph1, pl=pl1, pc=pc1, b0v=0,
                          qok=True, modo_auto_confirma=True, estado=st, dia_actual=1)

ok("día 1: pausa pura (sigue activa, sin muerte)",
   r1['hubo_muerte'] is False and r1['eval_estado']['activa'] is True)
ok("día 1: bal == -1057.0 (dx=-ndn=-6.6667 * 5*30 - comision 57, el golden)",
   abs(r1['eval_estado']['bal'] - (-1057.0)) < 1e-6, r1['eval_estado']['bal'])
ok("día 1: pool.frescas bajó a 4, sin rotas", r1['pool_estado'] == dict(frescas=4, rotas=0, subs=[]))
ok("día 1: eventos coincide con el golden",
   r1['eventos'] == dict(intentos=1, aprobaciones=0, emergencias=0, recompras=0, muertes_eval=0))

# === día 2: bal ya erosionado -- el mismo toque de suelo SÍ muere, en barra 1,
#     y el empalme sube hasta tocar el objetivo (ejercita aprobación dentro
#     del propio empalme) ========================================================
p0_dia2 = 5000.0
ph2 = [p0_dia2] * NB
pl2 = [p0_dia2] * NB
pc2 = [p0_dia2] * NB
pl2[1] = p0_dia2 - 20.0
pc2[1] = pl2[1]
p0_empalme = pl2[1]
ph2[5] = p0_empalme + 50.0   # sube muy por encima de nu (~20.38) en la barra 5
pc2[5] = ph2[5]
for b in range(6, NB):
    ph2[b] = pl2[b] = pc2[b] = pc2[5]
for b in range(2, 5):
    ph2[b] = pl2[b] = pc2[b] = p0_empalme

r2 = CV.procesa_dia_eval(r1['eval_estado'], r1['pool_estado'], [], direccion=1,
                          ph=ph2, pl=pl2, pc=pc2, b0v=0, qok=True,
                          modo_auto_confirma=True, estado=st, dia_actual=2)

ok("día 2: muere el intento 0 (continuación de la pausa de ayer)", r2['hubo_muerte'] is True)
ok("día 2: 1 muerte, 1 intento (el empalme -- el intento 0 es continuación, no toma sub)",
   r2['eventos']['muertes_eval'] == 1 and r2['eventos']['intentos'] == 1, r2['eventos'])
ok("día 2: el EMPALME tocó objetivo -- 1 aprobación, 1 recompra, sunk_a_recamara puesto",
   r2['eventos']['aprobaciones'] == 1 and r2['eventos']['recompras'] == 1
   and r2['sunk_a_recamara'] is not None)
ok("día 2: bal final == T_eval (3000.0, redondeo de coma flotante incluido)",
   abs(r2['eval_estado']['bal'] - 3000.0) < 1e-6, r2['eval_estado']['bal'])
ok("día 2: sunk_a_recamara == 283.7999... (el golden exacto)",
   abs(r2['sunk_a_recamara'] - 283.79999999999995) < 1e-6, r2['sunk_a_recamara'])
ok("día 2: caja_delta == -214.7999... (el golden exacto)",
   abs(r2['caja_delta'] - (-214.79999999999998)) < 1e-6, r2['caja_delta'])
ok("día 2: pool_estado == golden (rotas=1 por la muerte del intento 0, frescas de vuelta a 4 -- empalme -1, recompra +1)",
   r2['pool_estado'] == dict(frescas=4, rotas=1, subs=[]), r2['pool_estado'])
ok("día 2: la cuenta queda vacía tras la aprobación confirmada (auto-confirma)",
   r2['eval_estado']['activa'] is False and r2['eval_estado']['aprobada_confirmada'] is True)

# === día 2b (mismo punto de partida que el día 1): muere TARDE -- fuera de
#     la ventana de empalme -> no empalma -> se desactiva ====================
ph2b, pl2b, pc2b = dia_toque_de_suelo(barra_toque=83)   # 83 >= 86-4=82 -> fuera de ventana
r2b = CV.procesa_dia_eval(r1['eval_estado'], r1['pool_estado'], [], direccion=1,
                           ph=ph2b, pl=pl2b, pc=pc2b, b0v=0, qok=True,
                           modo_auto_confirma=True, estado=st, dia_actual=2)

ok("día 2b: muere tarde, sin empalme (fuera de la ventana), se desactiva",
   r2b['hubo_muerte'] is True and r2b['eval_estado']['activa'] is False)
ok("día 2b: eventos.intentos == 0 (nunca se intentó el empalme -- ni siquiera un toma_sub fallido)",
   r2b['eventos']['intentos'] == 0, r2b['eventos'])
ok("día 2b: bal == -2104.5 (el golden exacto, k/ndn del día ya erosionado)",
   abs(r2b['eval_estado']['bal'] - (-2104.5)) < 1e-6, r2b['eval_estado']['bal'])
ok("día 2b: pool_estado == golden (rotas=1 por la muerte, sin empalme que la reduzca)",
   r2b['pool_estado'] == dict(frescas=4, rotas=1, subs=[]), r2b['pool_estado'])

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
