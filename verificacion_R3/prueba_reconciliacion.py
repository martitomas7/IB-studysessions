# -*- coding: utf-8 -*-
"""D8.4, paso 7: bot/reconciliacion.py -- las filas de 07_ADAPTADOR_NT8.md
§6, una por una, contra reconcilia_arranque(), verificando que las
reacciones de bot/seguridad.py se disparan correctamente. También cierra
la puerta R3 completa de D8.5 (idempotencia de órdenes): matar el
"proceso" entre escribe_intencion y marca_resultado, reiniciar, y
confirmar que reconcilia_arranque() retro-completa la intención sin que
AdaptadorFalso reciba una segunda orden de apertura."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import config, estado as E, idempotencia_ordenes as IO, reconciliacion as REC, seguridad as SEG
from bot.adaptador_falso import AdaptadorFalso

_, checksum = config.cargar()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


DIR = "/tmp/prueba_reconciliacion"
CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES = "CH-EVAL", "CP-EVAL", "CH-FUN", "CP-FUN", "MES"
# OJO (bug real de la propia prueba, cazado al EJECUTARLA): reconciliacion.py
# resuelve el instrumento del HEDGE internamente vía
# cfg.hedge_broker.instrumento -- NO es el literal 'MES' que el resto de este
# fichero usa como marcador para el instrumento de la PROP (ese sí lo elige
# libremente el llamador, vía el parámetro instrumento_prop). Abrir la pata
# hedge con el literal 'MES' hacía que reconciliacion.py la buscara bajo una
# clave distinta (cuenta, 'MES (Micro E-mini S&P 500)') y la viera SIEMPRE en
# cero -- "una sola pata" en todos los casos, incluida la fila 5 (CUBIERTO).
MES_HEDGE = config.obtener().hedge_broker.instrumento


def estado_base():
    st = E.nuevo("v10", checksum)
    st["eval"]["activa"] = False
    st["funded"]["activa"] = False
    return st


def prepara():
    shutil.rmtree(DIR, ignore_errors=True)
    os.makedirs(DIR)
    return os.path.join(DIR, "nivel.json"), os.path.join(DIR, "ordenes")


print("=== Fila 1: 'una sola pata' (posición prop sin hedge) -- el fallo más caro posible ===")
ruta_nivel, ruta_ordenes = prepara()
a = AdaptadorFalso()
st = estado_base()
st["eval"]["activa"] = True
st["eval"]["m"], st["eval"]["k"] = 4, 10
oid = a.abrir(CP_EVAL, MES, 1, 10)
a.leer_estado_orden(oid)   # prop viva, hedge NUNCA se abrió
r = REC.reconcilia_arranque(a, st, CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES, ruta_nivel, ruta_ordenes)
ok("debe_operar = False", r['debe_operar'] is False, r)
ok("eval: motivo VIOLACION_TAMANOS (una pata sola, fuera de ventana de transición)",
   r['eval']['motivo'] == 'VIOLACION_TAMANOS', r['eval'])
ok("el nivel de seguridad sube a N3 (alerta máxima, exige humano)",
   SEG.nivel_actual(ruta_nivel) == 'N3', SEG.nivel_actual(ruta_nivel))
ok("la prop queda cerrada por la propia reconciliación (no se deja viva)",
   a.leer_posicion(CP_EVAL, MES)[0] == 0)

print("\n=== Fila 2: posición residual en cuenta que estado.json cree CERRADA ===")
ruta_nivel, ruta_ordenes = prepara()
a = AdaptadorFalso()
st = estado_base()   # eval.activa = False -- estado.json cree que no hay nada
oid_h = a.abrir(CH_EVAL, MES_HEDGE, -1, 4); a.leer_estado_orden(oid_h)
oid_p = a.abrir(CP_EVAL, MES, 1, 10); a.leer_estado_orden(oid_p)
r = REC.reconcilia_arranque(a, st, CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES, ruta_nivel, ruta_ordenes)
ok("debe_operar = False (posición residual sin que estado.json la explique)", r['debe_operar'] is False)
ok("nivel sube a N3", SEG.nivel_actual(ruta_nivel) == 'N3')

print("\n=== Fila 3: tamaño que NO coincide con k/m esperados (fill parcial no registrado) ===")
ruta_nivel, ruta_ordenes = prepara()
a = AdaptadorFalso()
st = estado_base()
st["eval"]["activa"] = True
st["eval"]["m"], st["eval"]["k"] = 4, 10
oid_h = a.abrir(CH_EVAL, MES_HEDGE, -1, 4); a.leer_estado_orden(oid_h)
oid_p = a.abrir(CP_EVAL, MES, 1, 7); a.leer_estado_orden(oid_p)   # 7, se esperaban 10
r = REC.reconcilia_arranque(a, st, CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES, ruta_nivel, ruta_ordenes)
ok("debe_operar = False (tamaño no corresponde)", r['debe_operar'] is False)
ok("eval: motivo VIOLACION_TAMANOS", r['eval']['motivo'] == 'VIOLACION_TAMANOS')
ok("nivel sube a N3", SEG.nivel_actual(ruta_nivel) == 'N3')

print("\n=== Fila 4: todo cuadra, SIN posición viva -- día nuevo o reinicio entre sesiones ===")
ruta_nivel, ruta_ordenes = prepara()
a = AdaptadorFalso()
st = estado_base()   # las dos cuentas planas, las dos inactivas
r = REC.reconcilia_arranque(a, st, CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES, ruta_nivel, ruta_ordenes)
ok("debe_operar = True", r['debe_operar'] is True, r)
ok("eval: motivo PLANO_DIA_NUEVO", r['eval']['motivo'] == 'PLANO_DIA_NUEVO')
ok("funded: motivo PLANO_DIA_NUEVO", r['funded']['motivo'] == 'PLANO_DIA_NUEVO')
ok("el nivel sigue en N0 (nada que alertar)", SEG.nivel_actual(ruta_nivel) == 'N0')

print("\n=== Fila 5: todo cuadra Y hay posición viva de las dos patas -- REINICIO A MEDIA SESIÓN "
      "(no es un error, NO se re-ejecuta la entrada) ===")
ruta_nivel, ruta_ordenes = prepara()
a = AdaptadorFalso()
st = estado_base()
st["eval"]["activa"] = True
st["eval"]["m"], st["eval"]["k"] = 4, 10
oid_h = a.abrir(CH_EVAL, MES_HEDGE, -1, 4); a.leer_estado_orden(oid_h)
oid_p = a.abrir(CP_EVAL, MES, 1, 10); a.leer_estado_orden(oid_p)   # exactamente m=4, k=10
r = REC.reconcilia_arranque(a, st, CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES, ruta_nivel, ruta_ordenes)
ok("debe_operar = True (reanuda, NO se aborta)", r['debe_operar'] is True, r)
ok("eval: motivo CUBIERTO_REANUDA", r['eval']['motivo'] == 'CUBIERTO_REANUDA')
ok("la posición de las dos patas SIGUE viva (nunca se toca en este caso)",
   a.leer_posicion(CH_EVAL, MES_HEDGE)[0] == -4 and a.leer_posicion(CP_EVAL, MES)[0] == 10)
ok("el nivel sigue en N0 -- reinicio a media sesión no es una degradación",
   SEG.nivel_actual(ruta_nivel) == 'N0')

print("\n=== D8.5 completo: matar el proceso ENTRE escribe_intencion y marca_resultado, reiniciar, "
      "y confirmar que NO se manda una segunda orden de apertura ===")
ruta_nivel, ruta_ordenes = prepara()
a = AdaptadorFalso()
st = estado_base()
st["eval"]["activa"] = True
st["eval"]["m"], st["eval"]["k"] = 4, 10
intent_id = "1:eval:0:abre"
# "el proceso murió" justo después de escribir la intención, ANTES de mandar
# la orden de verdad y ANTES de marcar el resultado -- exactamente la
# ventana que D8.5 tiene que proteger.
IO.escribe_intencion(ruta_ordenes, intent_id, dict(cuenta_hedge=CH_EVAL, cuenta_prop=CP_EVAL, m=4, k=10))
ok("tras la 'caída', resultado_de() sigue None -- ambiguo: ¿se mandó la orden o no?",
   IO.resultado_de(ruta_ordenes, intent_id) is None)
ok("intenciones_sin_resultado() detecta la ambigüedad del día 1", intent_id in
   IO.intenciones_sin_resultado(ruta_ordenes, dia_negociacion=1))

# "reinicio": el bot arranca, reconcilia ANTES de decidir si reintenta nada.
# Como la posición real está en CERO (la orden nunca llegó a mandarse de
# verdad -- AdaptadorFalso.abrir() nunca se llamó), la reconciliación ve
# PLANO, no CUBIERTO -- así que NO retro-completa nada; el estado sigue
# siendo "sin resultado", y es tarea de ciclo_vida.py/bucle_del_dia.py, NO
# de esta prueba, decidir si abre_las_dos_patas() se llama esta vez (con un
# intent_id NUEVO -- nunca reintenta el mismo intent_id a ciegas).
r_reinicio = REC.reconcilia_arranque(a, st, CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES,
                                      ruta_nivel, ruta_ordenes)
ok("tras el reinicio con posición real en CERO, la reconciliación NO retro-completa nada "
   "(no había nada que reconciliar, el bróker nunca vio la orden)",
   IO.resultado_de(ruta_ordenes, intent_id) is None)
ok("PLANO_DIA_NUEVO -- el bot puede intentar de nuevo con normalidad", r_reinicio['eval']['motivo']
   == 'PLANO_DIA_NUEVO')
ok("AdaptadorFalso NUNCA recibió ninguna orden real (la caída fue antes de abrir_las_dos_patas)",
   len(a.ordenes) == 0)

print("\n=== D8.5, el otro caso: 'caída' DESPUÉS de que el bróker SÍ recibió la orden -- "
      "reconciliación la encuentra CUBIERTA y retro-completa, sin mandar una segunda ===")
ruta_nivel, ruta_ordenes = prepara()
a = AdaptadorFalso()
st = estado_base()
st["eval"]["activa"] = True
st["eval"]["m"], st["eval"]["k"] = 4, 10
intent_id = "1:eval:0:abre"
IO.escribe_intencion(ruta_ordenes, intent_id, dict(cuenta_hedge=CH_EVAL, cuenta_prop=CP_EVAL, m=4, k=10))
# esta vez SÍ se manda de verdad (el proceso murió DESPUÉS de mandar, ANTES
# de marca_resultado -- la orden real ya existe en el bróker).
oid_h = a.abrir(CH_EVAL, MES_HEDGE, -1, 4); a.leer_estado_orden(oid_h)
oid_p = a.abrir(CP_EVAL, MES, 1, 10); a.leer_estado_orden(oid_p)
n_ordenes_antes = len(a.ordenes)
r_reinicio2 = REC.reconcilia_arranque(a, st, CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES,
                                       ruta_nivel, ruta_ordenes)
ok("la reconciliación ve CUBIERTO (la posición SÍ está, con el tamaño correcto)",
   r_reinicio2['eval']['motivo'] == 'CUBIERTO_REANUDA', r_reinicio2)
res_retro = IO.resultado_de(ruta_ordenes, intent_id)
ok("retro-completa la intención con reconciliado=True -- ya NO queda ambigua",
   res_retro is not None and res_retro.get('reconciliado') is True, res_retro)
ok("intenciones_sin_resultado() ya no la ve pendiente", intent_id not in
   IO.intenciones_sin_resultado(ruta_ordenes, dia_negociacion=1))
ok("NUNCA se mandó una segunda orden de apertura -- AdaptadorFalso sigue con las mismas 2 "
   "órdenes de antes de reconciliar", len(a.ordenes) == n_ordenes_antes, len(a.ordenes))

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
