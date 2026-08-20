# -*- coding: utf-8 -*-
"""R3 (Task 20, REVISION_REV5.md §4.1 / ORDEN_DE_TRABAJO_D8.md §3.1):
comparación pura del residuo diario. Fabrica pares teórico/real con
`sesion.resolver_dia` (mismo camino real, no un mock) variando solo el
deslizamiento -- exactamente lo que un fill real peor que el nivel exacto
del modelo produciría."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import config, sesion as SES
from bot.residuo_diario import acumula_residuos, calcula_residuo_dia

_, _ = config.cargar()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


plan = dict(k=10.0, nu=8.0, ndn=8.0, bloqueo=False, comision=1.5, Mm=5.0)  # Mm bajo -> muere fácil
ph = [5000, 5001]
pl = [5000, 4980]   # toca el suelo en la primera barra vigilada -> muerte
pc = [5000, 4985]

print("=== 1. día IDÉNTICO (mismo deslizamiento) -> residuo cero, mismo desenlace ===")
teorico = SES.resolver_dia(ph, pl, pc, 0, plan, m=4, fric=3.0, deslizamiento=0.0)
real_igual = SES.resolver_dia(ph, pl, pc, 0, plan, m=4, fric=3.0, deslizamiento=0.0)
r0 = calcula_residuo_dia(teorico, real_igual)
ok("residuo_total_usd = 0.0 cuando el día real es idéntico al teórico",
   r0['residuo_total_usd'] == 0.0, r0)
ok("mismo_desenlace = True", r0['mismo_desenlace'] is True)

print("\n=== 2. fill peor que el modelo (deslizamiento real > 0, teórico = 0) -> residuo negativo ===")
real_peor = SES.resolver_dia(ph, pl, pc, 0, plan, m=4, fric=3.0, deslizamiento=2.5)
r1 = calcula_residuo_dia(teorico, real_peor)
ok("el residuo de hedge es exactamente -deslizamiento (2.5) -- la única diferencia entre las dos "
   "llamadas es 'deslizamiento', y R-3.5 solo lo resta en la salida de muerte",
   abs(r1['residuo_hedge_usd'] - (-2.5)) < 1e-9, r1)
ok("mismo_desenlace sigue True -- el deslizamiento no cambia SI murió, solo cuánto costó",
   r1['mismo_desenlace'] is True)
ok("residuo_dx_puntos = 0.0 -- el deslizamiento afecta a hedge_dolares (R-3.5), no a dx_puntos",
   r1['residuo_dx_puntos'] == 0.0, r1)

print("\n=== 3. desenlace DISTINTO (p.ej. el modelo decía 'sobrevive', la realidad murió) ===")
plan_sobrevive = dict(k=10.0, nu=8.0, ndn=200.0, bloqueo=False, comision=1.5, Mm=5000.0)
ph_sin_tocar = [5000, 5001]
pl_sin_tocar = [5000, 4990]   # no llega a tocar el suelo (ndn=200) con este plan
pc_sin_tocar = [5000, 4995]
teorico_sobrevive = SES.resolver_dia(ph_sin_tocar, pl_sin_tocar, pc_sin_tocar, 0, plan_sobrevive,
                                      m=4, fric=3.0, deslizamiento=0.0)
ok("control: el teórico efectivamente NO murió", teorico_sobrevive['muere'] is False)
# el "real" usa un plan con Mm mucho más bajo -- misma trayectoria de precio, pero la cuenta SÍ
# habría muerto con ese margen (fabrica el caso "el modelo estaba mal calibrado ese día")
plan_muere_real = dict(plan_sobrevive, Mm=1.0)
real_muere = SES.resolver_dia(ph_sin_tocar, pl_sin_tocar, pc_sin_tocar, 0, plan_muere_real,
                               m=4, fric=3.0, deslizamiento=0.0)
r2 = calcula_residuo_dia(teorico_sobrevive, real_muere)
ok("mismo_desenlace = False cuando muere/pausa/objetivo difieren -- señal MÁS grave que un "
   "simple residuo en dólares", r2['mismo_desenlace'] is False, r2)
ok("desenlace_teorico y desenlace_real quedan ambos expuestos para diagnóstico",
   r2['desenlace_teorico']['muere'] is False and r2['desenlace_real']['muere'] is True, r2)

print("\n=== 4. acumula_residuos(): agregación sobre varios días ===")
lista = [r0, r1, r2]
agg = acumula_residuos(lista)
ok("n_dias correcto", agg['n_dias'] == 3, agg)
ok("residuo_total_usd_acumulado = suma de los tres residuos individuales",
   abs(agg['residuo_total_usd_acumulado'] - (r0['residuo_total_usd'] + r1['residuo_total_usd']
       + r2['residuo_total_usd'])) < 1e-9, agg)
ok("dias_con_desenlace_distinto cuenta exactamente el día 3 (el único con mismo_desenlace=False)",
   agg['dias_con_desenlace_distinto'] == 1, agg)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
