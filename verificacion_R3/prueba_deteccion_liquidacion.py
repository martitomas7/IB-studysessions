# -*- coding: utf-8 -*-
"""R3 (D8.3, ORDEN_DE_TRABAJO_D8.md §1, 10_SEGURIDAD.md §7 hueco 1):
`bot/deteccion_liquidacion.py` en proceso, contra `AdaptadorFalso`
directo. La puerta end-to-end (canal de control del simulador real) vive
en `verificacion_R3/integracion_proceso_real/prueba_liquidacion_forzosa.py`
-- este fichero cubre la lógica en aislamiento, más rápido de iterar."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot.adaptador_falso import AdaptadorFalso
from bot.deteccion_liquidacion import detecta_liquidacion_forzosa, resuelve_liquidacion_forzosa

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


print("=== 1. camino normal: la prop cierra sola vía SU PROPIA orden -- no es liquidación forzosa ===")
a = AdaptadorFalso()
oid_prop = a.abrir("CTA-PROP", "MES", 1, 10)   # fill_en_s por defecto = 0.0 -> llena al instante
a.leer_estado_orden(oid_prop)  # fuerza el avance del estado (patrón ya usado en el resto de R3)
oid_cierre = a.aplanar("CTA-PROP", "MES")
a.leer_estado_orden(oid_cierre)
ok("tras cerrar con nuestra propia orden, la posición real es 0",
   a.leer_posicion("CTA-PROP", "MES")[0] == 0)
es_liq = detecta_liquidacion_forzosa(a, "CTA-PROP", "MES", cantidad_esperada=10,
                                      ordenes_propias_conocidas=[oid_prop, oid_cierre])
ok("NO se detecta como liquidación forzosa (una orden propia SÍ está LLENA y lo explica)",
   es_liq is False, es_liq)

print("\n=== 2. liquidación forzosa real: la posición cae a cero SIN ninguna orden propia LLENA ===")
a2 = AdaptadorFalso()
oid_prop2 = a2.abrir("CTA-PROP", "MES", 1, 10)
a2.leer_estado_orden(oid_prop2)
ok("posición real = 10 tras la apertura", a2.leer_posicion("CTA-PROP", "MES")[0] == 10)
# se fabrica un bracket EN REPOSO que NO ha llenado (fill_en_s enorme -> nunca)
oid_stop = a2._nueva_orden('aplanar', "CTA-PROP", "MES", -1, 10, {'fill_en_s': 9999.0})
a2.leer_estado_orden(oid_stop)
ok("el bracket sigue vivo (ACEPTADA, no LLENA) cuando el proveedor liquida",
   a2.leer_estado_orden(oid_stop) != 'LLENA')
a2.fuerza_posicion_externa("CTA-PROP", "MES", 0)   # el proveedor liquida, sin orden nuestra
ok("posición real = 0 tras la liquidación externa", a2.leer_posicion("CTA-PROP", "MES")[0] == 0)
# OJO: solo se pasan las órdenes de CIERRE (oid_stop) -- la de apertura
# (oid_prop2) NUNCA se pasa aquí, ver docstring de la función.
es_liq2 = detecta_liquidacion_forzosa(a2, "CTA-PROP", "MES", cantidad_esperada=10,
                                       ordenes_propias_conocidas=[oid_stop])
ok("SÍ se detecta como liquidación forzosa (ninguna orden de CIERRE propia está LLENA)",
   es_liq2 is True, es_liq2)
print("\n=== 2b. trampa fijada: pasar por error la orden de APERTURA no debe enmascarar la detección ===")
es_liq2b = detecta_liquidacion_forzosa(a2, "CTA-PROP", "MES", cantidad_esperada=10,
                                        ordenes_propias_conocidas=[oid_prop2])
ok("si quien llama pasa por error la orden de apertura (siempre LLENA), "
   "la función documenta que eso produce un falso negativo -- responsabilidad del llamador, "
   "pinnned aquí para que D8.4 nunca lo haga por accidente",
   es_liq2b is False, es_liq2b)

print("\n=== 3. resuelve_liquidacion_forzosa(): cierra el hedge de inmediato y anota el evento ===")
a3 = AdaptadorFalso()
oid_hedge = a3.abrir("CTA-HEDGE", "MES", -1, 4)
a3.leer_estado_orden(oid_hedge)
ok("el hedge está vivo (posición != 0) antes de resolver la liquidación",
   a3.leer_posicion("CTA-HEDGE", "MES")[0] != 0)
r = resuelve_liquidacion_forzosa(a3, "CTA-HEDGE", "MES")
ok("el hedge queda confirmado en cero", r['cerrado'] is True, r)
ok("se anota el evento LIQUIDACION_FORZOSA con nivel_propuesto='N2'",
   any(e.get('tipo') == 'LIQUIDACION_FORZOSA' and e.get('nivel_propuesto') == 'N2'
       for e in r['eventos']), r['eventos'])
ok("la posición del hedge queda confirmada en cero de verdad",
   a3.leer_posicion("CTA-HEDGE", "MES")[0] == 0)

print("\n=== 4. no hay falso positivo con la cuenta ya plana desde el principio (nunca hubo posición) ===")
a4 = AdaptadorFalso()
es_liq4 = detecta_liquidacion_forzosa(a4, "CTA-PROP", "MES", cantidad_esperada=0,
                                       ordenes_propias_conocidas=[])
ok("cantidad_esperada=0 (nunca se abrió nada) nunca se marca como liquidación forzosa",
   es_liq4 is False, es_liq4)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
