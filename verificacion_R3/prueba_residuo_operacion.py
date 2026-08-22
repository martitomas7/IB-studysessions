# -*- coding: utf-8 -*-
"""D9 §3.4/3.6 fusionadas (AUTORIZACION_3_6_CERRADA.md, autorización R6,
22-08-2026) -- la pieza núcleo del residuo operación a operación: corre
`bot/bucle_del_dia.py` UN día real, EN VIVO, por el bucle de tiempo
concurrente (`bot/bucle_de_tiempo.py`), con `dir_residuo` puesto, y
comprueba de punta a punta:

  1. Persistencia de `sizing_G`/`sizing_H`/`sizing_fric`/`sizing_Mm` en
     `st['eval']` -- CON LA ASERCIÓN EXPLÍCITA DEL `H` que exige §5 de la
     autorización (espiando `sizing.plan()` para saber, con certeza, qué
     `H` recibió de verdad -- no una suposición sobre el código).
  2. El esquema enriquecido de `residuo_operacion` en los dos puntos de
     emisión (`protocolo_dos_patas.py` para la entrada, `resolucion_en_vivo.py`
     para la salida).
  3. El `residuo_dia` reconstruido por `bot/residuo_diario.py` vía el
     oráculo offline sobre las barras reales.
  4. R3: una implementación de la persistencia de `H` deliberadamente rota
     (usa el `H` YA MUTADO en vez del que plan() recibió) para confirmar
     que la aserción del punto 1 SÍ la cazaría.
  5. R3: `calcula_residuo_dia()` con un `dia_real` corrompido a mano, para
     confirmar que el residuo (ya con datos reales de esta corrida, no
     sintéticos) discrimina de verdad."""
import json
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import bucle_del_dia as BDD
from bot import config, estado as E, residuo_diario
from bot import sizing as SIZING_MOD
from bot.adaptador_falso import AdaptadorFalso
from bot.fuente_barras import Barra, ContextoDia

_, checksum = config.cargar()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


class FuenteEnVivoPlana:
    """Un día, barras COMPLETAMENTE PLANAS (mismo precio que el fill de
    apertura por defecto de AdaptadorFalso, 100.0) -- el bracket nunca lo
    toca ninguna barra (mismo principio que prueba_bucle_del_dia_liquidacion.py),
    así que el día se resuelve SIEMPRE por CAMPANA (fin de sesión, ninguna
    pata llenó) al llegar a `tope_barras` -- el caso más simple de fabricar
    de forma determinista para probar el esquema enriquecido y el residuo."""

    def __init__(self, precio_flat=100.0, tope_barras=50):
        self.precio_flat = precio_flat
        self.tope_barras = tope_barras
        self._dia_abierto = False
        self._b = -1

    def dia_disponible(self):
        return not self._dia_abierto

    def abre_dia(self):
        self._dia_abierto = True
        self._b = -1
        return ContextoDia()   # direccion=None -> bucle_del_dia sortea de verdad

    def siguiente_barra(self):
        self._b += 1
        p = self.precio_flat
        return Barra(b=self._b, ph=p, pl=p, pc=p,
                     es_ultima_barra_operable=(self._b >= self.tope_barras))

    def cierra_dia(self):
        pass


class RngFijo:
    """Determinista: 0.1 -- ventana '22h' (barra_inicio=0) y dirección
    larga (0.1 < 0.5); ninguna de las dos importa para un camino plano,
    solo hace falta que sea REPRODUCIBLE."""
    def random(self):
        return 0.1


DIR = "/tmp/prueba_residuo_operacion"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)
DIR_RESIDUO = os.path.join(DIR, "residuo")

CUENTA_HEDGE_EVAL, CUENTA_PROP_EVAL = "CH-EVAL", "CP-EVAL"
CUENTA_HEDGE_FUN, CUENTA_PROP_FUN = "CH-FUN", "CP-FUN"
INSTRUMENTO_PROP = "MES"

ruta_estado = os.path.join(DIR, "estado.json")
ruta_nivel = os.path.join(DIR, "nivel.json")
E.guardar(E.nuevo("v10", checksum), ruta_estado)

adaptador = AdaptadorFalso()
fuente = FuenteEnVivoPlana()

# --- espía de sizing.plan(): qué H (y G/fric) recibió DE VERDAD cada llamada ---
_capturados = []
_orig_plan = SIZING_MOD.plan
def _plan_espia(*args, **kwargs):
    _capturados.append((kwargs.get('G'), kwargs.get('H'), kwargs.get('fric')))
    return _orig_plan(*args, **kwargs)
SIZING_MOD.plan = _plan_espia

print("=== bucle_del_dia() EN VIVO, 1 día, camino plano (resuelve por CAMPANA) ===")
try:
    st_final = BDD.bucle_del_dia(
        fuente, adaptador,
        cuenta_hedge_eval=CUENTA_HEDGE_EVAL, cuenta_prop_eval=CUENTA_PROP_EVAL,
        cuenta_hedge_funded=CUENTA_HEDGE_FUN, cuenta_prop_funded=CUENTA_PROP_FUN,
        instrumento_prop=INSTRUMENTO_PROP,
        ruta_estado=ruta_estado, ruta_nivel=ruta_nivel,
        ruta_ordenes=os.path.join(DIR, "ordenes"), ruta_lock=os.path.join(DIR, "bot.lock"),
        dir_instantaneas=os.path.join(DIR, "instantaneas"), dias_retenidos=5,
        ruta_diario=os.path.join(DIR, "diario.jsonl"), fase='plena',
        rng=RngFijo(), dormir=lambda s: None, dir_residuo=DIR_RESIDUO)
finally:
    SIZING_MOD.plan = _orig_plan   # nunca dejar el espía puesto más allá de esta prueba

ok("bucle_del_dia() no devolvió None", st_final is not None)
ok("se procesó 1 día", st_final is not None and st_final['dia_negociacion'] == 1)
ok("eval SÍ llegó a abrir hoy (k>0 -- si no, esta prueba entera no ejercita nada)",
   st_final['eval']['k'] > 0, st_final['eval']['k'])

print("\n=== 1. Persistencia de sizing_G/H/fric/Mm (D9 §3.6 Capa A) ===")
ev = st_final['eval']
for clave in ('sizing_G', 'sizing_H', 'sizing_fric', 'sizing_Mm'):
    ok(f"eval.{clave} presente y numérico", clave in ev and isinstance(ev[clave], (int, float)),
       ev.get(clave))

triple_persistido = (ev['sizing_G'], ev['sizing_H'], ev['sizing_fric'])
ok("ASERCIÓN EXPLÍCITA (exigida por la autorización): el (G,H,fric) persistido "
   "es EXACTAMENTE uno de los que sizing.plan() recibió de verdad esta corrida -- "
   "no una suposición sobre el código, un hecho espiado en la propia llamada",
   triple_persistido in _capturados, (triple_persistido, _capturados))

print("\n=== 2. Esquema enriquecido: residuo_operacion en los dos puntos de emisión ===")
ruta_eventos = os.path.join(DIR_RESIDUO, "eventos_0001.jsonl")
ok("el fichero de eventos del día 1 SÍ se escribió", os.path.isfile(ruta_eventos), ruta_eventos)
eventos_leidos = [json.loads(l) for l in open(ruta_eventos)] if os.path.isfile(ruta_eventos) else []
por_tipo = {}
for e in eventos_leidos:
    por_tipo.setdefault(e['tipo'], []).append(e)

ok("hay eventos 'divergencia_fill' (agregado de siempre, sin tocar)",
   len(por_tipo.get('divergencia_fill', [])) >= 1)
res_op = por_tipo.get('residuo_operacion', [])
ok("hay al menos 2 'residuo_operacion' de ENTRADA (una por pata: hedge y prop)",
   sum(1 for r in res_op if r['tipo_salida'] == 'entrada') >= 2,
   [r['pata'] for r in res_op if r['tipo_salida'] == 'entrada'])
ok("hay al menos 1 'residuo_operacion' de SALIDA por CAMPANA (pata prop)",
   any(r['tipo_salida'] == 'campana' and r['pata'] == 'prop' for r in res_op), res_op)

CLAVES_RESIDUO_OP = {'tipo', 'pata', 'tipo_salida', 'tipo_orden', 'nivel_pedido', 'fill_obtenido',
                     'desviacion_ticks', 'm', 'contratos', 'order_id', 'feed_origen', 'ts_feed',
                     'ts_feed_motivo', 'ts_decision', 'ts_orden', 'ts_fill_broker',
                     'ts_fill_broker_motivo', 'ts_fill_recibido', 'ts_fill_recibido_motivo'}
ok("TODOS los registros 'residuo_operacion' tienen exactamente el esquema del §5",
   all(set(r) == CLAVES_RESIDUO_OP for r in res_op),
   [sorted(set(r) ^ CLAVES_RESIDUO_OP) for r in res_op if set(r) != CLAVES_RESIDUO_OP])

entrada_hedge = next(r for r in res_op if r['tipo_salida'] == 'entrada' and r['pata'] == 'hedge')
ok("entrada: tipo_orden='mercado' (abrir() nunca lleva precio)",
   entrada_hedge['tipo_orden'] == 'mercado')
ok("entrada: nivel_pedido=None (no hay 'nivel pedido' en una orden de mercado, R2: no se inventa)",
   entrada_hedge['nivel_pedido'] is None)
ok("entrada: ts_feed=None con motivo (AdaptadorFalso no simula un feed independiente)",
   entrada_hedge['ts_feed'] is None and bool(entrada_hedge['ts_feed_motivo']))
ok("entrada: ts_fill_broker YA es un número real (la orden de entrada llena en el acto)",
   isinstance(entrada_hedge['ts_fill_broker'], (int, float)))

salida_campana = next(r for r in res_op if r['tipo_salida'] == 'campana')
ok("salida por campana: tipo_orden='mercado'", salida_campana['tipo_orden'] == 'mercado')
ok("salida por campana: nivel_pedido=None (cierre a mercado, sin precio pedido)",
   salida_campana['nivel_pedido'] is None)
ok("salida por campana: desviacion_ticks=None (no hay nivel pedido contra el que medir)",
   salida_campana['desviacion_ticks'] is None)
ok("salida por campana: fill_obtenido == precio_flat (100.0, el camino es plano)",
   abs(salida_campana['fill_obtenido'] - 100.0) < 1e-9, salida_campana['fill_obtenido'])
ok("salida por campana: m viene del DetectorEnVivo (det_diagnostico.m), no None",
   salida_campana['m'] is not None)

print("\n=== 3. residuo_dia: el oráculo offline sobre las barras reales ===")
res_dia = por_tipo.get('residuo_dia', [])
ok("hay exactamente 1 'residuo_dia' (un slot activo hoy: eval)", len(res_dia) == 1, res_dia)
rd = res_dia[0]
ok("residuo_dia.slot == 'eval'", rd['slot'] == 'eval')
ok("camino plano, fills exactos (sin ruido) -> mismo_desenlace True", rd['mismo_desenlace'] is True, rd)
ok("camino plano, fills exactos -> residuo_total_usd ~ 0", abs(rd['residuo_total_usd']) < 1e-6,
   rd['residuo_total_usd'])
ok("residuo_dia trae dia_teorico Y dia_real (para diagnosticar sin tener que rehacer el cálculo)",
   'dia_teorico' in rd and 'dia_real' in rd)

print("\n=== 4. R3: la aserción del H SÍ cazaría la persistencia rota (H mutado, no el usado) ===")
# La versión ROTA persistiría el H DESPUÉS de sumarle el hedge_dolares de hoy
# (justo el error que la autorización pidió blindar) -- se reconstruye a mano
# aquí, sin tocar ciclo_vida.py, para demostrar que discrimina.
h_mutado_roto = ev['sizing_H'] + rd['dia_real']['hedge_dolares']
triple_roto = (ev['sizing_G'], h_mutado_roto, ev['sizing_fric'])
ok("el H REAL (usado por plan()) SÍ está entre los capturados", triple_persistido in _capturados)
ok("el H MUTADO (roto, post-hedge_dolares de hoy) NO está entre los capturados -- "
   "la aserción de la Parte 1 SÍ habría cazado este bug si ciclo_vida.py lo tuviera",
   triple_roto not in _capturados or rd['dia_real']['hedge_dolares'] == 0.0,
   (triple_roto, rd['dia_real']['hedge_dolares']))

print("\n=== 5. R3: calcula_residuo_dia() discrimina un dia_real corrompido a mano ===")
dia_real_corrupto = dict(rd['dia_real'])
dia_real_corrupto['dx_puntos'] += 5.0   # fabricar un deslizamiento de 5 puntos que NO ocurrió
residuo_corrupto = residuo_diario.calcula_residuo_dia(rd['dia_teorico'], dia_real_corrupto)
ok("con un dia_real corrompido a mano (+5 puntos), el residuo YA NO es ~0 -- discrimina de verdad",
   abs(residuo_corrupto['residuo_dx_puntos'] - 5.0) < 1e-9, residuo_corrupto)

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
