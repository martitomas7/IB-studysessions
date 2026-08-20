# -*- coding: utf-8 -*-
"""EQUIVALENCIA nucleo de referencia <-> motor congelado.

`nucleo_referencia_v10.py` se declara "la especificacion EJECUTABLE del nucleo".  Esa
afirmacion hay que sostenerla, no enunciarla: este script genera estados aleatorios, los
resuelve con LAS DOS implementaciones y compara los 9 campos de salida.

Existe porque una auditoria externa senalo que el paquete pedia creer la equivalencia por
prosa.  Cubre ademas la pregunta de precedencia (m7): mientras este script de 0
discrepancias, norma / nucleo / motor son la misma cosa y no hay a quien obedecer.

Uso:  python tests/prueba_nucleo_vs_motor.py [N]        (por defecto 60000)
"""
import os, sys, math
import numpy as np

_AQUI = os.path.dirname(os.path.abspath(__file__))
LAB = os.environ.get('LAB_DIR') or next((c for c in (
    os.path.join(_AQUI, '..', 'modelo'), os.path.join(_AQUI, 'modelo'),
    '/root/work/bot/lab') if os.path.exists(os.path.join(c, 'pipeline3.py'))), None)
assert LAB, "no encuentro pipeline3.py: pon LAB_DIR o coloca modelo/ junto a tests/"
sys.path.insert(0, os.path.abspath(LAB)); sys.path.insert(0, _AQUI)
import pipeline3 as P3
import nucleo_referencia_v10 as NR

N = int(sys.argv[1]) if len(sys.argv) > 1 else 60000
NB = 88
CMS, SLIP = 1.90, 10.0
rng = np.random.default_rng(20260819)

# --- estados aleatorios, cubriendo eval y funded, vivos y al borde de la muerte -------
bal = rng.uniform(-900.0, 3200.0, N)
pk = np.maximum(bal, 0.0) + rng.uniform(0.0, 2600.0, N)
s0 = rng.uniform(0.0, 3000.0, N)          # coste hundido: de una eval nueva a un linaje caro
B = np.where(rng.random(N) < 0.5, 46.295, 81.017)
H = rng.uniform(-1200.0, 900.0, N)
m = np.where(rng.random(N) < 0.5, 2.0, 4.0)
EXP = np.where(m == 2.0, 1110.0, 1480.0)
fric = 3.0 * m
T = np.where(m == 2.0, 3000.0, rng.choice([4100.0, 2000.0], N))
dcap = np.where(m == 2.0, 1e9, T * 0.50)
b0 = rng.choice([0, 0, 0, 62], N)          # ventana 22h / RTH
G = np.maximum(s0, 0.0) + B

# --- caminos: paseo aleatorio con la misma forma que usa el motor ---------------------
paso = rng.normal(0.0, 6.0, (N, NB)).cumsum(1)
ph = paso + np.abs(rng.normal(0.0, 3.0, (N, NB)))
pl = paso - np.abs(rng.normal(0.0, 3.0, (N, NB)))
pc = paso

# un tercio de los estados se coloca DELIBERADAMENTE al borde de la muerte, para que la
# rama de muerte se ejercite de verdad y no por casualidad
_borde = rng.random(N) < 0.34
_fl = np.minimum(pk - 2000.0, 100.0)
bal = np.where(_borde, rng.uniform(1.0, 1100.0, N) + _fl, bal)
G = np.maximum(s0, 0.0) + B

act = np.ones(N, bool)
dx, h, k, cst, muere, pausa, tgt, ib, bloq = P3.sesion(
    bal, pk, G, H, b0, ph, pl, pc, T, dcap, m, EXP, 40.0, act, fric,
    eod=True, mira=False, bloq_op=False, slipv=SLIP, cms=CMS)

CAMPOS = ('k', 'dx_puntos', 'hedge_dolares', 'comision', 'muere', 'pausa',
          'objetivo', 'barra_evento', 'bloqueo_k_menor_1')
motor = dict(k=k, dx_puntos=np.round(dx, 6), hedge_dolares=np.round(h, 4),
             comision=np.round(cst, 4), muere=muere, pausa=pausa, objetivo=tgt,
             barra_evento=ib, bloqueo_k_menor_1=bloq)

mal, ejemplos = 0, []
n_mu = n_bq = n_tg = 0
for i in range(N):
    e = dict(bal=float(bal[i]), pico=float(pk[i]), G=float(G[i]), H_hedge_acum=float(H[i]),
             friccion=float(fric[i]), m=float(m[i]), EXP=float(EXP[i]), T=float(T[i]),
             dcap=float(dcap[i]), kcap=40.0, barra_inicio=int(b0[i]), NB=NB,
             CMS=CMS, deslizamiento=SLIP, fsuelo=1.0,
             camino=dict(p0=0.0, tramos=[]))
    # el nucleo construye el camino desde tramos; aqui se lo inyectamos ya construido
    NR_ph, NR_pl, NR_pc = list(ph[i]), list(pl[i]), list(pc[i])
    _orig = NR.barras_desde_tramos
    NR.barras_desde_tramos = lambda *a, **kw: (NR_ph, NR_pl, NR_pc)
    try:
        r = NR.resolver_sesion(e)
    finally:
        NR.barras_desde_tramos = _orig
    dif = []
    for c in CAMPOS:
        a, b_ = r[c], motor[c][i]
        d = abs(float(a) - float(b_)) > 1e-6 if not isinstance(a, bool) else bool(a) != bool(b_)
        if d: dif.append(f"{c}: nucleo {a} motor {b_}")
    n_mu += bool(r['muere']); n_bq += bool(r['bloqueo_k_menor_1']); n_tg += bool(r['objetivo'])
    if dif:
        mal += 1
        if len(ejemplos) < 5: ejemplos.append((i, dif))

print(f"estados comparados: {N}")
print(f"  muertes ejercitadas   : {n_mu}")
print(f"  bloqueos ejercitados  : {n_bq}")
print(f"  objetivos ejercitados : {n_tg}")
print(f"  discrepancias nucleo-vs-motor: {mal}")
for i, dif in ejemplos:
    print(f"    estado {i}: " + " · ".join(dif))
if n_mu == 0 or n_bq == 0 or n_tg == 0:
    print("ERROR: el muestreo no ejercita alguna rama; la prueba no vale")
    sys.exit(1)
# --- R3: la prueba tiene que saber romperse -------------------------------------------
# se rompe el nucleo en memoria (look-ahead) y se exige que aparezcan discrepancias
_src = open(os.path.join(_AQUI, 'nucleo_referencia_v10.py')).read()
assert "for b in range(b0 + 1, NB):" in _src
import types
_roto = types.ModuleType('nucleo_roto')
exec(compile(_src.replace("for b in range(b0 + 1, NB):", "for b in range(b0, NB):", 1),
             '<roto>', 'exec'), _roto.__dict__)
_dif = 0
for i in range(min(N, 3000)):
    e = dict(bal=float(bal[i]), pico=float(pk[i]), G=float(G[i]), H_hedge_acum=float(H[i]),
             friccion=float(fric[i]), m=float(m[i]), EXP=float(EXP[i]), T=float(T[i]),
             dcap=float(dcap[i]), kcap=40.0, barra_inicio=int(b0[i]), NB=NB,
             CMS=CMS, deslizamiento=SLIP, fsuelo=1.0, camino=dict(p0=0.0, tramos=[]))
    NR_ph, NR_pl, NR_pc = list(ph[i]), list(pl[i]), list(pc[i])
    _roto.barras_desde_tramos = lambda *a, **kw: (NR_ph, NR_pl, NR_pc)
    r = _roto.resolver_sesion(e)
    if any((abs(float(r[c]) - float(motor[c][i])) > 1e-6 if not isinstance(r[c], bool)
            else bool(r[c]) != bool(motor[c][i])) for c in CAMPOS):
        _dif += 1
print(f"  auto-verificacion (nucleo roto con look-ahead): {_dif} discrepancias "
      f"sobre {min(N, 3000)} estados " + ("OK" if _dif else "ERROR: NO DETECTADO"))

print("EQUIVALENCIA: " + ("OK" if mal == 0 and _dif > 0 else "FALLA"))
sys.exit(0 if (mal == 0 and _dif > 0) else 1)
