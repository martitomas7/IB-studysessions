# -*- coding: utf-8 -*-
"""D8 §5.4 (ANALISIS_PUERTA_GRANDE.md §5): degradación (R-7.2) --
cobertura 0 en la Puerta Grande, la más profunda de las cuatro (ni
siquiera el CÁLCULO se ha ejercitado nunca -- ver
`verificacion_R3/CENSO_COBERTURA.md`: "Degradación: 0 -- NUNCA"). El
pedido: "Forzar la caja por debajo de la parada dinámica y comprobar que
`degradado`/`dia_degradacion` se fijan y que el circuito para de verdad."

Investigación previa a fabricar nada (R1/R3, mismo principio que §5.2):
`bot/tesoreria.py::muro_dinamico()`/`comprueba_degradacion()` son
funciones puras -- no hace falta erosionar caja día a día, basta con
LEER el muro real (mismas funciones, sin tocar nada) y forzar
`st['caja']` directamente por debajo de él, confirmado antes de usarlo.

Grep exhaustivo, ANTES de escribir el test, de qué hace HOY el resto del
sistema con `st['degradado']` -- para no fabricar un escenario y suponer
que algo reacciona cuando no es así:

- `bot/orquestador.py::procesa_dia()` (líneas 187-190): calcula el muro,
  llama a `comprueba_degradacion()`, y fija `degradado`/`dia_degradacion`
  -- ESTO SÍ está cableado y se confirma abajo, por primera vez.
- `bot/contexto_dashboard.py`/`bot/dashboard.py`: SOLO leen `degradado`
  para pintar un semáforo ('crítico' vs 'bien') -- lectura, cero acción.
- `bot/bucle_del_dia.py`, el bucle real de producción (línea ~90): el
  ÚNICO chequeo que para el bucle día a día es
  `if SEG.nivel_actual(ruta_nivel) != 'N0': break` -- la escalera N0-N4 de
  `bot/seguridad.py`. `degradado` NO aparece en ningún sitio de este
  fichero. Y nada, en NINGÚN módulo de `bot/`, llama a
  `seguridad.sube_a()`/`reacciona_a_*` por causa de la degradación.

Conclusión, confirmada abajo con el bucle REAL, no solo leída: **la
degradación se CALCULA y se FIJA correctamente (sticky, no se revierte
sola), pero el circuito NO para** -- sigue negociando exactamente igual
que si `degradado` fuera `False`. Es el MISMO patrón que §5.2 (bloqueo
sostenido de funded): una señal de negocio correcta que hoy solo
alimenta el panel, sin ningún camino de código que la convierta en una
parada real. No se arregla aquí -- cablear "degradado detiene el bucle"
es una decisión de negocio real (¿para inmediatamente? ¿ese mismo día,
al cierre? ¿solo humano puede reanudar, como N3/N4?) que le corresponde
al operador (R2/R6), no a esta sesión. Se deja medida, y PINEADA como
regresión nombrada -- si algún día se cablea, este test debe empezar a
fallar y alguien tiene que revisarlo, no que el cambio pase
desapercibido."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import bucle_del_dia as BDD, config, estado as E, orquestador as O, seguridad as SEG, tesoreria as T
from bot.adaptador_falso import AdaptadorFalso
from bot.fuente_barras import Barra, ContextoDia

_, checksum = config.cargar()
cfg = config.obtener()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


NB = 86
P0 = 5000.0


def _camino_plano():
    return [P0] * NB, [P0] * NB, [P0] * NB


# =============================================================================
# 1. El CÁLCULO -- primera vez que se ejercita, por primera vez con el
#    bucle real (orquestador.procesa_dia()), no reconstruido a mano (R2/R3).
# =============================================================================
print("=== 1. forzar caja por debajo del muro dinámico -- degradado/dia_degradacion "
      "se fijan de verdad ===")

st = E.nuevo('v10', checksum)
muro_eval_inactiva = T.muro_dinamico(0.0, 0.0)   # eval sigue inactiva al arrancar (E.nuevo())
ok(f"(control) eval arranca inactiva -- el muro de referencia es el de eval en 0 "
   f"(muro={muro_eval_inactiva:.3f} $)", st['eval']['activa'] is False, st['eval']['activa'])

MARGEN_BAJO_MURO = 500.0
st['caja'] = -(muro_eval_inactiva + MARGEN_BAJO_MURO)
ok("(pre-condición) antes de procesar el día, degradado sigue False -- la parada se "
   "declara el día en que se CRUZA, no antes", st['degradado'] is False, st['degradado'])

ph1, pl1, pc1 = _camino_plano()
st, fin_de_dia_1, diario_1 = O.procesa_dia(st, direccion=1, ventana_txt='22h', ph=ph1, pl=pl1,
                                            pc=pc1, b0v=0, n_resets_hoy=0)
ok("día 1: degradado se fija a True (caja-retirado < -muro, R-7.2)",
   st['degradado'] is True, st['degradado'])
ok("día 1: dia_degradacion se fija al día EXACTO en que se cruza (día 1)",
   st['dia_degradacion'] == 1, st['dia_degradacion'])

# --- sticky: no se revierte sola, ni aunque la caja se recupere del todo ----
print("\n=== 2. degradado es STICKY -- no se revierte solo aunque la caja se recupere ===")
st['caja'] = 1_000_000.0   # recuperación total, muy por encima de cualquier muro plausible
ph2, pl2, pc2 = _camino_plano()
st, fin_de_dia_2, diario_2 = O.procesa_dia(st, direccion=1, ventana_txt='22h', ph=ph2, pl=pl2,
                                            pc=pc2, b0v=0, n_resets_hoy=0)
ok("día 2, con la caja recuperada del todo: degradado SIGUE True (mismo principio que "
   "estado.json.degradado -- 'una vez True, no se revierte solo', comprueba_degradacion())",
   st['degradado'] is True, st['degradado'])
ok("día 2: dia_degradacion NO cambia -- sigue apuntando al PRIMER día que cruzó (1), "
   "no se reescribe", st['dia_degradacion'] == 1, st['dia_degradacion'])

# =============================================================================
# 3. El hallazgo confirmado: el circuito NO para -- ni con el bucle REAL de
#    producción. degradado=True desde el día 1, seguido de más días en
#    los que sigue negociando exactamente igual.
# =============================================================================
print("\n=== 3. el circuito, con el bucle REAL de producción, NO PARA por degradación ===")


class FuentePlanaNDias:
    """N días '22h' (b0v=0) de barras completamente planas -- ni funded ni
    eval mueren ni se activan/aprueban en la ventana corta del test (no
    hace falta: lo único que importa aquí es si el BUCLE se detiene por
    `degradado`, no la aritmética de sesión, que ya cubren otros
    tests)."""
    def __init__(self, n_dias, nb=NB, p0=P0):
        self.n_dias = n_dias
        self.nb = nb
        self.p0 = p0
        self._dia_actual = 0
        self._b = -1

    def dia_disponible(self):
        return self._dia_actual < self.n_dias

    def abre_dia(self):
        self._dia_actual += 1
        self._b = -1
        return ContextoDia()

    def siguiente_barra(self):
        self._b += 1
        return Barra(b=self._b, ph=self.p0, pl=self.p0, pc=self.p0,
                      es_ultima_barra_operable=(self._b >= self.nb - 1))

    def cierra_dia(self):
        pass


import random

DIR = "/tmp/prueba_degradacion"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)
ruta_estado = os.path.join(DIR, "estado.json")
ruta_nivel = os.path.join(DIR, "nivel.json")

st_inicial = E.nuevo('v10', checksum)
muro_ref = T.muro_dinamico(0.0, 0.0)
st_inicial['caja'] = -(muro_ref + MARGEN_BAJO_MURO)
E.guardar(st_inicial, ruta_estado)

N_DIAS = 5
adaptador = AdaptadorFalso()
fuente = FuentePlanaNDias(N_DIAS)
st_final = BDD.bucle_del_dia(
    fuente, adaptador,
    cuenta_hedge_eval="CH-EVAL", cuenta_prop_eval="CP-EVAL",
    cuenta_hedge_funded="CH-FUN", cuenta_prop_funded="CP-FUN",
    instrumento_prop="MES",
    ruta_estado=ruta_estado, ruta_nivel=ruta_nivel,
    ruta_ordenes=os.path.join(DIR, "ordenes"), ruta_lock=os.path.join(DIR, "bot.lock"),
    dir_instantaneas=os.path.join(DIR, "instantaneas"), dias_retenidos=5,
    ruta_diario=os.path.join(DIR, "diario.jsonl"),
    rng=random.Random(20260821), dormir=lambda s: None)

ok(f"el bucle en vivo procesó los {N_DIAS} días PEDIDOS -- confirmado: NO se detuvo "
   f"por causa de la degradación (si parase, dia_negociacion sería < {N_DIAS})",
   st_final is not None and st_final['dia_negociacion'] == N_DIAS,
   st_final['dia_negociacion'] if st_final is not None else None)
ok("degradado se quedó fijado en True desde el primer día, durante TODO el resto del "
   "bucle -- se calcula y se guarda bien", st_final['degradado'] is True, st_final['degradado'])
ok("dia_degradacion sigue siendo el día 1 -- el bucle real, no solo procesa_dia() aislado, "
   "confirma el mismo comportamiento sticky", st_final['dia_degradacion'] == 1,
   st_final['dia_degradacion'])
ok(f"CONFIRMADO -- HALLAZGO PINEADO: nivel.json se queda en N0 durante los {N_DIAS} días, "
   f"pese a degradado=True desde el día 1 -- bot/bucle_del_dia.py SOLO detiene el bucle "
   f"si seguridad.nivel_actual() != 'N0', y NADA en bot/ escala ese nivel por causa de la "
   f"degradación (grep confirmado antes de escribir este test). El circuito, HOY, NO para "
   f"de verdad por degradación -- solo lo pinta el panel (bot/contexto_dashboard.py, "
   f"bot/dashboard.py). Cablear una parada real es una decisión del operador (R2/R6), no "
   f"de esta sesión -- si algún día se cablea, este assert debe empezar a fallar.",
   SEG.nivel_actual(ruta_nivel) == 'N0', SEG.nivel_actual(ruta_nivel))

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
