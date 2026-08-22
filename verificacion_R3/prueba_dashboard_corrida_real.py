# -*- coding: utf-8 -*-
"""D8 §5.5 (ANALISIS_PUERTA_GRANDE.md §5 / ORDEN_DE_TRABAJO_D8.md §5):
"dashboard contra una corrida real" -- `verificacion_R3/prueba_dashboard.py`
ya prueba `contexto_dashboard.py`/`dashboard.py` a fondo, pero SIEMPRE
contra `estado`/`diario` fabricados a mano en el propio test (goldens
sintéticos). Lo que falta, y es lo que pide este ítem, es el pipeline
COMPLETO de punta a punta: `bot/bucle_del_dia.py` (producción de verdad)
-> disco (`estado.json`/`diario.jsonl`/`nivel.json`) -> LEÍDOS de disco
(no reutilizados en memoria) -> `contexto_dashboard.construye()` ->
`dashboard.genera_html()` -- para cazar cualquier desajuste entre la
FORMA que de verdad escribe el bucle en vivo y la forma que el panel
espera leer (el mismo tipo de bug que ya cazó
`prueba_lector_laboratorio.py`: "ts" vs "ts_pared", nunca ejercitado con
datos reales hasta que alguien probó con datos reales).

Fabrica una corrida corta pero con eventos GENUINOS (no inventados
después, sino producidos por el bucle real):
  - una muerte real de eval + CONTRA armándose (misma receta de erosión
    de `prueba_sorteo_direccion_contra.py`/`prueba_bloqueo_funded_sostenido.py`
    -- un toque de suelo dado dos días seguidos, el segundo sí mata),
  - y, al final, una degradación real (la caja se fuerza por debajo del
    muro entre dos invocaciones, mismo patrón que
    `prueba_degradacion.py`) -- para que el panel tenga un nivel N3 con
    causa tipada de verdad que pintar, no un ctx fabricado a mano."""
import json
import os
import random
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from apoyo_puerta_grande import AdaptadorReplaySobrePack

from bot import (bucle_del_dia as BDD, calendario, config, contexto_dashboard as CD,
                  dashboard as DASH, estado as E, seguridad as SEG, tesoreria as T)
from bot.fuente_barras import Barra, ContextoDia

_, checksum = config.cargar()
cfg = config.obtener()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


NB = 86
P0 = 5000.0
MAGNITUD_TOQUE = 100_000.0   # ver prueba_sorteo_direccion_contra.py -- garantiza SIEMPRE
                              # la pata STOP, sin conocer el ndn exacto del día.


def _camino_plano():
    return [P0] * NB, [P0] * NB, [P0] * NB


def _camino_con_toque(barra_toque=1):
    ph = [P0] * NB
    pl = list(ph)
    pc = list(ph)
    pl[barra_toque] = P0 - MAGNITUD_TOQUE
    pc[barra_toque] = pl[barra_toque]
    for b in range(barra_toque + 1, NB):
        ph[b] = pl[b] = pc[b] = pc[barra_toque]
    return ph, pl, pc


class FuenteConMuerteReal:
    """Mismo patrón que `FuenteEnVivoConMuerteReal` de
    `prueba_sorteo_direccion_contra.py` -- `direccion=None` (el bucle
    sortea de verdad), oráculo de resolución de LA PUERTA GRANDE
    (`AdaptadorReplaySobrePack`) para que un bracket se resuelva por
    precio real, un toque de suelo dado dos días seguidos para una
    muerte real de eval (R-3.4). Dirección: no hace falta controlarla
    (esta prueba no verifica CONTRA, ya lo hace
    `prueba_sorteo_direccion_contra.py`) -- basta con dejar que el bucle
    la sortee de verdad y aceptar cualquier signo."""

    def __init__(self, n_dias, dia_erosion, dia_muerte, adaptador, cuentas_prop):
        self.n_dias = n_dias
        self.dia_erosion = dia_erosion
        self.dia_muerte = dia_muerte
        self.adaptador = adaptador
        self.cuentas_prop = cuentas_prop
        self._dia_actual = 0
        self._b = -1
        self._ph = self._pl = self._pc = None

    def dia_disponible(self):
        return self._dia_actual < self.n_dias

    def abre_dia(self):
        self._dia_actual += 1
        self._b = -1
        if self._dia_actual in (self.dia_erosion, self.dia_muerte):
            self._ph, self._pl, self._pc = _camino_con_toque()
        else:
            self._ph, self._pl, self._pc = _camino_plano()
        for cuenta_prop in self.cuentas_prop:
            self.adaptador.registra_dia(cuenta_prop, self._ph, self._pl, self._pc,
                                         self._pc, barra_inicio=0)
        return ContextoDia()

    def siguiente_barra(self):
        self._b += 1
        barra = Barra(b=self._b, ph=self._ph[self._b], pl=self._pl[self._b],
                       pc=self._pc[self._b], es_ultima_barra_operable=(self._b >= NB - 1))
        self.adaptador.notifica_barra(barra.b)
        return barra

    def cierra_dia(self):
        for cuenta_prop in self.cuentas_prop:
            self.adaptador.quita_dia(cuenta_prop)


DIR = "/tmp/prueba_dashboard_corrida_real"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)
RUTA_ESTADO = os.path.join(DIR, "estado.json")
RUTA_NIVEL = os.path.join(DIR, "nivel.json")
RUTA_DIARIO = os.path.join(DIR, "diario.jsonl")
E.guardar(E.nuevo('v10', checksum), RUTA_ESTADO)

print("=== 1. corrida real: bot/bucle_del_dia.py, N días, con una muerte real de eval ===")

CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES = "CH-EVAL", "CP-EVAL", "CH-FUN", "CP-FUN", "MES"
adaptador = AdaptadorReplaySobrePack(MES, modo='perfecto')
N_DIAS = 8
DIA_EROSION, DIA_MUERTE = 4, 5
fuente = FuenteConMuerteReal(N_DIAS, DIA_EROSION, DIA_MUERTE, adaptador, (CP_EVAL, CP_FUN))

_orig_ventana = calendario.ventana_del_dia
calendario.ventana_del_dia = lambda es_dia_de_dato: ('22h', 0)
try:
    st_final = BDD.bucle_del_dia(
        fuente, adaptador,
        cuenta_hedge_eval=CH_EVAL, cuenta_prop_eval=CP_EVAL,
        cuenta_hedge_funded=CH_FUN, cuenta_prop_funded=CP_FUN,
        instrumento_prop=MES,
        ruta_estado=RUTA_ESTADO, ruta_nivel=RUTA_NIVEL,
        ruta_ordenes=os.path.join(DIR, "ordenes"), ruta_lock=os.path.join(DIR, "bot.lock"),
        dir_instantaneas=os.path.join(DIR, "instantaneas"), dias_retenidos=5,
        ruta_diario=RUTA_DIARIO, fase='plena', rng=random.Random(20260821), dormir=lambda s: None)
finally:
    calendario.ventana_del_dia = _orig_ventana

ok(f"los {N_DIAS} días se procesaron de verdad", st_final is not None
   and st_final['dia_negociacion'] == N_DIAS, st_final['dia_negociacion'] if st_final else None)

diario_lineas_crudas = [json.loads(l) for l in open(RUTA_DIARIO, encoding='utf-8')]
muertes_eval_reales = sum(d['eventos']['muertes_eval'] for d in diario_lineas_crudas)
ok("la corrida produjo una muerte real de eval (>= 1) -- no un evento inventado después",
   muertes_eval_reales >= 1, muertes_eval_reales)

print("\n=== 2. degradación real: la caja se fuerza entre dos invocaciones, un día más ===")
st_leido = E.cargar(RUTA_ESTADO)
muro_ref = T.muro_dinamico(
    cfg.sizing.m_eval.valor() if st_leido['eval']['activa'] else 0.0,
    cfg.sizing.exp_eval_usd.valor() if st_leido['eval']['activa'] else 0.0)
st_leido['caja'] = -(muro_ref + 500.0)
E.guardar(st_leido, RUTA_ESTADO)


class FuentePlanaUnDia:
    def __init__(self, nb=NB, p0=P0):
        self.nb, self.p0, self._abierto, self._b = nb, p0, False, -1

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


st_final2 = BDD.bucle_del_dia(
    FuentePlanaUnDia(), adaptador,
    cuenta_hedge_eval=CH_EVAL, cuenta_prop_eval=CP_EVAL,
    cuenta_hedge_funded=CH_FUN, cuenta_prop_funded=CP_FUN,
    instrumento_prop=MES,
    ruta_estado=RUTA_ESTADO, ruta_nivel=RUTA_NIVEL,
    ruta_ordenes=os.path.join(DIR, "ordenes"), ruta_lock=os.path.join(DIR, "bot.lock"),
    dir_instantaneas=os.path.join(DIR, "instantaneas"), dias_retenidos=5,
    ruta_diario=RUTA_DIARIO, fase='plena', rng=random.Random(1), dormir=lambda s: None)
ok("el día extra se procesó y degradó de verdad", st_final2['degradado'] is True,
   st_final2['degradado'])
ok("el nivel subió a N3 de verdad, cableado por bot/bucle_del_dia.py",
   SEG.nivel_actual(RUTA_NIVEL) == 'N3', SEG.nivel_actual(RUTA_NIVEL))

# =============================================================================
# 3. El pipeline COMPLETO: disco -> contexto_dashboard.construye() ->
#    dashboard.genera_html() -- todo LEÍDO de disco, nada reutilizado de
#    las variables de arriba (para que la prueba sea honesta: es la MISMA
#    ruta que seguiría un proceso de panel separado, arrancado en frío).
# =============================================================================
print("\n=== 3. pipeline completo: disco -> contexto_dashboard -> dashboard.genera_html ===")

estado_disco = E.cargar(RUTA_ESTADO)
diario_disco = [json.loads(l) for l in open(RUTA_DIARIO, encoding='utf-8')]
nivel_disco = SEG.lee_nivel(RUTA_NIVEL)

ctx = CD.construye(estado_disco, diario_disco[-1], diario_disco, ahora_iso='2026-08-21T12:00:00Z',
                    nivel_registro=nivel_disco)
ok("construye() no revienta contra datos REALES de disco (nunca ejercitado así antes de "
   "esta prueba)", ctx is not None)

# --- valores REALES, no re-derivados: comparados contra lo que hay en el
#     propio estado.json/diario.jsonl leídos, para que un desajuste de forma
#     lo cace esta prueba y no un usuario mirando el panel en producción ---
ok("ctx['riesgo']['caja'] == estado.json.caja EXACTO",
   ctx['riesgo']['caja'] == estado_disco['caja'], (ctx['riesgo']['caja'], estado_disco['caja']))
ok("ctx['ahora']['direccion'] == la dirección REAL del último día del diario",
   ctx['ahora']['direccion'] == diario_disco[-1]['direccion'], ctx['ahora']['direccion'])
ok("ctx['ahora']['contencion']['nivel'] == 'N3' -- el nivel REAL leído de nivel.json, no "
   "fabricado", ctx['ahora']['contencion']['nivel'] == 'N3', ctx['ahora']['contencion'])
ok("ctx['ahora']['contencion']['causa'] == 'degradacion_tesoreria' -- la causa tipada REAL",
   ctx['ahora']['contencion']['causa'] == 'degradacion_tesoreria', ctx['ahora']['contencion'])
n_dias_reales = len(diario_disco)
ok(f"el bloque MODELO vs REALIDAD agrega sobre los {n_dias_reales} días REALES del diario "
   f"(E6.n == len(diario))",
   next(b for b in ctx['laboratorio'] if b['nombre'] == 'E6')['n'] == n_dias_reales,
   next(b for b in ctx['laboratorio'] if b['nombre'] == 'E6'))
fila_muertes_eval = next(f for f in ctx['modelo_vs_realidad'] if f['evento'] == 'muertes de eval')
ok("la fila 'muertes de eval' del bloque 6 cuenta EXACTAMENTE las muertes reales del "
   "diario -- ni una fabricada, ni una perdida",
   fila_muertes_eval['n'] == muertes_eval_reales, fila_muertes_eval)

html = DASH.genera_html(ctx)
ok("el HTML generado no revienta (string no vacío)", isinstance(html, str) and len(html) > 0)
ok("el HTML pinta el nivel real N3", 'N3' in html and 'KILL' in html)
ok("el HTML pinta la causa tipada real", 'degradacion_tesoreria' in html)
ok("el HTML pinta la caja real (formateada, no en crudo -- separador de miles con espacio "
   "fino \\u2009, mismo formato que dashboard.py::_num())",
   f"{estado_disco['caja']:,.2f}".replace(",", " ") in html)
ok("el HTML pinta el bloque CUENTAS sin reventar (la sección existe)",
   'bloque-cuentas' in html and '4 · CUENTAS' in html)
ok("el HTML pinta el bloque MODELO vs REALIDAD (bloque 6, con datos reales agregados)",
   'bloque-modelo' in html and '6 · MODELO vs REALIDAD' in html)

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
