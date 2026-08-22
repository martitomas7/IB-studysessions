# -*- coding: utf-8 -*-
"""D8 §5.4 (ANALISIS_PUERTA_GRANDE.md §5) + DECISION_DEGRADACION_N3.md
(revisión operador 21-08-2026): degradación (R-7.2) -- cobertura 0 en la
Puerta Grande, la más profunda de las cuatro (ni siquiera el CÁLCULO se
había ejercitado nunca).

Historia de esta prueba, para que quede trazada (R1/R3):

1. Primera versión (commit 3eee10e): confirmó que `degradado`/
   `dia_degradacion` se fijan y son sticky, pero encontró y PINEÓ un
   hallazgo real -- el circuito NO paraba de verdad, solo se pintaba en
   el panel.
2. El operador revisó el hallazgo por su cuenta (DECISION_DEGRADACION_N3.md)
   y decidió: **degradación -> N3 (KILL)**, evaluado CADA día, cableado en
   `bot/bucle_del_dia.py` vía la nueva
   `bot/seguridad.py::reacciona_a_degradacion_tesoreria()`. Motivos (suyos,
   no inventados aquí): `comprueba_degradacion()` corre DESPUÉS de las
   sesiones del día -- cuando se detecta, el día ya está cerrado y el bot
   ya está PLANO, así que la única decisión real es "¿abre mañana?", y la
   respuesta, con una causa que por norma NUNCA desaparece (R-7.2: sticky),
   es no -- N3 es el único nivel cuya salida es "humano, explícito", la
   semántica correcta de un estado irreversible. También decidió ampliar
   `seguridad.py` a una escalera ÚNICA con causa tipada (`CAUSAS`), en vez
   de un segundo sistema de escalada en paralelo.
3. Esta versión (la actual) reemplaza la Parte 3 original (que pineaba el
   hallazgo) por los 5 tests que el operador pidió explícitamente para
   confirmar el cableado -- la Parte 1/2 (el cálculo, sticky) se
   mantienen sin cambios, siguen siendo ciertas.

IMPORTANTE, norma, no solo del bot (palabras del operador, textual): "el
modelo congelado (`modelo/`, `pipeline3.py`) NO simula el régimen
degradado -- mide una probabilidad, no opera un capital, así que sigue
corriendo más allá del cruce del muro sin parar (fiel a lo que es: un
simulador)." Por tanto TODO resultado de `modelo/` (P(degradar), la cifra
de $/mes, el replay de 504 días) correspondiente a un linaje que cruza el
muro deja de ser válido a partir de ese día -- el bot, aquí, SÍ para; el
modelo seguía midiendo. No son la misma cosa."""
import os
import random
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import (bucle_del_dia as BDD, config, contexto_dashboard as CD, dashboard as DASH,
                  estado as E, orquestador as O, seguridad as SEG, tesoreria as T)
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
# 1. El CÁLCULO -- primera vez que se ejercita, con el bucle real
#    (orquestador.procesa_dia()), no reconstruido a mano (R2/R3).
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
# Arnés común para las partes 3-6: un día a la vez, por el bucle REAL de
# producción, con eval FORZADA inactiva (pool agotado + emergencia apagada
# por el operador, mismo patrón que prueba_pool_agotado.py) -- así el muro
# dinámico (`tesoreria.muro_dinamico(0, 0)`) se queda CONSTANTE mientras
# dura la prueba (si eval se activase, el muro se movería -- R-7.1 lo resta
# de la exposición comprometida -- y el cruce exacto dejaría de ser
# predecible). Nada de esto cambia la aritmética que se está probando
# (R-7.2 no distingue si eval está activa o no); solo hace el escenario
# determinista.
# =============================================================================
DIR = "/tmp/prueba_degradacion"


class FuentePlanaUnDia:
    """Un solo día '22h' (b0v=0), barras planas -- se construye una
    instancia NUEVA por cada llamada a `bucle_del_dia()` (cada una es,
    literalmente, una corrida de producción de UN día -- exactamente como
    se invocaría el bot real, una vez al día, leyendo/escribiendo
    `estado.json`/`nivel.json` entre invocaciones)."""
    def __init__(self, nb=NB, p0=P0):
        self.nb = nb
        self.p0 = p0
        self._abierto = False
        self._b = -1

    def dia_disponible(self):
        return not self._abierto

    def abre_dia(self):
        self._abierto = True
        self._b = -1
        return ContextoDia()

    def siguiente_barra(self):
        self._b += 1
        return Barra(b=self._b, ph=self.p0, pl=self.p0, pc=self.p0,
                      es_ultima_barra_operable=(self._b >= self.nb - 1))

    def cierra_dia(self):
        pass


def _prepara_estado_base(caja_inicial):
    st0 = E.nuevo('v10', checksum)
    st0['pool'] = dict(frescas=0, rotas=2, subs=[])
    st0['desviaciones_activas'] = [dict(palanca='emergencia', desde_dia=1, hasta_dia=1000,
                                         quien='prueba_degradacion',
                                         ts_pared='2026-08-21T00:00:00Z')]
    st0['caja'] = caja_inicial
    return st0


def _corre_un_dia(ruta_estado, ruta_nivel, dir_run, semilla):
    adaptador = AdaptadorFalso()
    return BDD.bucle_del_dia(
        FuentePlanaUnDia(), adaptador,
        cuenta_hedge_eval="CH-EVAL", cuenta_prop_eval="CP-EVAL",
        cuenta_hedge_funded="CH-FUN", cuenta_prop_funded="CP-FUN",
        instrumento_prop="MES",
        ruta_estado=ruta_estado, ruta_nivel=ruta_nivel,
        ruta_ordenes=os.path.join(dir_run, "ordenes"), ruta_lock=os.path.join(dir_run, "bot.lock"),
        dir_instantaneas=os.path.join(dir_run, "instantaneas"), dias_retenidos=5,
        ruta_diario=os.path.join(dir_run, "diario.jsonl"), fase='plena',
        rng=random.Random(semilla), dormir=lambda s: None)


MURO_REF = T.muro_dinamico(0.0, 0.0)   # constante durante todo el arnés -- eval forzada inactiva

shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)
RUTA_ESTADO = os.path.join(DIR, "estado.json")
RUTA_NIVEL = os.path.join(DIR, "nivel.json")

# =============================================================================
# 3. EL DÍA EXACTO (DECISION_DEGRADACION_N3.md §5, test 2): cruzar el muro
#    el día D -> N3 el día D, N0 el día D-1.
# =============================================================================
print("\n=== 3. el día exacto: N0 el día D-1, N3 el día D (por el bucle REAL) ===")

E.guardar(_prepara_estado_base(-(MURO_REF - 1000.0)), RUTA_ESTADO)   # sano, holgado 1000$
st_d1 = _corre_un_dia(RUTA_ESTADO, RUTA_NIVEL, DIR, semilla=1)
ok("día 1 (sano): degradado sigue False", st_d1['degradado'] is False, st_d1['degradado'])
ok("día 1 (sano): nivel sigue N0", SEG.nivel_actual(RUTA_NIVEL) == 'N0', SEG.nivel_actual(RUTA_NIVEL))

# "algo pasa" entre el día 1 y el día 2 -- se fuerza la caja por debajo del
# muro directamente sobre el estado.json persistido (mismo principio que
# §5.3: el arnés fabrica la PRE-CONDICIÓN, nunca el resultado).
st_forzado = E.cargar(RUTA_ESTADO)
st_forzado['caja'] = -(MURO_REF + 500.0)
E.guardar(st_forzado, RUTA_ESTADO)

st_d2 = _corre_un_dia(RUTA_ESTADO, RUTA_NIVEL, DIR, semilla=2)
ok("día 2 (cruza): degradado se fija a True", st_d2['degradado'] is True, st_d2['degradado'])
ok("día 2 (cruza): dia_degradacion == 2 (el día EXACTO, no el 1)",
   st_d2['dia_degradacion'] == 2, st_d2['dia_degradacion'])
ok("día 2 (cruza): el nivel sube a N3 ESE MISMO día -- no un día tarde, no un día pronto",
   SEG.nivel_actual(RUTA_NIVEL) == 'N3', SEG.nivel_actual(RUTA_NIVEL))
ultima = SEG.lee_nivel(RUTA_NIVEL)['historial'][-1]
ok("la transición queda con causa='degradacion_tesoreria' (no un motivo de texto libre "
   "sin tipar)", ultima['causa'] == 'degradacion_tesoreria', ultima)

# =============================================================================
# 4. INVERTIDO (test 1): con degradado=True Y nivel YA en N3 (persistido de
#    una corrida anterior -- "no reanuda aunque lo reinicien"), una NUEVA
#    invocación de bucle_del_dia() no procesa NINGÚN día -- el chequeo de
#    entrada del bucle (nivel_actual() != 'N0': break) actúa ANTES de tocar
#    ningún día nuevo.
# =============================================================================
print("\n=== 4. invertido: con degradado=True y nivel ya en N3, una nueva invocación "
      "no procesa NINGÚN día ===")
dia_negociacion_antes = st_d2['dia_negociacion']
st_d3 = _corre_un_dia(RUTA_ESTADO, RUTA_NIVEL, DIR, semilla=3)
ok("bucle_del_dia() devuelve el ESTADO SIN CAMBIAR -- dia_negociacion sigue igual "
   "que antes de esta invocación (0 días nuevos procesados)",
   st_d3 is not None and st_d3['dia_negociacion'] == dia_negociacion_antes,
   (st_d3['dia_negociacion'] if st_d3 is not None else None, dia_negociacion_antes))
ok("nivel sigue en N3 (no se tocó)", SEG.nivel_actual(RUTA_NIVEL) == 'N3')

# =============================================================================
# 5. LO QUE IMPORTA (test 3): un humano baja el nivel a N0 a mano, con
#    degradado TODAVÍA True -> al día SIGUIENTE el bot vuelve a subir a N3
#    solo, sin que nadie se lo pida. Si esto no pasa, la barrera es
#    decorativa (palabras del operador).
# =============================================================================
print("\n=== 5. lo que importa: humano baja a N0 a mano, degradado sigue True -> "
      "el bot vuelve a subir a N3 SOLO al día siguiente ===")
SEG.baja_humana(RUTA_NIVEL, 'N0', quien='operador_martitomas7',
                 motivo='revisión manual -- comprobando si la barrera es de verdad')
ok("(fabricado) el humano consigue bajar a N0", SEG.nivel_actual(RUTA_NIVEL) == 'N0')
ok("(control) degradado SIGUE True en el estado persistido -- el humano NO lo tocó",
   E.cargar(RUTA_ESTADO)['degradado'] is True, E.cargar(RUTA_ESTADO)['degradado'])

st_d4 = _corre_un_dia(RUTA_ESTADO, RUTA_NIVEL, DIR, semilla=4)
ok("el bot SÍ procesa este día (partía de N0, el humano lo autorizó)",
   st_d4 is not None and st_d4['dia_negociacion'] == dia_negociacion_antes + 1,
   st_d4['dia_negociacion'] if st_d4 is not None else None)
ok("pero AL CIERRE de ese mismo día, con degradado todavía True, el bot vuelve a "
   "subir a N3 ÉL SOLO -- sin que nadie se lo pida (si esto no pasa, la barrera es "
   "decorativa)", SEG.nivel_actual(RUTA_NIVEL) == 'N3', SEG.nivel_actual(RUTA_NIVEL))
ultima_2 = SEG.lee_nivel(RUTA_NIVEL)['historial'][-1]
ok("la re-subida también queda tipada con causa='degradacion_tesoreria'",
   ultima_2['causa'] == 'degradacion_tesoreria' and ultima_2['de'] == 'N0', ultima_2)

# =============================================================================
# 6. REPOSICIÓN (test 4): degradado borrado + caja por encima del muro +
#    humano baja a N0 -> reanuda limpio, ya no vuelve a subir.
# =============================================================================
print("\n=== 6. reposición: degradado borrado + caja repuesta + humano baja a N0 -> "
      "reanuda limpio ===")
st_reponer = E.cargar(RUTA_ESTADO)
st_reponer['degradado'] = False
st_reponer['dia_degradacion'] = None
st_reponer['caja'] = -(MURO_REF - 2000.0)   # bien por encima del muro, sano de nuevo
E.guardar(st_reponer, RUTA_ESTADO)
SEG.baja_humana(RUTA_NIVEL, 'N0', quien='operador_martitomas7',
                 motivo='capital repuesto -- caja por encima del muro, degradado borrado')
ok("(fabricado) reposición: degradado=False, caja sana, nivel=N0",
   not E.cargar(RUTA_ESTADO)['degradado'] and SEG.nivel_actual(RUTA_NIVEL) == 'N0')

dia_antes_reposicion = E.cargar(RUTA_ESTADO)['dia_negociacion']
st_d5 = _corre_un_dia(RUTA_ESTADO, RUTA_NIVEL, DIR, semilla=5)
ok("tras la reposición, el bot procesa el día con normalidad",
   st_d5 is not None and st_d5['dia_negociacion'] == dia_antes_reposicion + 1,
   st_d5['dia_negociacion'] if st_d5 is not None else None)
ok("degradado se queda en False -- no vuelve a activarse por sí solo",
   st_d5['degradado'] is False, st_d5['degradado'])
ok("el nivel se queda en N0 -- la reposición fue limpia, no re-escala",
   SEG.nivel_actual(RUTA_NIVEL) == 'N0', SEG.nivel_actual(RUTA_NIVEL))

shutil.rmtree(DIR, ignore_errors=True)

# =============================================================================
# 7. LA CAUSA TIPADA LLEGA AL PANEL Y SE PINTA (test 5)
# =============================================================================
print("\n=== 7. la causa tipada llega al panel (contexto_dashboard.py) y se pinta "
      "(dashboard.py) ===")
DIR2 = "/tmp/prueba_degradacion_panel"
shutil.rmtree(DIR2, ignore_errors=True)
os.makedirs(DIR2)
ruta_nivel_panel = os.path.join(DIR2, "nivel.json")
SEG.reacciona_a_degradacion_tesoreria(ruta_nivel_panel, dia_negociacion=7, dia_degradacion=5)

st_panel = E.nuevo('v10', checksum)
st_panel['degradado'] = True
st_panel['dia_degradacion'] = 5
nivel_registro = SEG.lee_nivel(ruta_nivel_panel)
ctx = CD.construye(st_panel, None, [], ahora_iso='2026-08-21T00:00:00Z',
                    nivel_registro=nivel_registro)
ok("ctx['ahora']['contencion']['nivel'] == 'N3'",
   ctx['ahora']['contencion']['nivel'] == 'N3', ctx['ahora']['contencion'])
ok("ctx['ahora']['contencion']['causa'] == 'degradacion_tesoreria' -- la causa TIPADA, "
   "no solo el motivo de texto libre, llega hasta el contexto del panel",
   ctx['ahora']['contencion']['causa'] == 'degradacion_tesoreria', ctx['ahora']['contencion'])
ok("el semáforo global del panel es 'critico' -- ahora refleja el NIVEL de verdad, no "
   "solo 'degradado' a secas (DECISION_DEGRADACION_N3.md §3: una sola escalera)",
   ctx['ahora']['semaforo_global'] == 'critico', ctx['ahora']['semaforo_global'])

html = DASH.genera_html(ctx)
ok("el HTML generado SÍ pinta la causa tipada ('degradacion_tesoreria' aparece en el "
   "HTML, no solo en el ctx)", 'degradacion_tesoreria' in html)
ok("el HTML generado SÍ pinta el nivel N3", 'N3' in html and 'KILL' in html)
shutil.rmtree(DIR2, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
