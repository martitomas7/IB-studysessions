# -*- coding: utf-8 -*-
"""RUNNER del replay pack v10.  Dos modos:

  python runner_replay_v10.py              -> autocomprueba los invariantes del pack
  python runner_replay_v10.py estados.json -> valida TU orquestador: un json con la misma
                                              forma que `dias[].fin_de_dia`, uno por dia

REGLA: si falla, se arregla el orquestador, jamas el pack.
"""
import json, os, sys
AQUI = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(os.path.join(AQUI, 'replay_v10.json')))
D = P['dias']
TOPE = 1076.00          # DLL + CMS*kcap = 1000 + 1,90*40
fallos = []

def inv(dias):
    """Invariantes de ORQUESTADOR: los que ningun golden puede ver porque miran UN dia
    aislado.  El hueco de relevo NO se comprueba aqui como regla dura (depende del stock de
    recamara y de la tesoreria, y una regla ingenua da falsos positivos): lo caza la
    comparacion de estado, que para un relevo un dia tarde produce >1.000 divergencias."""
    f = []
    for d in dias:
        i, e, n = d['invariantes'], d['eventos'], d['dia']
        if i['sesiones_de_eval'] > 1 + i['empalmes']:
            f.append(f"dia {n}: {i['sesiones_de_eval']} sesiones de eval con {i['empalmes']} "
                     f"empalmes -> alguna CUENTA opero dos veces el mismo dia")
        if i['empalmes'] > 1:
            f.append(f"dia {n}: {i['empalmes']} empalmes (maximo 1/dia)")
        for k in ('peor_dia_una_cuenta_eval', 'peor_dia_funded'):
            if i[k] < -TOPE - 1e-6:
                f.append(f"dia {n}: {k} = {i[k]:.2f} $ supera el tope diario de {TOPE:.2f} $")
        if i.get('bloqueo_funded'):     # Regla 4.3: la bloqueada NO opera
            if abs(i['peor_dia_funded']) > 1e-9:
                f.append(f"dia {n}: bloqueo_funded=1 pero la cuenta movio balance "
                         f"({i['peor_dia_funded']}) -> viola la Regla 4.3")
    return f

def comparar(dias, mios):
    f = []
    for d, m in zip(dias, mios):
        a, b = d['fin_de_dia'], m
        for ruta in (('caja',), ('funded', 'bal'), ('funded', 's0'), ('eval', 'bal'),
                     ('recamara', 'n'), ('pool', 'frescas'), ('pool', 'rotas')):
            x, y = a, b
            for k in ruta: x, y = x[k], y[k]
            if abs(x - y) > 1e-3:
                f.append(f"dia {d['dia']}: {'.'.join(ruta)} esperado {x} obtenido {y}")
    return f

fallos += inv(D)
if len(sys.argv) > 1:
    fallos += comparar(D, json.load(open(sys.argv[1])))
print(f"replay v10: {len(D)} dias · {len(fallos)} fallos")
for x in fallos[:12]: print("  " + x)
if len(fallos) > 12: print(f"  ... y {len(fallos)-12} mas")
sys.exit(1 if fallos else 0)
