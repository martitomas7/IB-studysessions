# -*- coding: utf-8 -*-
"""D8.1 (ORDEN_DE_TRABAJO_D8.md §1) -- puerta explícita: "0 discrepancias
contra sesion.resolver_dia como oráculo, sobre los 504 días del pack Y
≥1.500 estados sintéticos". `prueba_detector_en_vivo.py` ya cubre los 504
días reales (902 estados comparados); este fichero es el ≥1.500
SINTÉTICOS -- casos de borde fabricados a propósito (los que el replay real
no necesariamente contiene, ver ORDEN_DE_TRABAJO_D8.md §5.1) más un barrido
aleatorio masivo con semilla fija (reproducible, no depende del azar real).

Comparación: `resolver_dia()` (lote, oráculo YA verificado) vs
`resuelve_dia_incremental()` (envoltorio de conveniencia sobre
`DetectorEnVivo`, que alimenta barra a barra -- exactamente el camino que
D8 en vivo usará, nunca la fórmula reimplementada aparte)."""
import os
import random
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import config, sesion as SES
from bot.detector_en_vivo import resuelve_dia_incremental

_, _ = config.cargar()  # necesario para valor_punto_usd -- mismo patrón que el resto de R3

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


CAMPOS = ('dx_puntos', 'hedge_dolares', 'comision', 'muere', 'pausa', 'objetivo', 'barra_evento')
TOL = 1e-9


def compara(caso_nombre, ph, pl, pc, b0, plan, m, fric, desliz, discrepancias):
    real = SES.resolver_dia(ph, pl, pc, b0, plan, m, fric, desliz)
    incr = resuelve_dia_incremental(ph, pl, pc, b0, plan, m, fric, desliz)
    for campo in CAMPOS:
        vr, vi = real[campo], incr[campo]
        if isinstance(vr, float):
            igual = abs(vr - vi) < TOL
        else:
            igual = vr == vi
        if not igual:
            discrepancias.append((caso_nombre, campo, vr, vi))


def plan(k=10.0, nu=8.0, ndn=8.0, bloqueo=False, comision=1.5, Mm=500.0):
    return dict(k=k, nu=nu, ndn=ndn, bloqueo=bloqueo, comision=comision, Mm=Mm)


discrepancias = []
n_casos = 0

print("=== casos de borde fabricados a propósito (ORDEN_DE_TRABAJO_D8.md §5.1) ===")

# 1. suelo y objetivo EN LA MISMA BARRA -- R-3.3, el suelo gana el empate
ph = [5000, 5000, 5015, 5015, 5015]
pl = [5000, 5000, 4985, 4985, 4985]
pc = [5000, 5000, 5000, 5000, 5000]
compara("empate_misma_barra", ph, pl, pc, 1, plan(nu=8, ndn=8), 4, 3.0, 0.0, discrepancias)
n_casos += 1

# 2. el suelo se toca en la barra de ENTRADA (b0) -- R-3.2, no se mira, el
#    barrido empieza en b0+1: se fabrica pl[b0] muy por debajo de p0-ndn
#    para confirmar que NO dispara nada (el día sigue).
ph = [5000, 4900, 5000, 5000, 5015]
pl = [4900, 4995, 4995, 4995, 4995]  # pl[b0=0]=4900 -- tocaría el suelo si se mirara
pc = [5000, 5000, 5000, 5000, 5010]
compara("suelo_tocado_en_barra_entrada_ignorado", ph, pl, pc, 0, plan(nu=8, ndn=8), 4, 3.0, 0.0,
        discrepancias)
n_casos += 1

# 3. día de rango cero -- no se mueve nada, cierra por campana sin dividir por cero
ph = pl = pc = [5000.0] * 6
compara("rango_cero", ph, pl, pc, 1, plan(nu=8, ndn=8), 4, 3.0, 0.0, discrepancias)
n_casos += 1

# 4. muerte en la PRIMERA barra vigilada (b0+1) -- el camino más corto posible
ph = [5000, 5001]
pl = [5000, 4980]
pc = [5000, 4985]
compara("muerte_primera_barra", ph, pl, pc, 0, plan(nu=8, ndn=8, Mm=5.0), 4, 3.0, 0.0, discrepancias)
n_casos += 1

# 5. muerte en la ÚLTIMA barra -- límite del empalme
ph = [5000, 5000, 5000, 5000, 5001]
pl = [5000, 5000, 5000, 5000, 4980]
pc = [5000, 5000, 5000, 5000, 4985]
compara("muerte_ultima_barra", ph, pl, pc, 0, plan(nu=8, ndn=8, Mm=5.0), 4, 3.0, 0.0, discrepancias)
n_casos += 1

# 6. bloqueo (k<1) con evento que SÍ habría disparado -- confirma que
#    barra_evento sigue reflejando el barrido real, pero el negocio queda a cero
ph = [5000, 5000, 5015]
pl = [5000, 4985, 5010]
pc = [5000, 5000, 5012]
compara("bloqueado_con_evento", ph, pl, pc, 0, plan(nu=8, ndn=8, bloqueo=True), 4, 3.0, 0.0,
        discrepancias)
n_casos += 1

# 7. bloqueo sin ningún evento (cierra por campana, igual bloqueado)
ph = pl = pc = [5000.0, 5000.0, 5000.0, 5000.0]
compara("bloqueado_sin_evento", ph, pl, pc, 0, plan(nu=8, ndn=8, bloqueo=True), 4, 3.0, 0.0,
        discrepancias)
n_casos += 1

# 8. día degenerado -- NB = b0+1, ni una barra que barrer
ph = pl = pc = [5000.0]
compara("dia_sin_barras_que_barrer", ph, pl, pc, 0, plan(nu=8, ndn=8), 4, 3.0, 0.0, discrepancias)
n_casos += 1

# 9. hueco que salta el suelo (gap muy por debajo de -ndn) -- dx tiene que
#    quedar EXACTO en -ndn (el modelo asume nivel exacto), no en el precio
#    real del hueco -- mismo comportamiento en las dos implementaciones
ph = [5000, 5000]
pl = [5000, 4900]   # gap de 100 puntos, muy por debajo de ndn=8
pc = [5000, 4920]
compara("hueco_salta_el_suelo", ph, pl, pc, 0, plan(nu=8, ndn=8, Mm=5000.0), 4, 3.0, 0.0,
        discrepancias)
n_casos += 1

# 10. techo (objetivo) puro, sin ambigüedad con el suelo
ph = [5000, 5012]
pl = [5000, 4998]
pc = [5000, 5010]
compara("objetivo_puro", ph, pl, pc, 0, plan(nu=8, ndn=8), 4, 3.0, 0.0, discrepancias)
n_casos += 1

# 11. con deslizamiento activo, solo se aplica en la salida de MUERTE (R-3.5)
ph = [5000, 5001]
pl = [5000, 4980]
pc = [5000, 4985]
compara("deslizamiento_solo_en_muerte", ph, pl, pc, 0, plan(nu=8, ndn=8, Mm=5.0), 4, 3.0, 2.5,
        discrepancias)
n_casos += 1
ph2 = [5000, 5012]
pl2 = [5000, 4998]
pc2 = [5000, 5010]
compara("deslizamiento_no_aplica_sin_muerte", ph2, pl2, pc2, 0, plan(nu=8, ndn=8, Mm=5000.0), 4,
        3.0, 2.5, discrepancias)
n_casos += 1

print(f"  {n_casos} casos de borde fabricados, {len(discrepancias)} discrepancias hasta aquí")

print("\n=== barrido aleatorio masivo (semilla fija, reproducible) hasta completar >=1.500 en total ===")
OBJETIVO_TOTAL = 1500
rng = random.Random(20260820)  # semilla fija -- reproducible, no depende del azar real
while n_casos < OBJETIVO_TOTAL:
    NB = rng.randint(2, 90)
    b0 = rng.randint(0, max(0, NB - 2))
    p0 = 5000.0
    ph_r, pl_r, pc_r = [], [], []
    precio = p0
    for _ in range(NB):
        paso = rng.uniform(-6.0, 6.0)
        precio += paso
        alto = precio + rng.uniform(0.0, 4.0)
        bajo = precio - rng.uniform(0.0, 4.0)
        ph_r.append(round(alto, 2))
        pl_r.append(round(bajo, 2))
        pc_r.append(round(precio, 2))
    ndn = rng.uniform(3.0, 20.0)
    nu = rng.uniform(3.0, 20.0)
    Mm = rng.choice([5.0, 50.0, 500.0, 5000.0])   # a veces provoca muerte, a veces no
    m = rng.choice([2, 4, 6, 10])
    k = rng.choice([1, 5, 10, 20])
    fric = rng.uniform(0.0, 5.0)
    desliz = rng.uniform(0.0, 5.0)
    bloqueo = rng.random() < 0.1   # ~10% de los casos, bloqueados
    p = plan(k=k, nu=nu, ndn=ndn, bloqueo=bloqueo, comision=rng.uniform(0.5, 3.0), Mm=Mm)
    compara(f"aleatorio_{n_casos}", ph_r, pl_r, pc_r, b0, p, m, fric, desliz, discrepancias)
    n_casos += 1

ok(f"se compararon {n_casos} estados sintéticos (>= 1.500 exigidos por ORDEN_DE_TRABAJO_D8.md §1)",
   n_casos >= OBJETIVO_TOTAL, n_casos)
ok(f"0 discrepancias detector-en-vivo vs resolver_dia sobre los {n_casos} estados sintéticos",
   len(discrepancias) == 0, discrepancias[:5])

if discrepancias:
    print(f"\n  primeras discrepancias: {discrepancias[:10]}")

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
