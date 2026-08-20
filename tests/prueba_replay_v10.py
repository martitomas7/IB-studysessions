"""PRUEBA DE DISCRIMINACION del replay pack: orquestadores rotos a proposito."""
import json, sys, os
import numpy as np
_AQUI = os.path.dirname(os.path.abspath(__file__))
# LAB = donde vive pipeline3.py + motor_exp.py.  En el paquete de ingenieria es ../modelo;
# en el laboratorio original es /root/work/bot/lab.  Se puede forzar con LAB_DIR.
LAB = os.environ.get('LAB_DIR') or next((c for c in (
    os.path.join(_AQUI, '..', 'modelo'), os.path.join(_AQUI, 'modelo'),
    '/root/work/bot/lab') if os.path.exists(os.path.join(c, 'pipeline3.py'))), None)
assert LAB, "no encuentro pipeline3.py: pon LAB_DIR o coloca modelo/ junto a tests/"
LAB = os.path.abspath(LAB)
sys.path.insert(0, LAB)
BASE=open(LAB+'/pipeline3.py').read().replace("os.path.dirname(os.path.abspath(__file__))",repr(LAB))
SNAP="""
        T.append(dict(t=t, caja=float(caja[0]), f_bal=float(f_bal[0]), f_s0=float(f_s0[0]),
            e_bal=float(e_bal[0,0]) if E>0 else 0.0, d_n=int(d_n[0]),
            fresh=int(fresh[0]), broken=int(broken[0]), f_act=bool(f_act[0]),
            ses=int(SES[0]), emp=int(EMP[0]), pde=float(PDE[0]), pdf=float(PDF[0]), bqf=int(BQF[0]),
            mu_f=float(n_fd[0])))
        minc = np.minimum(minc, caja)"""
def motor(rot=None):
    s=BASE.replace("        minc = np.minimum(minc, caja)",SNAP,1)
    s=s.replace("            frv = SPR * mv\n            _opera","            frv = SPR * mv\n            SES[:]=0; EMP[:]=0; PDE[:]=0.0\n            _opera",1)
    s=s.replace("                caja += np.where(act, h, 0.0)","                SES += act.astype(int)\n                PDE = np.minimum(PDE, np.where(act, dx*5*k-cst, 0.0))\n                caja += np.where(act, h, 0.0)",1)
    s=s.replace("                    n_att += rearr","                    n_att += rearr\n                    EMP += rearr.astype(int)",1)
    s=s.replace("            caja += np.where(fa, h, 0.0)","            PDF[:] = np.where(fa, dx*5*k-cst, 0.0)\n            caja += np.where(fa, h, 0.0)",1)
    s=s.replace("            f_act = f_act & ~mu & ~bq","            BQF[:]=bq.astype(int)\n            f_act = f_act & ~mu & ~bq",1)
    assert "BQF[:]=bq" in s
    s=s.replace("    caja = np.zeros(R)","    SES=np.zeros(R,int); EMP=np.zeros(R,int); BQF=np.zeros(R,int)\n    PDE=np.zeros(R); PDF=np.zeros(R)\n    caja = np.zeros(R)",1)
    if rot=='superviviente_opera_dos_veces':   # el bug de v8 en la forma que SI existe a R=1
        s = s.replace("                    _opera = e_act[:, s].copy() if doble else rearr.copy()",
                      "                    _opera = e_act[:, s].copy()", 1)
        s = s.replace("                if intento == 0 and mu.any():",
                      "                if intento == 0:", 1)
        s = s.replace("                    if not rearr.any():", "                    if False:", 1)
        assert 'if False:' in s and 'if intento == 0:' in s
    if rot=='empalme_libre':   # el empalme deja de tener tope de 1/dia -> 2 pasadas siempre
        s=s.replace("                    _opera = rearr.copy()","                    _opera = e_act[:, s].copy()",1)
    ns={'__name__':'x','T':[]}; exec(compile(s,'x','exec'),ns); return ns
CFG=dict(R=1,DIAS=504,E=1,m_eval=2.,exp_eval=1110.,m_fun=4.,exp_fun=1480.,b_eval=40.,b_fun=70.,
  pool=2,qcap=3,qcap_tes=10000.,retencion=6860.,emerg=True,empalme=True,dormidas_ini=0,eod=True,
  cal_rth=(0.18,62,40.),cms=1.90,nb_use=86,relevo=0,slip_micro=2.5,holg=6134.114-2830,seed=14)
P=json.load(open(os.path.join(_AQUI,'replay_v10.json'))); D=P['dias']; TOPE=1076.0
def evalua(T):
    est=[];inv=[]
    for i,s in enumerate(T):
        n=i+1
        if s['ses']>1+s['emp']: inv.append(f"dia {n}: sesiones_de_eval={s['ses']} con {s['emp']} empalmes -> una CUENTA opero dos veces")
        if s['emp']>1: inv.append(f"dia {n}: {s['emp']} empalmes (max 1)")
        if s.get('bqf') and abs(s['pdf'])>1e-9:
            inv.append(f"dia {n}: bloqueo pero la cuenta movio balance ({s['pdf']:.2f}) -> viola la Regla 4.3")
        for k,et in (('pde','eval'),('pdf','funded')):
            if s[k]<-TOPE-1e-6: inv.append(f"dia {n}: peor_dia_{et}={s[k]:.2f} supera el tope {TOPE}")
        a=D[i]['fin_de_dia']
        for ruta,v in ((('caja',),s['caja']),(('funded','bal'),s['f_bal']),(('funded','s0'),s['f_s0']),
                       (('eval','bal'),s['e_bal']),(('recamara','n'),s['d_n']),(('pool','frescas'),s['fresh'])):
            x=a
            for k in ruta: x=x[k]
            if abs(x-v)>1e-3: est.append(f"dia {n}: {'.'.join(ruta)} esperado {x} obtenido {round(v,4)}")
    return est,inv
CASOS=[('orquestador CORRECTO',{},None),
       ('BUG DE v8: doble sesion de la eval',dict(doble=True),None),
       ('relevo D+2 (un dia tarde)',dict(relevo=1),None),
       ('qcap ignorado (recamara sin tope)',dict(qcap=None),None),
       ('empalme sin tope de 1/dia',{},'empalme_libre'),
       ('la eval SUPERVIVIENTE opera dos veces',{},'superviviente_opera_dos_veces'),
       ('look-ahead en la barra de entrada',dict(mira_atras=True),None),
       ('opera la cuenta bloqueada (viola regla 4.3)',dict(bloq_opera=True),None)]
print(f"{'orquestador':46s}{'fallos de estado':>18}{'invariantes rotos':>19}{'1er dia':>9}")
for et,kw,rot in CASOS:
    ns=motor(rot); ns['corre'](**{**CFG,**kw}); est,inv=evalua(ns['T'])
    d1=min([int(x.split()[1].rstrip(':')) for x in est+inv], default=0)
    print(f"{et:46s}{len(est):>18}{len(inv):>19}{d1 if d1 else '-':>9}")
    for x in inv[:1]: print(f"      -> {x}")
