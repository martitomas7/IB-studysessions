# -*- coding: utf-8 -*-
"""R3 (D8.2, ORDEN_DE_TRABAJO_D8.md §1): órdenes en reposo (bracket OCO) en
`bot/adaptador_falso.py`, en proceso. La puerta end-to-end (fabricar en el
simulador un día en que las DOS podrían dispararse y demostrar que solo
una queda) vive en
`verificacion_R3/integracion_proceso_real/prueba_bracket_ordenes_reposo.py`."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot.adaptador_falso import AdaptadorFalso

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


print("=== R3-0 (pin): cancelar() sobre una orden LLENA (camino sin grupo) devuelve LLENA ===")
a0 = AdaptadorFalso()
oid = a0.abrir("CTA", "MES", 1, 4)
a0.leer_estado_orden(oid)  # fuerza el avance (fill_en_s=0.0 por defecto)
ok("estado ya es LLENA antes de cancelar", a0.leer_estado_orden(oid) == 'LLENA')
r0 = a0.cancelar(oid)
ok("cancelar() sobre una orden LLENA devuelve LLENA, no CANCELADA (contrato preexistente)",
   r0 == 'LLENA', r0)

print("\n=== R3-1: coloca_bracket() básico -- dos order_id distintos, ambos ACEPTADA, mismo grupo ===")
a1 = AdaptadorFalso()
b = a1.coloca_bracket("CTA-PROP", "MES", -1, 10, precio_stop=4990.0, precio_limite=5010.0)
ok("dos order_id distintos", b['order_id_stop'] != b['order_id_limite'], b)
ok("stop ACEPTADA", a1.leer_estado_orden(b['order_id_stop']) == 'ACEPTADA')
ok("limite ACEPTADA", a1.leer_estado_orden(b['order_id_limite']) == 'ACEPTADA')
ok("ninguna de las dos auto-llena sola (nunca modela trayectoria de precio)",
   a1.leer_estado_orden(b['order_id_stop']) != 'LLENA'
   and a1.leer_estado_orden(b['order_id_limite']) != 'LLENA')

print("\n=== R3-2: fabrica_resolucion_bracket(pierna='stop') -> stop LLENA, límite CANCELADA ===")
a2 = AdaptadorFalso()
b2 = a2.coloca_bracket("CTA-PROP", "MES", -1, 10, precio_stop=4990.0, precio_limite=5010.0)
a2.fabrica_resolucion_bracket(b2['id_grupo_oco'], 'stop')
ok("stop queda LLENA", a2.leer_estado_orden(b2['order_id_stop']) == 'LLENA')
ok("límite queda CANCELADA (auto-cancel, sin llamar a cancelar() explícitamente)",
   a2.leer_estado_orden(b2['order_id_limite']) == 'CANCELADA')
ok("el fill del stop es exactamente al nivel pedido (precio_fill=None -> pass 1, sin deslizamiento)",
   a2.leer_fill(b2['order_id_stop'])[2] == 4990.0)

print("\n=== R3-3: simétrico con pierna='limite' ===")
a3 = AdaptadorFalso()
b3 = a3.coloca_bracket("CTA-PROP", "MES", -1, 10, precio_stop=4990.0, precio_limite=5010.0)
a3.fabrica_resolucion_bracket(b3['id_grupo_oco'], 'limite')
ok("límite queda LLENA", a3.leer_estado_orden(b3['order_id_limite']) == 'LLENA')
ok("stop queda CANCELADA", a3.leer_estado_orden(b3['order_id_stop']) == 'CANCELADA')

print("\n=== R3-4: ninguna llena; cancelar(order_id_stop) cancela LAS DOS patas ===")
a4 = AdaptadorFalso()
b4 = a4.coloca_bracket("CTA-PROP", "MES", -1, 10, precio_stop=4990.0, precio_limite=5010.0)
r4 = a4.cancelar(b4['order_id_stop'])
ok("cancelar() sobre el stop devuelve CANCELADA", r4 == 'CANCELADA', r4)
ok("el límite (nombrado NUNCA) también queda CANCELADA -- grupo completo",
   a4.leer_estado_orden(b4['order_id_limite']) == 'CANCELADA')

print("\n=== R3-5: cancelar() sobre una pata ya LLENA de un grupo -> devuelve LLENA, "
      "la hermana queda en su estado correcto (ya CANCELADA, no se pisa) ===")
a5 = AdaptadorFalso()
b5 = a5.coloca_bracket("CTA-PROP", "MES", -1, 10, precio_stop=4990.0, precio_limite=5010.0)
a5.fabrica_resolucion_bracket(b5['id_grupo_oco'], 'stop')
r5 = a5.cancelar(b5['order_id_stop'])   # la pata ya LLENA
ok("cancelar() sobre la pata ya LLENA devuelve LLENA (idempotente y veraz)", r5 == 'LLENA', r5)
ok("la hermana sigue CANCELADA (no se pisó ni se re-canceló)",
   a5.leer_estado_orden(b5['order_id_limite']) == 'CANCELADA')

print("\n=== R3-6: fabrica_resolucion_bracket(precio_fill=X) fabrica deslizamiento (pass 2) ===")
a6 = AdaptadorFalso()
b6 = a6.coloca_bracket("CTA-PROP", "MES", -1, 10, precio_stop=4990.0, precio_limite=5010.0)
a6.fabrica_resolucion_bracket(b6['id_grupo_oco'], 'stop', precio_fill=4988.5)
ok("leer_fill() refleja el precio fabricado (4988.5), NO el nivel pedido (4990.0)",
   a6.leer_fill(b6['order_id_stop'])[2] == 4988.5)

print("\n=== R3-11: incidente de doble-fill -- fabrica_doble_fill_bracket() ===")
a7 = AdaptadorFalso()
b7 = a7.coloca_bracket("CTA-PROP", "MES", -1, 10, precio_stop=4990.0, precio_limite=5010.0)
a7.fabrica_doble_fill_bracket(b7['id_grupo_oco'], precio_fill_stop=4990.0, precio_fill_limite=5010.0)
ok("AMBAS patas quedan LLENA (fallo de fidelidad del OCO real, fabricado a propósito)",
   a7.leer_estado_orden(b7['order_id_stop']) == 'LLENA'
   and a7.leer_estado_orden(b7['order_id_limite']) == 'LLENA')
# posición neta: se abrieron k=10 en direccion +1 fuera de este test (no se
# abrió aquí explícitamente); lo que importa es que las DOS órdenes del
# bracket (misma cantidad, misma dirección de cierre) sumaron su efecto dos
# veces -- responsabilidad de D8.4 corregir la posición neta sobrante con
# aplanar(), no de este simulador.
pos7, _ = a7.leer_posicion("CTA-PROP", "MES")
ok("la posición refleja que las DOS patas ejecutaron (doble efecto, sin corrección automática -- "
   "eso es responsabilidad de D8.4, ver ORDEN_DE_TRABAJO_D8.md §1 y la síntesis de diseño previa)",
   pos7 == -20, pos7)   # direccion_cierre=-1, cantidad=10, dos veces

print("\n=== R3: bloqueo (k<1) no coloca ningún bracket -- responsabilidad de quien llama, "
      "coloca_bracket() en sí no valida 'k' (R2: eso viene de sizing.py) ===")
# comprobación de contrato, no de negocio: coloca_bracket() no rechaza
# cantidad=0 por sí sola (no es su responsabilidad decidir si hoy toca
# operar) -- se deja constancia explícita de que la NO-invocación es la
# única barrera real, y vive en D8.4 (ORDEN_DE_TRABAJO_D8.md §5.1, última
# fila: 'no debe colocar ninguna orden').
ok("(nota, no una comprobación ejecutable) el guardián de 'no colocar nada si k<1' pertenece "
   "a D8.4 -- coloca_bracket() es un ejecutor puro, igual que abrir()/aplanar()", True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
