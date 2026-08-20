# -*- coding: utf-8 -*-
"""deteccion_liquidacion.py · D8.3 · ORDEN_DE_TRABAJO_D8.md §1 ·
10_SEGURIDAD.md §7, hueco 1

"Si `leer_posicion(prop)` pasa a cero SIN una orden nuestra que lo
explique -> el proveedor ha liquidado -> cerrar el hedge inmediatamente,
anotar el evento, N2."

Este módulo no vigila nada por su cuenta ni mantiene hilo propio -- es una
comprobación de un instante (`detecta_liquidacion_forzosa`) y una reacción
(`resuelve_liquidacion_forzosa`) que D8.4 (`bucle_del_dia`, todavía sin
construir) llamará en cada vuelta de sondeo, con lo que ese bucle YA sabe
en ese instante: cuánta posición prop cree tener el bot
(`cantidad_esperada`) y qué `order_id` propios ha colocado para esa pata
(el bracket de D8.2, y cualquier `aplanar()` de cierre).

PROHIBIDO (mismo principio que el resto de `bot/`): no decide sizing ni
sesión -- solo lee el puerto (`leer_posicion`/`leer_estado_orden`) y, si
hace falta reaccionar, reutiliza `_aplana_hasta_confirmar()` de
`protocolo_dos_patas.py` tal cual está, sin reimplementar nada de su
lógica de reintento (misma disciplina que evitó extraer/tocar
`sesion.py`: reutilizar en vez de bifurcar)."""
import time

from bot.protocolo_dos_patas import _aplana_hasta_confirmar


def detecta_liquidacion_forzosa(adaptador, cuenta_prop, instrumento_prop,
                                 cantidad_esperada, ordenes_propias_conocidas):
    """True si la posición prop real es CERO, el bot esperaba tener una
    posición distinta de cero (`cantidad_esperada`), y NINGUNA orden propia
    DE CIERRE conocida (`ordenes_propias_conocidas`: los `order_id` de
    SALIDA que el bot ha colocado sobre esa pata -- el bracket de D8.2,
    cualquier `aplanar()` de cierre) está en estado `LLENA`. Si alguna SÍ lo
    está, el cierre a cero lo explica una orden nuestra -- no es
    liquidación forzosa, es el resultado normal de nuestro propio
    bracket/cierre.

    OJO: `ordenes_propias_conocidas` son órdenes de CIERRE, nunca la orden
    de APERTURA que abrió la posición -- esa, por construcción, siempre
    está `LLENA` (así se llegó a tener posición) y no dice nada sobre si el
    cierre a cero fue nuestro; incluirla produciría un falso negativo
    permanente (nunca se detectaría ninguna liquidación forzosa mientras el
    `order_id` de apertura siga en la lista).

    No mantiene estado entre llamadas: D8.4 la llama en cada vuelta de
    sondeo con lo que sabe en ESE instante -- si `ordenes_propias_conocidas`
    no incluye la orden de cierre que de verdad cerró la posición, es un
    error de quien llama (no le pasó la lista completa), no de esta
    función."""
    cantidad_real, _ = adaptador.leer_posicion(cuenta_prop, instrumento_prop)
    if cantidad_real != 0 or cantidad_esperada == 0:
        return False
    for order_id in ordenes_propias_conocidas:
        if adaptador.leer_estado_orden(order_id) == 'LLENA':
            return False
    return True


def resuelve_liquidacion_forzosa(adaptador_hedge, cuenta_hedge, instrumento_hedge,
                                  eventos=None, reloj=None, dormir=None,
                                  max_reintentos=10000, intervalo_reintento_s=0.01):
    """Reacción de D8.3: cerrar el hedge INMEDIATAMENTE (la pata prop ya no
    existe -- el proveedor la liquidó, no hay nada que cerrar ahí) y anotar
    el evento. Reutiliza `_aplana_hasta_confirmar` de `protocolo_dos_patas`
    -- mismo insistir-hasta-confirmar-la-posición-en-cero que ya usa
    `cierra_las_dos_patas`, aplicado a una sola pata.

    El nivel N2 (10_SEGURIDAD.md §3: "PLANO Y PARADO HOY") lo declara quien
    llama (D8.4 / `bot/seguridad.py`, todavía sin construir) al ver
    `tipo == 'LIQUIDACION_FORZOSA'` en los eventos devueltos -- este módulo
    NO conoce la escalera N0-N4, solo reporta el hecho (mismo principio que
    el resto de `bot/`: aquí no se decide, se ejecuta y se informa).

    Devuelve {cerrado: bool, intentos: int, eventos: [...]}."""
    reloj = reloj or time.monotonic
    dormir = dormir or time.sleep
    eventos = eventos if eventos is not None else []
    eventos.append(dict(tipo='LIQUIDACION_FORZOSA', cuenta_hedge=cuenta_hedge,
                         instrumento_hedge=instrumento_hedge, nivel_propuesto='N2',
                         motivo='leer_posicion(prop)=0 sin orden propia que lo explique'))
    cerrado, intentos = _aplana_hasta_confirmar(
        adaptador_hedge, cuenta_hedge, instrumento_hedge, reloj, dormir, eventos,
        'hedge_tras_liquidacion_forzosa', max_reintentos, intervalo_reintento_s)
    return dict(cerrado=cerrado, intentos=intentos, eventos=eventos)
