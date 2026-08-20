# -*- coding: utf-8 -*-
"""GENERADOR DE LAS CIFRAS QUE LA NORMA CITA.

Existe porque una auditoria externa senalo, con razon, que siete cifras citadas en
01_ESPECIFICACION_E2E.md y 04_GUARDARRAILES no eran reproducibles con nada que el paquete
enviara.  Este script las produce, TODAS, sobre la config congelada v10 y con el motor que
viaja en modelo/.  Escribe cifras_citadas.json.

Lo que NO hace: inventar.  Si una cifra historica se midio sobre otra configuracion, este
script mide la que corresponde a v10 y lo dice; no reescribe la historica.

Uso:  python modelo/cifras_citadas.py            (tarda ~3 min)
"""
import os, sys, json
import numpy as np

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
import pipeline3 as P3

V10 = dict(E=1, m_eval=2., exp_eval=1110., m_fun=4., exp_fun=1480., b_eval=40., b_fun=70.,
           pool=2, qcap=3, qcap_tes=10000., retencion=6860., emerg=True, empalme=True,
           dormidas_ini=0, eod=True, cal_rth=(0.18, 62, 40.), cms=1.90, nb_use=86,
           relevo=0, slip_micro=2.5, holg=6134.114 - 2830)
SE = (3, 5, 7, 11, 13, 17, 19, 23)
R, DIAS = 3000, 252
out = {}


def med(**x):
    """Media sobre las 8 semillas, escenario crono, igual que estres_v10.py."""
    v = np.array([[(r := P3.corre(R=R, DIAS=DIAS, **{**V10, **x}, seed=s, crono=True))['jmes'],
                   r['p5'], r['parada_dyn']] for s in SE])
    return dict(jmes=float(v[:, 0].mean()), p5=float(v[:, 1].mean()),
                pd=float(100 * v[:, 2].mean()))


# =============================================================================
# 1 · LA IDENTIDAD DE COBERTURA, medida sobre el motor
#     Afirmacion auditada: "0 fallos en 20.179 muertes sobre 600.000 estados" (sin
#     deslizamiento) y "el 0,65 % de las muertes cierra con deficit" (con el).
# =============================================================================
BASE = open(os.path.join(_AQUI, 'pipeline3.py')).read().replace(
    "os.path.dirname(os.path.abspath(__file__))", repr(_AQUI))

# instrumentacion: en cada muerte apunta el deficit  (G - H) - h  y el P&L del hedge
INSTR = [
    ("    caja = np.zeros(R)",
     "    DEF=[]; NMU=[0]; NEST=[0]; WTOT=np.zeros(R); HTOT=np.zeros(R)\n    caja = np.zeros(R)"),
    ("            caja += np.where(fa, h, 0.0)",
     "            NEST[0]+=int(fa.sum()); NMU[0]+=int((mu&fa).sum())\n"
     "            _d=(G-f_H)-h\n"
     "            DEF.append(_d[mu&fa].copy())\n"
     "            HTOT += np.where(fa, h, 0.0)\n"
     "            caja += np.where(fa, h, 0.0)"),
    ("                caja += np.where(act, h, 0.0)",
     "                NEST[0]+=int(act.sum()); NMU[0]+=int((mu&act).sum())\n"
     "                _d=(G-e_H[:, s])-h\n"
     "                DEF.append(_d[mu&act].copy())\n"
     "                HTOT += np.where(act, h, 0.0)\n"
     "                caja += np.where(act, h, 0.0)"),
    ("                caja += np.where(pasa, Wv, 0.0)",
     "                WTOT += np.where(pasa, Wv, 0.0)\n                caja += np.where(pasa, Wv, 0.0)"),
]


def motor_instrumentado():
    s = BASE
    for viejo, nuevo in INSTR:
        assert viejo in s, viejo[:50]
        s = s.replace(viejo, nuevo, 1)
    # exponer los acumuladores en el dict de salida
    s = s.replace("    jmes = caja / DIAS * 21.0\n    return dict(",
                  "    jmes = caja / DIAS * 21.0\n    return dict(_def=DEF, _nmu=NMU[0], "
                  "_nest=NEST[0], _wtot=WTOT, _htot=HTOT, _caja=caja, _fees=fees, ", 1)
    assert "_def=DEF" in s
    ns = {'__name__': 'p3i'}
    exec(compile(s, 'p3i', 'exec'), ns)
    return ns


P3I = motor_instrumentado()


def identidad(slip):
    r = P3I['corre'](R=500, DIAS=252, **{**V10, 'slip_micro': slip}, seed=7, crono=True)
    d = np.concatenate([x for x in r['_def'] if len(x)]) if r['_nmu'] else np.zeros(0)
    # deficit > 0  =>  el hedge NO llego a cubrir G - H  =>  el linaje cierra por debajo de B
    mal = d[d > 1e-9]
    return dict(estados=int(r['_nest']), muertes=int(r['_nmu']),
                con_deficit=int(mal.size),
                pct_deficit=float(100.0 * mal.size / max(r['_nmu'], 1)),
                deficit_mediana=float(np.median(mal)) if mal.size else 0.0,
                deficit_peor=float(mal.max()) if mal.size else 0.0)


print("1 · identidad de cobertura ...")
out['identidad'] = {
    'sin_deslizamiento':      identidad(0.0),
    'deslizamiento_v10_2_50': identidad(2.5),
    'deslizamiento_ambar_6_25': identidad(6.25),
    'deslizamiento_rojo_12_50': identidad(12.5),
}
for k, v in out['identidad'].items():
    print(f"   {k:26} {v['muertes']:6d} muertes / {v['estados']:7d} estados · "
          f"con deficit {v['con_deficit']:5d} ({v['pct_deficit']:.2f} %) · "
          f"mediana {v['deficit_mediana']:.2f} $ · peor {v['deficit_peor']:.2f} $")

# =============================================================================
# 2 · EL LIBRO DEL HEDGE  (payouts cobrados, cuotas pagadas, P&L del hedge)
#     Afirmacion auditada: "pago ~2.099 y recupero ~1.983" -- se midio sobre v9.1.
#     Aqui se mide sobre v10.
# =============================================================================
print("2 · libro del hedge (config v10) ...")
r = P3I['corre'](R=3000, DIAS=DIAS, **V10, seed=7, crono=True)
f = 21.0 / DIAS
out['libro_hedge_v10'] = dict(
    payouts_cobrados=float(r['_wtot'].mean() * f),
    cuotas_pagadas=float(r['_fees'].mean() * f),
    pl_hedge=float(r['_htot'].mean() * f),
    caja=float(r['_caja'].mean() * f),
    cuadre=float((r['_htot'] + r['_wtot'] - r['_fees'] - r['_caja']).mean() * f))
L = out['libro_hedge_v10']
print(f"   payouts +{L['payouts_cobrados']:.0f} · cuotas -{L['cuotas_pagadas']:.0f} · "
      f"hedge {L['pl_hedge']:+.0f} · caja {L['caja']:.0f} $/mes · "
      f"residuo del cuadre {L['cuadre']:.4f}")

# =============================================================================
# 3 · EL EXPERIMENTO DEL BUFFER CONDICIONAL (b_cond)
#     Afirmacion auditada: "1.194 -> 946 $/mes, P(degradar) 24,53 %"
# =============================================================================
print("3 · buffer condicional (soltar B los dias en que la muerte es imposible) ...")
out['b_cond'] = dict(base=med(), soltando_B=med(b_cond=1.0))
b, c = out['b_cond']['base'], out['b_cond']['soltando_B']
print(f"   base {b['jmes']:.0f} $/mes · P {b['pd']:.2f} %   ->   "
      f"soltando B {c['jmes']:.0f} $/mes · P {c['pd']:.2f} %")

# =============================================================================
# 4 · EL COSTE DE LOS DOS BUGS HISTORICOS, sobre la config v10
#     Afirmacion auditada: "-32,5 % (doble sesion)" y "-13,6 % (look-ahead)".
#     Esas dos se midieron sobre la config de v8.  Aqui se mide v10.
# =============================================================================
print("4 · coste de los dos bugs, sobre la config v10 ...")
out['bugs_sobre_v10'] = dict(
    base=out['b_cond']['base'],
    doble_sesion=med(doble=True),
    look_ahead=med(mira_atras=True),
    los_dos=med(doble=True, mira_atras=True))
for k in ('doble_sesion', 'look_ahead', 'los_dos'):
    v = out['bugs_sobre_v10'][k]
    d = 100.0 * (v['jmes'] - b['jmes']) / b['jmes']
    out['bugs_sobre_v10'][k]['delta_pct'] = float(d)
    print(f"   {k:14} {v['jmes']:7.0f} $/mes ({d:+.1f} % vs base) · P {v['pd']:.2f} %")

# =============================================================================
# 5 · LA CAMPANA:  cuantas barras se dejan de operar
# =============================================================================
out['campana'] = dict(barras_totales=int(P3.NB), barras_operadas=int(V10['nb_use']),
                      minutos_por_barra=15,
                      minutos_sin_operar=int((P3.NB - V10['nb_use']) * 15))
print(f"5 · campana: {V10['nb_use']} de {P3.NB} barras -> se dejan de operar "
      f"{out['campana']['minutos_sin_operar']} min al final de la sesion")

# =============================================================================
# 6 · LA HOLGURA DE LA IDENTIDAD, Y QUE SIGNIFICA DE VERDAD UN "DEFICIT"
#     El indicador "% de muertes con deficit > 0" es engañoso: la holgura esta
#     CUANTIZADA (k es entero), asi que ese porcentaje es una funcion escalon sin
#     contenido economico.  Lo que importa es (a) cuanto se come el deslizamiento
#     del buffer B, y (b) si algun linaje llega a cerrar en NEGATIVO.
# =============================================================================
INSTR2 = [
    ("    caja = np.zeros(R)", "    HOL=[]; BB=[]; TIPO=[]\n    caja = np.zeros(R)"),
    ("            caja += np.where(fa, h, 0.0)",
     "            _hol=(h + (slip_fijo+slip_micro*m_fun)) - (G-f_H)\n"
     "            _n=int((mu&fa).sum())\n"
     "            HOL.append(_hol[mu&fa].copy()); BB.append(np.full(_n, Bf)); TIPO.append(np.ones(_n))\n"
     "            caja += np.where(fa, h, 0.0)"),
    ("                caja += np.where(act, h, 0.0)",
     "                _hol=(h + (slip_fijo+slip_micro*mv)) - (G-e_H[:, s])\n"
     "                _n=int((mu&act).sum())\n"
     "                HOL.append(_hol[mu&act].copy()); BB.append(np.full(_n, Be)); TIPO.append(np.zeros(_n))\n"
     "                caja += np.where(act, h, 0.0)")]


def motor_holgura():
    s2 = BASE
    for viejo, nuevo in INSTR2:
        assert viejo in s2, viejo[:50]
        s2 = s2.replace(viejo, nuevo, 1)
    s2 = s2.replace("    jmes = caja / DIAS * 21.0\n    return dict(",
                    "    jmes = caja / DIAS * 21.0\n    return dict(_hol=HOL,_bb=BB,_tipo=TIPO, ", 1)
    ns2 = {'__name__': 'p3h'}
    exec(compile(s2, 'p3h', 'exec'), ns2)
    return ns2


print("6 · holgura de la identidad y significado del deficit ...")
P3H = motor_holgura()
rh = P3H['corre'](R=600, DIAS=DIAS, **V10, seed=7, crono=True)
hol = np.concatenate([x for x in rh['_hol'] if len(x)])
bb = np.concatenate([x for x in rh['_bb'] if len(x)])
tp = np.concatenate([x for x in rh['_tipo'] if len(x)])
out['holgura'] = dict(
    muertes=int(hol.size), muertes_eval=int((tp == 0).sum()), muertes_funded=int((tp == 1).sum()),
    b_eval=float(bb[tp == 0][0]), b_funded=float(bb[tp == 1][0]),
    percentiles={nom: {q: float(np.percentile(hol[msk], q)) for q in (0, 5, 25, 50, 75, 95)}
                 for nom, msk in (('todas', np.ones(hol.size, bool)),
                                  ('eval', tp == 0), ('funded', tp == 1))},
    bandas={})
for sm in (0.0, 2.5, 4.0, 5.0, 6.25, 12.5, 25.0):
    slip = np.where(tp == 1, sm * 4.0, sm * 2.0)
    defi = np.maximum(0.0, slip - hol)
    cierre = bb - defi
    out['holgura']['bandas'][f"{sm:.2f}"] = dict(
        slip_eval=sm * 2, slip_funded=sm * 4,
        pct_cierra_bajo_B=float(100 * (defi > 1e-9).mean()),
        deficit_medio=float(defi.mean()),
        deficit_pct_de_B=float(100 * defi.mean() / bb.mean()),
        pct_cierra_en_negativo=float(100 * (cierre < 0).mean()))
print(f"   holgura mediana: eval {np.median(hol[tp == 0]):.2f} $ · funded {np.median(hol[tp == 1]):.2f} $")
print(f"   {'slip $/micro':>12} {'% cierra <B':>12} {'deficit medio':>14} {'% de B':>8} {'% NEGATIVO':>12}")
for kb, vb in out['holgura']['bandas'].items():
    print(f"   {kb:>12} {vb['pct_cierra_bajo_B']:11.2f}% {vb['deficit_medio']:13.2f}$ "
          f"{vb['deficit_pct_de_B']:7.1f}% {vb['pct_cierra_en_negativo']:11.2f}%")

# el coste del deslizamiento en EV es slip x muertes: se comprueba contra la tabla de estres
rb = P3.corre(R=3000, DIAS=DIAS, **V10, seed=7, crono=True)
me, mf = rb['att'] - rb['apr'], rb['fdm']
out['coste_deslizamiento'] = dict(muertes_eval_mes=float(me), muertes_funded_mes=float(mf))
for nom, d in (('verde_a_ambar', 6.25 - 2.5), ('verde_a_rojo', 12.5 - 2.5)):
    out['coste_deslizamiento'][nom] = dict(predicho=float(me * d * 2 + mf * d * 4))
print(f"   muertes/mes: eval {me:.2f} · funded {mf:.2f}")
print(f"   coste VERDE->AMBAR predicho por slip x muertes = "
      f"{out['coste_deslizamiento']['verde_a_ambar']['predicho']:.1f} $/mes (tabla de estres: 116,0)")
print(f"   coste VERDE->ROJO  predicho por slip x muertes = "
      f"{out['coste_deslizamiento']['verde_a_rojo']['predicho']:.1f} $/mes (tabla de estres: 313,6)")

# =============================================================================
# 7 · LA PUERTA F3.1: donde se rompe el criterio pre-registrado P(degradar) <= 5 %
# =============================================================================
print("7 · puerta F3.1: barrido fino de la friccion ...")
out['puerta_f31'] = dict(criterio="P(degradar) <= 5 % (protocolo pre-registrado)", friccion={}, combinaciones={})
for spr in (3.0, 4.0, 4.1, 4.25, 4.5, 4.75, 5.0):
    v = med(SPR=spr)
    v['pasa'] = bool(v['pd'] <= 5.0)
    out['puerta_f31']['friccion'][f"{spr:.2f}"] = v
    print(f"   SPR {spr:4.2f}  EV {v['jmes']:7.1f} · p5 {v['p5']:7.1f} · P {v['pd']:5.2f} %  "
          f"{'PASA' if v['pasa'] else 'FALLA'}")
for nom, kw in (('spr410_slip_ambar', dict(SPR=4.1, slip_micro=6.25)),
                ('spr300_slip_rojo', dict(slip_micro=12.5)),
                ('spr410_slip_rojo', dict(SPR=4.1, slip_micro=12.5))):
    v = med(**kw); v['pasa'] = bool(v['pd'] <= 5.0)
    out['puerta_f31']['combinaciones'][nom] = v
    print(f"   {nom:20} EV {v['jmes']:7.1f} · p5 {v['p5']:7.1f} · P {v['pd']:5.2f} %  "
          f"{'PASA' if v['pasa'] else 'FALLA'}")

# =============================================================================
# 8 · TASAS DE EVENTO POR MES, con la agregacion CORRECTA de 8 semillas
#     Existe porque estres_v10.json solo publica jmes/p5/pd, y modelo_v10.json:esc.crono
#     es de UNA semilla (la cabecera de 03_CONFIG.yaml prohibe citarlo).  El laboratorio
#     (08_LABORATORIO, E6) necesita estas tasas como referencia y hasta ahora se citaban
#     sin fuente regenerable.  Esto lo cierra.
# =============================================================================
print("8 · tasas de evento por mes (8 semillas) ...")
_RS = [P3.corre(R=R, DIAS=DIAS, **V10, seed=s, crono=True) for s in SE]


def _agg(f):
    v = np.array([f(r) for r in _RS])
    return dict(por_mes=float(v.mean()), sd=float(v.std(ddof=1)))


out['tasas_evento_mes'] = {
    'intentos_eval':   _agg(lambda r: r['att']),
    'aprobaciones':    _agg(lambda r: r['apr']),
    'muertes_eval':    _agg(lambda r: r['att'] - r['apr']),
    'muertes_funded':  _agg(lambda r: r['fdm']),
    'muertes_totales': _agg(lambda r: r['att'] - r['apr'] + r['fdm']),
    'emergencias':     _agg(lambda r: r['emerg']),
    'recompras':       _agg(lambda r: r['rebuy']),
    'resets_gratis':   _agg(lambda r: r['reset']),
}
for _k, _v in out['tasas_evento_mes'].items():
    print(f"   {_k:18} {_v['por_mes']:8.3f} /mes  (sd {_v['sd']:.3f})")

json.dump(out, open(os.path.join(_AQUI, 'cifras_citadas.json'), 'w'), indent=1)
print("\ncifras_citadas.json escrito")
