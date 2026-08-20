# -*- coding: utf-8 -*-
"""RUNNER de los goldens v10.  Uso:  python runner_goldens_v10.py [adaptador]
Sin argumento valida `nucleo_referencia_v10.py`.  Con argumento, valida el modulo indicado,
que debe exponer `resolver_sesion(entradas) -> salidas`.
REGLA: si un test falla se arregla EL CODIGO, jamas el test.
"""
import json, os, sys, importlib
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
mod = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'nucleo_referencia_v10')
G = json.load(open(os.path.join(AQUI, 'goldens_v10.json')))
mal = 0
for c in G['casos']:
    s, e = c['salidas'], mod.resolver_sesion(c['entradas'])
    dif = [k for k in s if (abs(s[k] - e[k]) > 1e-6 if isinstance(s[k], float) else s[k] != e[k])]
    if dif:
        mal += 1
        print(f"FALLA {c['nombre']}: " + " ".join(f"{k}: esperado {s[k]} obtenido {e[k]}" for k in dif))
print(f"{len(G['casos']) - mal}/{len(G['casos'])} goldens OK")
sys.exit(1 if mal else 0)
