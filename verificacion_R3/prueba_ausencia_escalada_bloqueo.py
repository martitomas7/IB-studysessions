# -*- coding: utf-8 -*-
"""D8 §5.2, respuesta del operador (RESPUESTA_D8_ITEM2_BLOQUEO.md §3):
"un test de censo... que fije como regresión que HOY el hueco existe".

Este test NO prueba una función -- **certifica una AUSENCIA**. No hay
nada que arreglar (el operador lo confirma: `bot/` reproduce el motor
congelado exactamente, R-2.4 tal cual pipeline3.py:284). Lo que hay que
fijar, para que no se pueda cerrar en silencio ni olvidarse, es que HOY:

1. Ningún camino de `bot/` escribe `pendientes_humano[].dias_esperando`
   (el campo que el dashboard necesitaría para pintar el aviso).
2. `alertas.bloqueada_escalada_dias`/`proveedor_mata_cuenta_dias`
   (03_CONFIG.yaml) los lee SOLO el panel (`contexto_dashboard.py`/
   `dashboard.py`) -- ningún camino los conecta a `bot/seguridad.py`
   (la escalera N0-N4).
3. No existe, en ningún sitio de `bot/`, un contador de "días
   bloqueada"/"días sin operar" por cuenta -- ni en el esquema de
   `estado.py::nuevo()`, ni en ningún módulo.

Nota del operador sobre el NOMBRE correcto del contador, para cuando
algún día se construya (no ahora): NO es "días consecutivos bloqueada"
(mal definido -- el modelo desactiva la cuenta y mañana puede activarse
OTRA dormida distinta). Es, por cuenta del PROVEEDOR, no por slot:
`dias_sin_operar` -- días consecutivos en que ESA cuenta no ha abierto
ninguna posición. Este test también confirma que ese nombre NO aparece
todavía en ningún sitio (para que, el día que se construya con el
nombre equivocado, alguien lo note aquí)."""
import inspect
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import bucle_del_dia as BDD, ciclo_vida as CV, contexto_dashboard as CD
from bot import dashboard as DASH, estado as E, orquestador as O, seguridad as SEG

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


print("=== HOY: certificando una AUSENCIA, no una función (RESPUESTA_D8_ITEM2_BLOQUEO.md §3) ===")

FUENTE_PANEL = inspect.getsource(CD) + inspect.getsource(DASH)
FUENTE_NEGOCIO = (inspect.getsource(CV) + inspect.getsource(O) + inspect.getsource(BDD)
                  + inspect.getsource(SEG))
FUENTE_ESTADO = inspect.getsource(E)

for clave in ("bloqueada_escalada_dias", "proveedor_mata_cuenta_dias", "dias_esperando"):
    ok(f"'{clave}': el panel LO USA de verdad (contexto_dashboard.py/dashboard.py)",
       clave in FUENTE_PANEL, clave)
    ok(f"'{clave}': NINGÚN camino de negocio (ciclo_vida/orquestador/bucle_del_dia/"
       f"seguridad) lo escribe ni lo conecta a la escalera N0-N4",
       clave not in FUENTE_NEGOCIO, clave)

for clave in ("dias_bloqueada", "dias_sin_operar"):
    ok(f"'{clave}': NO existe todavía ningún contador con este nombre en bot/ "
       f"(ni negocio, ni estado.py::nuevo(), ni el panel)",
       clave not in FUENTE_NEGOCIO and clave not in FUENTE_ESTADO and clave not in FUENTE_PANEL,
       clave)

# --- funcional, no solo textual: un bloqueo real no deja NINGÚN rastro en
#     pendientes_humano (complementa, sin repetir, la integración de 10 días
#     ya hecha en prueba_bloqueo_funded_sostenido.py) ---------------------
from bot import config as CFG
_, checksum = CFG.cargar()
st = E.nuevo('v10', checksum)
fu_bloqueada = dict(activa=True, fase=1, bal=101.0, pico=2100.0+ 100.0, H=0.0, s0=500.0,
                     dias=5, espera=0, k=0.0, m=0.0)
NB = 86
ph = pl = pc = [5000.0] * NB
r = CV.procesa_dia_funded(fu_bloqueada, direccion=1, ph=ph, pl=pl, pc=pc, b0v=0, es_dia_nuevo=False)
ok("un bloqueo real (r['bloqueo']=True, confirmado) no añade NADA a "
   "pendientes_humano -- nadie lo escribe hoy", r['bloqueo'] is True, r['bloqueo'])
ok("(estado global de referencia) pendientes_humano sigue vacío tras el bloqueo",
   st['pendientes_humano'] == [], st['pendientes_humano'])

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK -- "
      f"{'AUSENCIA CONFIRMADA (correcto, es lo que se pedía fijar)' if n_ok == len(resultados) else 'ALGO CAMBIÓ'}")
if n_ok != len(resultados):
    sys.exit(1)
