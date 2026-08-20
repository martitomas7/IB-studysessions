# -*- coding: utf-8 -*-
"""REPLAY PACK v10 · traza dia a dia del motor congelado para validar el ORQUESTADOR
del bot sin brokers.  A diferencia del pack de v8 -que era solo una traza-, este incluye
INVARIANTES DE ORQUESTADOR por dia: el numero de sesiones por cuenta, la perdida diaria
maxima por cuenta, el hueco de relevo y el estado del pool.  Esos son los que habrian
cazado el bug de la doble sesion, que ningun golden puede ver.
Uso: python replay_v10.py   ->  replay_v10.json
"""
import os, sys, json
import numpy as np
_LAB = os.environ.get("LAB_DIR") or next((c for c in (
    os.path.dirname(os.path.abspath(__file__)),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelo"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "modelo"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "lab"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lab"),
    "/root/work/bot/lab") if os.path.exists(os.path.join(c, "pipeline3.py"))), None)
assert _LAB, "no encuentro pipeline3.py: usa LAB_DIR"
_LAB = os.path.abspath(_LAB)
sys.path.insert(0, _LAB)
src = open(os.path.join(_LAB, 'pipeline3.py')).read().replace(
    "os.path.dirname(os.path.abspath(__file__))", repr(_LAB))

SNAP = """
        T.append(dict(t=t, j=int(j if np.isscalar(j) else j[0]), dir=int(sdir[0]),
            caja=float(caja[0]), ret=float(ret[0]), fees=float(fees[0]),
            f_act=bool(f_act[0]), f_fase=int(f_fase[0]), f_bal=float(f_bal[0]),
            f_pk=float(f_pk[0]), f_H=float(f_H[0]), f_s0=float(f_s0[0]),
            f_nd=int(f_nd[0]), f_espera=int(f_espera[0]),
            e_act=bool(e_act[0,0]) if E>0 else False,
            e_bal=float(e_bal[0,0]) if E>0 else 0.0,
            e_H=float(e_H[0,0]) if E>0 else 0.0,
            e_s0=float(e_s0[0,0]) if E>0 else 0.0,
            d_n=int(d_n[0]), d_sunk=float(d_sunk[0]),
            fresh=int(fresh[0]), broken=int(broken[0]),
            n_att=float(n_att[0]), n_apr=float(n_apr[0]), n_fd=float(n_fd[0]),
            n_reset=float(n_reset[0]), n_emerg=float(n_emerg[0]), n_rebuy=float(n_rebuy[0]),
            ses_eval=int(SES[0]), emp=int(EMP[0]), rth=bool(b0v[0] > 0),
            peor_dia_eval=float(PDE[0]), peor_dia_fun=float(PDF[0]), bqf=int(BQF[0])))
        minc = np.minimum(minc, caja)"""
src = src.replace("        minc = np.minimum(minc, caja)", SNAP, 1)
# contadores por dia
src = src.replace("            frv = SPR * mv\n            _opera",
                  "            frv = SPR * mv\n            SES[:]=0; EMP[:]=0; PDE[:]=0.0\n            _opera", 1)
src = src.replace("                caja += np.where(act, h, 0.0)",
                  "                SES += act.astype(int)\n"
                  "                PDE = np.minimum(PDE, np.where(act, dx*5*k-cst, 0.0))\n"
                  "                caja += np.where(act, h, 0.0)", 1)
src = src.replace("                    n_att += rearr", "                    n_att += rearr\n                    EMP += rearr.astype(int)", 1)
src = src.replace("            f_act = f_act & ~mu & ~bq",
                  "            BQF[:] = bq.astype(int)\n            f_act = f_act & ~mu & ~bq", 1)
assert "BQF[:] = bq" in src, "el parche de BQF no se aplico"
src = src.replace("            caja += np.where(fa, h, 0.0)",
                  "            PDF[:] = np.where(fa, dx*5*k-cst, 0.0)\n            caja += np.where(fa, h, 0.0)", 1)
src = src.replace("    caja = np.zeros(R)",
                  "    SES=np.zeros(R,int); EMP=np.zeros(R,int); BQF=np.zeros(R,int)\n"
                  "    PDE=np.zeros(R); PDF=np.zeros(R)\n    caja = np.zeros(R)", 1)
ns = {'__name__': 'rp', 'T': []}
exec(compile(src, 'rp', 'exec'), ns)
T = ns['T']

CFG = dict(R=1, DIAS=504, E=1, m_eval=2., exp_eval=1110., m_fun=4., exp_fun=1480.,
           b_eval=40., b_fun=70., pool=2, qcap=3, qcap_tes=10000., retencion=6860.,
           emerg=True, empalme=True, dormidas_ini=0, eod=True, cal_rth=(0.18, 62, 40.),
           cms=1.90, nb_use=86, relevo=0, slip_micro=2.5, holg=6134.114 - 2830, seed=14)
res = ns['corre'](**CFG)
PH, PL, PC = ns['PH'], ns['PL'], ns['PC']
NB = 86
dias, prev = [], dict(fees=0., n_att=0., n_apr=0., n_fd=0., n_reset=0., n_emerg=0., n_rebuy=0.)
for i, s in enumerate(T):
    j = s['j']
    ev = {k: round(s['n_' + k[:5] if k != 'cuotas' else 'fees'] - prev['n_' + k[:5] if k != 'cuotas' else 'fees'], 4)
          for k in ()}  # placeholder
    ev = dict(intentos=round(s['n_att'] - prev['n_att']), aprobaciones=round(s['n_apr'] - prev['n_apr']),
              muertes_funded=round(s['n_fd'] - prev['n_fd']), resets=round(s['n_reset'] - prev['n_reset']),
              emergencias=round(s['n_emerg'] - prev['n_emerg']), recompras=round(s['n_rebuy'] - prev['n_rebuy']),
              cuotas_dia=round(s['fees'] - prev['fees'], 4))
    prev = {k: s[k] for k in prev}
    dias.append(dict(
        dia=s['t'] + 1, direccion=s['dir'], ventana='RTH' if s['rth'] else '22h',
        barras=dict(ph=[round(x, 2) for x in PH[j][:NB]], pl=[round(x, 2) for x in PL[j][:NB]],
                    pc=[round(x, 2) for x in PC[j][:NB]]),
        eventos=ev,
        invariantes=dict(sesiones_de_eval=s['ses_eval'], empalmes=s['emp'],
                         peor_dia_una_cuenta_eval=round(s['peor_dia_eval'], 4),
                         peor_dia_funded=round(s['peor_dia_fun'], 4),
                         bloqueo_funded=s['bqf']),
        fin_de_dia=dict(caja=round(s['caja'], 4), retirado=round(s['ret'], 2),
                        funded=dict(activa=s['f_act'], fase=s['f_fase'], bal=round(s['f_bal'], 4),
                                    pico=round(s['f_pk'], 4), H=round(s['f_H'], 4),
                                    s0=round(s['f_s0'], 4), dias=s['f_nd'], espera=s['f_espera']),
                        eval=dict(activa=s['e_act'], bal=round(s['e_bal'], 4), H=round(s['e_H'], 4),
                                  s0=round(s['e_s0'], 4)),
                        recamara=dict(n=s['d_n'], sunk_total=round(s['d_sunk'], 4)),
                        pool=dict(frescas=s['fresh'], rotas=s['broken']))))
INV = dict(
  sesiones_por_cuenta_y_dia="<= 1.  Dos sesiones el mismo dia solo pueden ser cuentas DISTINTAS "
      "(la muerta y su empalme).  El campo `sesiones_de_eval` cuenta SESIONES, no cuentas: "
      "vale 2 solo si `empalmes`=1.  ESTE es el invariante que caza el bug de v8.",
  perdida_diaria_por_cuenta="ninguna cuenta pierde mas que DLL + comision en un dia natural "
      "(con k<=40 el tope es 1.000 + 1,90*40 = 1.076,00 $)",
  empalmes_por_dia="<= 1",
  relevo_de_dormida="tras una muerte de la funded, la siguiente sesion funded ocurre en el "
      "siguiente dia de negociacion (regla escrita del proveedor)",
  bloqueo_regla_4_3="si `bloqueo_funded`=1 ese dia la cuenta NO opera: la caja no cambia "
      "por su hedge, el balance no se mueve y no hay comision",
  qcap="el slot de eval no abre intentos nuevos con >= qcap dormidas, salvo tesoreria viva >= qcap_tes",
  pool="frescas + rotas + operando + aprobadas_del_mes debe cuadrar con las compras registradas")
COB = {}
for d in dias:
    COB.setdefault('fase_' + str(d['fin_de_dia']['funded']['fase']), 0)
    COB['fase_' + str(d['fin_de_dia']['funded']['fase'])] += 1
for k, c in (('empalme', lambda d: d['invariantes']['empalmes']),
             ('bloqueo_regla_4_3', lambda d: d['invariantes']['bloqueo_funded']),
             ('aprobacion', lambda d: d['eventos']['aprobaciones']),
             ('muerte_funded', lambda d: d['eventos']['muertes_funded']),
             ('emergencia', lambda d: d['eventos']['emergencias']),
             ('reset_gratis', lambda d: d['eventos']['resets']),
             ('recompra', lambda d: d['eventos']['recompras']),
             ('ventana_RTH', lambda d: 1 if d['ventana'] == 'RTH' else 0),
             ('direccion_corta', lambda d: 1 if d['direccion'] < 0 else 0)):
    COB[k] = sum(c(d) for d in dias)
assert COB.get('fase_5', 0) > 0, "la traza no visita la FASE 5: esa rama quedaria sin cubrir"
assert COB['bloqueo_regla_4_3'] > 0, "la traza no contiene ningun bloqueo"
out = dict(version="replay pack v10 · 19-08-2026",
  descripcion="Traza dia a dia del motor congelado v10 (504 dias, semilla 14, arranque frio). "
      "La semilla 14 y los 504 dias se eligen DELIBERADAMENTE: cubren a la vez el evento de "
      "BLOQUEO de la Regla 4.3 (raro: 5 de 80 semillas en 252 dias) y la FASE 5 de la funded "
      "-el 5o cobro, que cierra el linaje sin muerte por una rama de codigo distinta-. "
      "El orquestador del bot debe reproducir `fin_de_dia` EXACTO (tolerancia 1e-3 $) forzando "
      "la direccion, la ventana, los resets y las barras dadas; y debe cumplir `invariantes` "
      "en TODOS los dias.",
  convencion=dict(
      barras=f"{NB} barras de 15 min en el eje REAL del indice (campana T-20 ya aplicada); "
             "si direccion=-1 el bot opera corto (equivale al reflejo p->2*p0-p)",
      direccion="FORZARLA, no sortear", ventana="FORZARLA", resets="forzar los del dia",
      arranque="todo a cero, pool 2 frescas, recamara vacia", config=CFG),
  invariantes_de_orquestador=INV,
  resultado_global=dict(caja_final=round(float(T[-1]['caja']), 2), dias=len(dias)),
  cobertura_de_rama=COB,
  dias=dias)
_SAL = os.path.dirname(os.path.abspath(__file__))   # la traza vive junto a su runner
json.dump(out, open(os.path.join(_SAL, 'replay_v10.json'), 'w'), indent=1)
kb = os.path.getsize(os.path.join(_SAL, 'replay_v10.json')) / 1024
ses = [d['invariantes']['sesiones_de_eval'] for d in dias]
emp = [d['invariantes']['empalmes'] for d in dias]
peor = min(min(d['invariantes']['peor_dia_una_cuenta_eval'] for d in dias),
           min(d['invariantes']['peor_dia_funded'] for d in dias))
print(f"replay_v10.json: {len(dias)} dias, {kb:,.0f} KB, caja final {out['resultado_global']['caja_final']:,.2f} $")
print(f"  sesiones de eval/dia: max {max(ses)} · dias con 2 sesiones {sum(1 for x in ses if x==2)} "
      f"· empalmes totales {sum(emp)}  -> coinciden: {sum(1 for x in ses if x==2)==sum(emp)}")
print(f"  peor perdida de UNA cuenta en un dia: {peor:,.2f} $  (tope 1.076,00)")
print("  cobertura de rama: " + " · ".join(f"{k}={v}" for k,v in sorted(COB.items())))
nb = sum(d["invariantes"]["bloqueo_funded"] for d in dias)
assert nb > 0, "la traza no contiene ningun bloqueo: la rama de la Regla 4.3 quedaria sin cubrir"
print(f"  bloqueos de la regla 4.3 en la traza: {sum(d['invariantes']['bloqueo_funded'] for d in dias)}")
print(f"  eventos: {sum(d['eventos']['intentos'] for d in dias)} intentos · "
      f"{sum(d['eventos']['aprobaciones'] for d in dias)} aprobaciones · "
      f"{sum(d['eventos']['muertes_funded'] for d in dias)} muertes funded")
