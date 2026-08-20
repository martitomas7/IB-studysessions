# -*- coding: utf-8 -*-
"""PRUEBA DE DISCRIMINACION de los goldens: nucleos ROTOS a proposito.

Existe por la Regla R3 de 04_GUARDARRAILES: una comprobacion que nunca ha disparado no es
una comprobacion, es un comentario.  Aqui se rompe el nucleo de referencia de tres maneras
-- las tres formas de equivocarse que este proyecto YA cometio -- y se exige que los
goldens caigan, y que caigan EN LOS CASOS PREVISTOS.

Si algun dia una de estas roturas deja de romper goldens, es que los goldens se han
degradado: no se sigue adelante hasta arreglarlos.

Uso:  python prueba_goldens_v10.py
Salida: tabla de roturas.  Codigo 0 solo si TODAS rompen lo previsto.
"""
import json, os, sys, types

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTE = open(os.path.join(AQUI, 'nucleo_referencia_v10.py')).read()
G = json.load(open(os.path.join(AQUI, 'goldens_v10.json')))


def carga(nombre, roturas):
    """Compila el nucleo con las sustituciones de `roturas` aplicadas (1 vez cada una)."""
    src = FUENTE
    for viejo, nuevo in roturas:
        assert viejo in src, f"[{nombre}] el ancla no esta en el nucleo: {viejo!r}"
        src = src.replace(viejo, nuevo, 1)
    mod = types.ModuleType('nucleo_roto_' + nombre)
    exec(compile(src, '<' + nombre + '>', 'exec'), mod.__dict__)
    return mod


def falla_en(mod):
    """Devuelve la lista de nombres de golden que NO reproduce este nucleo."""
    malos = []
    for c in G['casos']:
        esp = c['salidas']
        try:
            obt = mod.resolver_sesion(c['entradas'])
        except Exception as e:                      # una rotura que explota tambien cuenta
            malos.append(c['nombre']); continue
        for k in esp:
            v, w = esp[k], obt[k]
            dif = abs(v - w) > 1e-6 if isinstance(v, float) else v != w
            if dif:
                malos.append(c['nombre']); break
    return malos


# --- las tres roturas, con lo que DEBE caer -------------------------------------------
ROTOS = [
    # 1) el look-ahead de v8: vigilar DESDE la barra de entrada en vez de desde la siguiente.
    #    Costo historico: 13,6 % del titular.
    ('look_ahead_en_b0',
     [("for b in range(b0 + 1, NB):", "for b in range(b0, NB):")],
     ['LOOKAHEAD_suelo_en_b0', 'LOOKAHEAD_objetivo_en_b0', 'LOOKAHEAD_empalme_b40']),

    # 2) sin la segunda pasada del sizing (la cuna de comision): k queda sobredimensionado
    #    y la salida EOD dispara la muerte antes de tiempo.
    ('sin_cuna_de_comision',
     [("""    k = float(kcap) if den <= 0 else math.floor(min(m * max(Mm - CMS * k1, 1e-9)
                                                    / max(den, 1e-9), kcap))""",
       "    pass  # ROTO: se queda con k0, sin restar la comision")],
     None),          # None = "tiene que romper algo, no exigimos cuales"

    # 3) ignorar la Regla 4.3: dejar operar a la cuenta con k<1.
    ('opera_bloqueada',
     [("""    if bloq:                                           # REGLA 4.3: no opera
        dx = 0.0; cst = 0.0; h = 0.0
        muere = False; pausa = False; tgt = False""",
       "    if False:\n        pass  # ROTO: la bloqueada opera igual")],
     ['bloqueo_k_menor_1']),
]

print(f"{'nucleo roto':<34}{'goldens que caen':>18}   cuales")
print("-" * 96)
todo_ok = True
for nombre, roturas, esperados in ROTOS:
    mod = carga(nombre, roturas)
    caen = falla_en(mod)
    print(f"{nombre:<34}{len(caen):>18}   {', '.join(caen) if caen else '(ninguno)'}")
    if not caen:
        print(f"      -> ERROR: esta rotura NO rompe ningun golden. Los goldens no discriminan.")
        todo_ok = False
    if esperados is not None:
        faltan = [e for e in esperados if e not in caen]
        if faltan:
            print(f"      -> ERROR: deberian caer tambien {faltan}")
            todo_ok = False
        else:
            print(f"      -> OK: caen los previstos ({', '.join(esperados)})")

# y el nucleo INTACTO tiene que pasarlos todos
intacto = carga('intacto', [])
caen = falla_en(intacto)
print("-" * 96)
print(f"{'nucleo de referencia INTACTO':<34}{len(caen):>18}   {', '.join(caen) if caen else '(ninguno)'}")
if caen:
    print("      -> ERROR: el nucleo de referencia no pasa sus propios goldens.")
    todo_ok = False

print()
print("PRUEBA DE DISCRIMINACION: " + ("OK" if todo_ok else "FALLA"))
sys.exit(0 if todo_ok else 1)
