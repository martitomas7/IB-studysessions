# -*- coding: utf-8 -*-
"""Genera la TABLA DE ESTRES completa de v10.1 con 8 semillas y su desviacion, y la
curva de exposicion a la contraparte.  Escribe estres_v10.json.  Uso: python estres_v10.py
Existe para que ninguna fila de la certificacion salga de una ejecucion no trazable."""
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
import pipeline3 as P3
V10 = dict(E=1, m_eval=2., exp_eval=1110., m_fun=4., exp_fun=1480., b_eval=40., b_fun=70.,
           pool=2, qcap=3, qcap_tes=10000., retencion=6860., emerg=True, empalme=True,
           dormidas_ini=0, eod=True, cal_rth=(0.18, 62, 40.), cms=1.90, nb_use=86,
           relevo=0, slip_micro=2.5, holg=6134.114 - 2830)
SE = (3, 5, 7, 11, 13, 17, 19, 23)
def med(**x):
    v = np.array([[(r := P3.corre(R=3000, DIAS=252, **{**V10, **x}, seed=s, crono=True))['jmes'],
                   r['p5'], r['parada_dyn']] for s in SE])
    return dict(jmes=float(v[:, 0].mean()), jmes_sd=float(v[:, 0].std(ddof=1)),
                p5=float(v[:, 1].mean()), pd=float(100 * v[:, 2].mean()),
                pd_sd=float(100 * v[:, 2].std(ddof=1)))
EJES = [('base', {}),
        ('desliz_ambar_25', dict(slip_micro=6.25)), ('desliz_rojo_50', dict(slip_micro=12.5)),
        ('relevo_D2', dict(relevo=1)), ('relevo_D3', dict(relevo=2)),
        ('cuota_100', dict(cuota=100.)), ('cuota_125_catalogo', dict(cuota=125.)),
        ('cuota_153', dict(cuota=153.)),
        ('margen_150', dict(cal_rth=(0.18, 62, 150.), holg=6134.114 - (4*150+1480+2*150+1110))),
        ('resets_mitad', dict(reset_p=1/60.)),
        ('sin_contra', dict(contra_dias=0)), ('sin_empalme', dict(empalme=False)),
        ('sin_contra_ni_empalme', dict(contra_dias=0, empalme=False)),
        ('SPR4_pesimista', dict(SPR=4.0)), ('SPR41_un_cruce_por_pata', dict(SPR=4.1)),
        ('SPR5', dict(SPR=5.0)), ('SPR6', dict(SPR=6.0)),
        ('comb_cuota100_ambar_D2', dict(cuota=100., slip_micro=6.25, relevo=1)),
        ('comb_SPR41_ambar_D2', dict(SPR=4.1, slip_micro=6.25, relevo=1)),
        ('comb_SPR41_cuota100_ambar_D2', dict(SPR=4.1, cuota=100., slip_micro=6.25, relevo=1)),
        ('todo_mal', dict(SPR=4.0, slip_micro=6.25, relevo=1, cuota=90., reset_p=1/60.,
                          contra_dias=0, empalme=False)),
        # --- EJE NUEVO (19-08): el proveedor CAMBIA LAS REGLAS sin cancelar.
        #     Sus Terminos permiten «unilaterally amend, modify, or update these Terms».
        ('regla_retiro_1500', dict(w_bruto=1500.)),
        ('regla_retiro_1000', dict(w_bruto=1000.)),
        ('regla_primer_retiro_1000', dict(w1=1000.)),
        ('regla_split_70_30', dict(split=0.70)),
        ('regla_ciclos_3', dict(nciclos=3)),
        ('regla_ciclos_2', dict(nciclos=2)),
        ('regla_sin_reset_gratis', dict(reset_p=1e-9)),
        ('regla_buffer_3000', dict(buf=3000.)),
        ('regla_objetivo_eval_4000', dict(t_eval=4000.)),
        ('regla_MLL_1500', dict(mll=1500.)),
        ('regla_DLL_750', dict(dll=750.)),
        ('regla_kcap_20', dict(kcap_p=20.)),
        ('regla_retiro1500_y_ciclos3', dict(w_bruto=1500., nciclos=3))]
out = dict(semillas=list(SE), R=3000, DIAS=252, filas={})
base = None
print(f"{'eje':34s}{'EV':>7}{'sd':>6}{'p5':>7}{'P(degradar)':>13}{'sd':>6}{'':>4}")
for nom, x in EJES:
    r = med(**x); out['filas'][nom] = r
    if nom == 'base': base = r
    if nom != 'base':      # anti-no-op: la fila debe mover ALGUNA metrica
        _mueve = (abs(r['jmes'] - base['jmes']) > 1e-9 or abs(r['pd'] - base['pd']) > 1e-9
                  or abs(r['p5'] - base['p5']) > 1e-9)
        assert _mueve, f"NO-OP: la fila {nom} es identica a la base"
    print(f"{nom:34s}{r['jmes']:7.0f}{r['jmes_sd']:6.1f}{r['p5']:7.0f}{r['pd']:12.2f}%"
          f"{r['pd_sd']:6.2f}{'  X' if r['pd'] > 5 else '  ok'}")
# exposicion a la contraparte: caja acumulada por mes
M = [P3.corre(R=3000, DIAS=252, **V10, seed=s, crono=True)['meses'] for s in SE]
out['exposicion'] = {k: [float(v) for v in np.mean([m[k] for m in M], axis=0)]
                     for k in ('p5', 'p50', 'media')}
json.dump(out, open(os.path.join(_LAB, 'estres_v10.json'), 'w'), indent=1)
print("\nexposicion (caja acumulada a fin de mes, 8 semillas):")
print("  mes " + "".join(f"{i:7d}" for i in range(1, 13)))
for k in ('p5', 'p50'):
    print(f"  {k:4s}" + "".join(f"{v:7.0f}" for v in out['exposicion'][k]))
# --- EMITIR LA TABLA DEL DOCUMENTO DESDE EL JSON (estructural: no se escribe a mano) ---
ET = {'base':'**base**','desliz_ambar_25':'deslizamiento ámbar (25 $/muerte)',
 'desliz_rojo_50':'deslizamiento ROJO (50 $/muerte)','relevo_D2':'relevo D+2 (fallas la activación)',
 'relevo_D3':'relevo D+3 (fallas dos noches)','cuota_100':'cuota 100 $',
 'cuota_125_catalogo':'**cuota 125 $ (precio de CATÁLOGO)**','cuota_153':'cuota 153 $',
 'margen_150':'margen del bróker 150 $/micro','resets_mitad':'resets a la mitad',
 'sin_contra':'sin contra','sin_empalme':'sin empalme','sin_contra_ni_empalme':'sin contra NI empalme',
 'SPR4_pesimista':'fricción SPR=4 (pesimista)','SPR41_un_cruce_por_pata':'**fricción SPR=4,1** (1 tick por PATA)',
 'SPR5':'**fricción SPR=5**','SPR6':'fricción SPR=6',
 'comb_cuota100_ambar_D2':'cuota 100 + ámbar + D+2','comb_SPR41_ambar_D2':'SPR 4,1 + ámbar + D+2',
 'comb_SPR41_cuota100_ambar_D2':'**SPR 4,1 + cuota 100 + ámbar + D+2**',
 'todo_mal':'**TODO MAL a la vez**',
 'regla_retiro_1500':'REGLA: tope de retiro 1.500 $','regla_retiro_1000':'REGLA: tope de retiro 1.000 $',
 'regla_primer_retiro_1000':'REGLA: primer retiro 1.000 $','regla_split_70_30':'REGLA: split 70/30',
 'regla_ciclos_3':'REGLA: 3 ciclos','regla_ciclos_2':'REGLA: 2 ciclos',
 'regla_sin_reset_gratis':'REGLA: sin reset gratis','regla_buffer_3000':'REGLA: buffer 3.000 $',
 'regla_objetivo_eval_4000':'REGLA: objetivo eval 4.000 $','regla_MLL_1500':'**REGLA: MLL 1.500 $**',
 'regla_DLL_750':'**REGLA: DLL 750 $**','regla_kcap_20':'REGLA: kcap 20 contratos',
 'regla_retiro1500_y_ciclos3':'REGLA: retiro 1.500 + 3 ciclos'}
L = ["| eje estresado | EV $/mes | sd | p5 | P(degradar) | sd | |",
     "|---|---|---|---|---|---|---|"]
for nom, r in out['filas'].items():
    ok = '' if nom == 'base' else ('❌' if r['pd'] > 5 else '✅')
    L.append(f"| {ET.get(nom,nom)} | {r['jmes']:,.0f} | {r['jmes_sd']:.1f} | {r['p5']:,.0f} | "
             f"{r['pd']:.2f} % | {r['pd_sd']:.2f} | {ok} |".replace(',', '.'))
tabla = "\n".join(L)
doc = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'CONSOLIDACION_v10.md')
for cand in (doc, os.path.join(_LAB, '..', 'CONSOLIDACION_v10.md'), 'CONSOLIDACION_v10.md'):
    if os.path.exists(cand):
        t = open(cand).read()
        A, B = '<!-- TABLA_ESTRES:INICIO -->', '<!-- TABLA_ESTRES:FIN -->'
        if A in t and B in t:
            t = t[:t.index(A)+len(A)] + "\n" + tabla + "\n" + t[t.index(B):]
            open(cand, 'w').write(t)
            print(f"tabla del documento REGENERADA desde el JSON en {os.path.basename(cand)}")
        break
open(os.path.join(_LAB, 'TABLA_ESTRES.md'), 'w').write(tabla + "\n")
print("\nestres_v10.json + TABLA_ESTRES.md escritos")
