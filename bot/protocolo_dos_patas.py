# -*- coding: utf-8 -*-
"""protocolo_dos_patas.py · D-C (botón de pánico) y sustrato para D8 ·
05_ORDEN_DE_CONSTRUCCION.md

Transcripción literal, rama por rama, del protocolo de `07_ADAPTADOR_NT8.md`
§5.3 (apertura, corregida en su revisión 2 -- la carrera cancelar-vs-fill, y
en su revisión 4 -- el rechazo instantáneo como tercera salida, ver abajo) y
§5.4 (cierre, formalizado en su revisión 3 -- mismo principio, insistiendo en
vez de abortando). Opera contra CUALQUIER objeto que implemente el puerto de
§1 de ese documento (`abrir`/`aplanar`/`cancelar`/`leer_estado_orden`/
`leer_fill`/`leer_posicion`/`hay_conexion`) -- hoy `bot/adaptador_falso.py`
(el "adaptador falso" que `08_LABORATORIO.md` §8 y `DATOS_Y_DASHBOARD.md`
Parte 4 piden para probar esto sin NT8); cuando exista el adaptador NT8 real
de D-A, este módulo sirve sin cambios -- solo cambia qué objeto se le pasa.

Es el módulo que el comando de Clase A "aplanar ambas" del dashboard (D-C,
`08_LABORATORIO.md` §7.4) tiene que llamar -- **nunca** un atajo propio: "Un
botón que aplane las dos patas a la vez reintroduce exactamente la carrera
cancelar-vs-fill que se corrigió en la revisión 2 de `07_ADAPTADOR_NT8.md`."

REGLA GENERAL 1, la misma en apertura y cierre: **un `aplanar()` no se
considera hecho hasta que la POSICIÓN confirma cero** (no el estado de la
última orden -- ver DEFECTO 3 más abajo). Fue un bug real de este módulo,
cazado en su propia verificación R3 (ver `prueba_protocolo_dos_patas.py`):
las primeras versiones de las ramas de aborto de §5.3 llamaban a `aplanar()`
una vez y devolvían sin comprobar el resultado -- exactamente el tipo de
"fire and forget" que la revisión 1 de `07_ADAPTADOR_NT8.md` §5.3 tenía y
que su revisión 2 existe para prohibir. Por eso TODO aplanamiento de este
módulo, sea en un aborto de apertura o en el cierre normal, pasa por
`_aplana_hasta_confirmar()`.

REGLA GENERAL 2 (revisión operador 20-08-2026, DEFECTO 1 de su revisión):
**un rechazo/cancelación INSTANTÁNEO -- antes de que expire el timeout -- es
información cierta y limpia, no ambigua.** Las primeras versiones de este
módulo solo sondeaban hasta `LLENA`, así que un `RECHAZADA` inmediato se
trataba igual que "sigue viva" y se consumía el timeout entero -- en la
FASE PROP eso significaba quedarse con el hedge abierto y desnudo durante
`N` segundos enteros, exactamente la exposición que `N` existe para acotar
(§5.2). Corregido: se sondea contra `ESTADOS_TERMINALES` completo desde el
principio, así que `RECHAZADA`/`CANCELADA` cortan de inmediato, sin
ambigüedad ni alerta máxima -- es un desenlace limpio, no un caso de duda.

REGLA GENERAL 3 (revisión operador 20-08-2026, DEFECTO 2 de su revisión):
**`hay_conexion()` se comprueba de LAS DOS cuentas antes de mandar la
PRIMERA orden.** El puerto de `07_ADAPTADOR_NT8.md` §1 lo dice literal:
"se comprueba antes de cada operación; nunca se asume". Con cualquiera de
las dos conexiones caída, no se abre nada -- ninguna pata, sin excepción
(§7: "si afecta a una APERTURA que aún no confirmó: no se reintenta, se
aborta el día"). El cierre NO lleva este mismo guardián: §7 distingue
explícitamente que un CIERRE con posición real viva SÍ se reintenta con
alerta creciente -- abortar el cierre por conexión caída sería dejar una
pata real sin gestionar, lo contrario de lo que el cierre existe para
evitar. `_aplana_hasta_confirmar()` ya reintenta indefinidamente ante
cualquier fallo (incluida una conexión caída, si el adaptador la refleja
como órdenes que nunca confirman), así que el cierre no necesita un
guardián aparte -- insistir ES la respuesta correcta ahí.

PROHIBIDO (mismo principio que `sesion.py`/`ciclo_vida.py`): este módulo no
decide CUÁNDO abrir ni CUÁNTO -- dirección, `k`, `m` y las cuentas ya vienen
resueltos por quien lo llama. Solo ejecuta la secuencia que la norma fija.
"""
import time

from bot import config

ESTADOS_TERMINALES = frozenset({'LLENA', 'CANCELADA', 'RECHAZADA'})
ESTADOS_RECHAZO_LIMPIO = frozenset({'CANCELADA', 'RECHAZADA'})


def _poll_hasta(adaptador, order_id, terminales, timeout_s, reloj, dormir, intervalo_s=0.01):
    """Sondea `leer_estado_orden(order_id)` hasta que el estado esté en
    `terminales`, o hasta que pasen `timeout_s` segundos (`None` = sin
    límite -- así insiste el cierre, §5.4). Devuelve (estado, agotó_timeout)."""
    t0 = reloj()
    while True:
        estado = adaptador.leer_estado_orden(order_id)
        if estado in terminales:
            return estado, False
        if timeout_s is not None and (reloj() - t0) >= timeout_s:
            return estado, True
        dormir(intervalo_s)


def _aplana_hasta_confirmar(adaptador, cuenta, instrumento, reloj, dormir, eventos,
                             etiqueta, max_reintentos=10000, intervalo_reintento_s=0.01):
    """Llama `aplanar()` y NO lo da por hecho hasta que `leer_posicion()`
    confirma CERO -- no hasta que la ÚLTIMA orden diga `LLENA` (DEFECTO 3,
    revisión operador 20-08-2026: un bróker real puede rechazar una orden de
    cantidad cero -- si la posición YA es cero, el estado de esa orden nunca
    sería 'LLENA' aunque la cuenta ya esté exactamente donde debía estar).
    Si la posición no llega a cero, reintenta (§5.4: 'se reintenta... con
    prioridad creciente sin dejar de intentar'). Se usa tanto en el cierre
    normal (§5.4) como en cualquier aborto de la apertura (§5.3) que tenga
    que aplanar una pata -- un aplanamiento a medias es tan peligroso como
    no haberlo intentado.

    `max_reintentos` es una VÁLVULA DE SEGURIDAD DE INGENIERÍA, no una regla
    de negocio (§5.4 no fija techo; en producción/D8 la escalada de alerta
    no tiene por qué tener límite) -- mismo principio que `TOL`/`65536` de
    `bot/config.py`. Devuelve (confirmado: bool, intentos: int)."""
    cantidad, _ = adaptador.leer_posicion(cuenta, instrumento)
    if cantidad == 0:
        return True, 0   # ya estaba plana -- no se manda nada (evita el pedido de cantidad cero)
    intentos = 0
    while True:
        intentos += 1
        oid = adaptador.aplanar(cuenta, instrumento)
        estado_final, _ = _poll_hasta(adaptador, oid, ESTADOS_TERMINALES, None, reloj, dormir)
        cantidad, _ = adaptador.leer_posicion(cuenta, instrumento)
        if cantidad == 0:
            return True, intentos
        eventos.append(dict(tipo='ALERTA_MAXIMA', motivo=f'aplanar_no_confirma_{etiqueta}',
                             intento=intentos, estado=estado_final, posicion_restante=cantidad))
        if intentos >= max_reintentos:
            return False, intentos
        dormir(intervalo_reintento_s)


def abre_las_dos_patas(adaptador, cuenta_hedge, cuenta_prop, instrumento_prop,
                        direccion, m, k, eventos=None, reloj=None, dormir=None):
    """07_ADAPTADOR_NT8.md §5.3 (revisión 2 corregida, revisión 4 con rechazo
    limpio y guardián de conexión): FASE HEDGE primero, FASE PROP solo con
    el hedge ya confirmado. `eventos`, si se pasa, recoge los eventos de
    laboratorio (timeouts de N/N_hedge, divergencia de precio de fill entre
    las dos patas -- 08_LABORATORIO.md §1.2).

    Devuelve {abierto: bool, order_id_hedge, order_id_prop, motivo (si
    abierto=False)}."""
    reloj = reloj or time.monotonic
    dormir = dormir or time.sleep
    eventos = eventos if eventos is not None else []
    cfg = config.obtener()
    N = cfg.adaptador.timeout_prop_s.valor()
    N_hedge = cfg.adaptador.timeout_hedge_s.valor()
    MES = cfg.hedge_broker.instrumento

    # ---- GUARDIÁN DE CONEXIÓN (DEFECTO 2) -- antes de la PRIMERA orden -----
    hedge_ok = adaptador.hay_conexion(cuenta_hedge)
    prop_ok = adaptador.hay_conexion(cuenta_prop)
    if not (hedge_ok and prop_ok):
        eventos.append(dict(tipo='conexion_caida', hedge_conectado=hedge_ok,
                             prop_conectado=prop_ok, alerta='MAXIMA'))
        return dict(abierto=False, order_id_hedge=None, order_id_prop=None,
                    motivo='conexion_caida_no_se_abre_nada')

    # ---- FASE HEDGE --------------------------------------------------
    oid_hedge = adaptador.abrir(cuenta_hedge, MES, -direccion, m)
    estado, agoto = _poll_hasta(adaptador, oid_hedge, ESTADOS_TERMINALES, N_hedge, reloj, dormir)
    if not agoto and estado in ESTADOS_RECHAZO_LIMPIO:
        # DEFECTO 1: rechazo/cancelación instantáneo -- limpio, sin ambigüedad,
        # nada que aplanar (el hedge nunca se abrió), sin alerta máxima.
        eventos.append(dict(tipo='hedge_rechazado_limpio', order_id=oid_hedge, estado=estado))
        return dict(abierto=False, order_id_hedge=oid_hedge, order_id_prop=None,
                    motivo='hedge_rechazado_no_se_opera_hoy')
    if agoto:
        # 2b: pasa N_hedge sin confirmar y sin rechazo -- sigue viva/parcial
        adaptador.cancelar(oid_hedge)
        estado_final, _ = _poll_hasta(adaptador, oid_hedge, ESTADOS_TERMINALES, None, reloj, dormir)
        evento = dict(tipo='timeout_hedge', order_id=oid_hedge, resultado=estado_final)
        if estado_final == 'CANCELADA':
            eventos.append(evento)
            return dict(abierto=False, order_id_hedge=oid_hedge, order_id_prop=None,
                        motivo='N_hedge_expirado_cancelado')
        elif estado_final == 'LLENA':
            # la cancelación llegó tarde: el hedge SI se ejecutó -- tratar
            # como 2a e ir a FASE PROP con el hedge ya confirmado.
            _, _, evento['precio_fill_hedge'] = adaptador.leer_fill(oid_hedge)
            eventos.append(evento)
        else:
            # PARCIAL / error de cancelación / estado ambiguo
            evento['alerta'] = 'MAXIMA'
            eventos.append(evento)
            _aplana_hasta_confirmar(adaptador, cuenta_hedge, MES, reloj, dormir, eventos,
                                     'hedge_ambiguo_apertura')
            return dict(abierto=False, order_id_hedge=oid_hedge, order_id_prop=None,
                        motivo='hedge_ambiguo_tras_cancelar_aplanado')
    # aquí: o bien no agotó y estado=='LLENA' (2a), o bien agotó+resuelto a LLENA arriba

    # ---- FASE PROP (solo se llega aquí con el hedge YA confirmado) ----
    oid_prop = adaptador.abrir(cuenta_prop, instrumento_prop, direccion, k)
    estado, agoto = _poll_hasta(adaptador, oid_prop, ESTADOS_TERMINALES, N, reloj, dormir)
    if not agoto and estado in ESTADOS_RECHAZO_LIMPIO:
        # DEFECTO 1, lado prop: la prop nunca se abrió, con certeza e
        # instantáneo -- SOLO AHORA (ya lo sabemos con certeza) se aplana el
        # hedge, sin alerta máxima: no es ambiguo.
        eventos.append(dict(tipo='prop_rechazada_limpio', order_id=oid_prop, estado=estado))
        _aplana_hasta_confirmar(adaptador, cuenta_hedge, MES, reloj, dormir, eventos,
                                 'hedge_tras_prop_rechazada')
        return dict(abierto=False, order_id_hedge=oid_hedge, order_id_prop=oid_prop,
                    motivo='prop_rechazada_hedge_aplanado')
    if not agoto:
        # LLENA
        _registra_divergencia(adaptador, oid_hedge, oid_prop, eventos)
        return dict(abierto=True, order_id_hedge=oid_hedge, order_id_prop=oid_prop)

    # 4b: pasa N sin confirmar y sin rechazo -- SIEMPRE se cancela la prop
    # primero, nunca el hedge
    adaptador.cancelar(oid_prop)
    estado_final, _ = _poll_hasta(adaptador, oid_prop, ESTADOS_TERMINALES, None, reloj, dormir)
    evento = dict(tipo='timeout_prop', order_id=oid_prop, resultado=estado_final)
    if estado_final == 'CANCELADA':
        # confirmado que la prop nunca se abrió -- SOLO AHORA se aplana el hedge
        eventos.append(evento)
        _aplana_hasta_confirmar(adaptador, cuenta_hedge, MES, reloj, dormir, eventos,
                                 'hedge_tras_N_expirado')
        return dict(abierto=False, order_id_hedge=oid_hedge, order_id_prop=oid_prop,
                    motivo='N_expirado_prop_cancelada_hedge_aplanado')
    elif estado_final == 'LLENA':
        # la cancelación llegó tarde: la prop SI se ejecutó -- no se toca el
        # hedge, las dos patas están puestas.
        eventos.append(evento)
        _registra_divergencia(adaptador, oid_hedge, oid_prop, eventos)
        return dict(abierto=True, order_id_hedge=oid_hedge, order_id_prop=oid_prop)
    else:
        # PARCIAL / error de cancelación / estado ambiguo: no se puede
        # confirmar cuál es el estado real de NINGUNA de las dos patas --
        # aplanar las dos, en el orden de Arquitectura §7.2 (el inverso),
        # cada una confirmada hasta LLENA antes de pasar a la siguiente.
        evento['alerta'] = 'MAXIMA'
        eventos.append(evento)
        _aplana_hasta_confirmar(adaptador, cuenta_prop, instrumento_prop, reloj, dormir, eventos,
                                 'prop_ambigua_apertura')
        _aplana_hasta_confirmar(adaptador, cuenta_hedge, MES, reloj, dormir, eventos,
                                 'hedge_tras_prop_ambigua')
        return dict(abierto=False, order_id_hedge=oid_hedge, order_id_prop=oid_prop,
                    motivo='prop_ambiguo_tras_cancelar_aplanadas_las_dos')


def _registra_divergencia(adaptador, oid_hedge, oid_prop, eventos):
    """07_ADAPTADOR_NT8.md §5.3, retoque de revisión 3: en CUALQUIER apertura
    donde las dos patas confirmen, se registra `AvgFillPrice` de las dos y su
    diferencia como evento de laboratorio -- 08_LABORATORIO.md §1.2."""
    _, _, precio_hedge = adaptador.leer_fill(oid_hedge)
    _, _, precio_prop = adaptador.leer_fill(oid_prop)
    if precio_hedge is not None and precio_prop is not None:
        eventos.append(dict(tipo='divergencia_fill', order_id_hedge=oid_hedge,
                             order_id_prop=oid_prop, precio_hedge=precio_hedge,
                             precio_prop=precio_prop, diferencia=precio_prop - precio_hedge))


def cierra_las_dos_patas(adaptador, cuenta_prop, instrumento_prop, cuenta_hedge,
                          eventos=None, reloj=None, dormir=None,
                          max_reintentos=10000, intervalo_reintento_s=0.01):
    """07_ADAPTADOR_NT8.md §5.4: orden inverso de la apertura (primero la
    prop, luego el hedge). 'Ninguna pata' se logra aquí INSISTIENDO hasta
    completar -- lo contrario de la apertura, que la logra abortando. Nunca
    se toca el hedge mientras el cierre de la prop no esté confirmado (la
    POSICIÓN en cero, ver DEFECTO 3 en `_aplana_hasta_confirmar`).

    SIN guardián de `hay_conexion` a propósito (ver docstring del módulo,
    REGLA GENERAL 3): un cierre con conexión caída se reintenta, no se
    aborta -- `_aplana_hasta_confirmar` ya lo hace.

    Devuelve {cerrado: bool, pata_abierta (si cerrado=False), intentos_prop,
    intentos_hedge}."""
    reloj = reloj or time.monotonic
    dormir = dormir or time.sleep
    eventos = eventos if eventos is not None else []
    MES = config.obtener().hedge_broker.instrumento

    # ---- FASE PROP (cierre) -------------------------------------------
    cerrada_prop, intentos_prop = _aplana_hasta_confirmar(
        adaptador, cuenta_prop, instrumento_prop, reloj, dormir, eventos,
        'cierre_prop', max_reintentos, intervalo_reintento_s)
    if not cerrada_prop:
        return dict(cerrado=False, pata_abierta='prop', intentos_prop=intentos_prop,
                    intentos_hedge=0)

    # ---- FASE HEDGE (cierre) -- solo con la prop YA confirmada cerrada --
    cerrado_hedge, intentos_hedge = _aplana_hasta_confirmar(
        adaptador, cuenta_hedge, MES, reloj, dormir, eventos,
        'cierre_hedge', max_reintentos, intervalo_reintento_s)
    return dict(cerrado=cerrado_hedge, intentos_prop=intentos_prop, intentos_hedge=intentos_hedge,
                **({} if cerrado_hedge else {'pata_abierta': 'hedge'}))


def cierra_las_dos_patas_INGENUO_ROTO(adaptador, cuenta_prop, instrumento_prop, cuenta_hedge,
                                       eventos=None, reloj=None, dormir=None):
    """**SOLO PARA R3 (comprobación 11 de 08_LABORATORIO.md §8) -- NUNCA se
    llama desde el dashboard real.** La versión ingenua que el propio
    `DATOS_Y_DASHBOARD.md` Parte 4, punto 6 pide implementar A PROPÓSITO para
    demostrar que la comprobación de 'las dos patas o ninguna' la caza:
    manda aplanar() a las dos cuentas SIN esperar a que la prop confirme
    estado terminal primero, y sin reintentar si la primera vuelta no
    confirma. Si la prop no confirma a la primera (mismo escenario que
    `cierra_las_dos_patas` sí maneja bien) y el hedge sí lo hace, esto deja
    exactamente una pata sola."""
    reloj = reloj or time.monotonic
    dormir = dormir or time.sleep
    eventos = eventos if eventos is not None else []
    MES = config.obtener().hedge_broker.instrumento
    oid_prop = adaptador.aplanar(cuenta_prop, instrumento_prop)
    oid_hedge = adaptador.aplanar(cuenta_hedge, MES)   # BUG: no espera a la prop, no reintenta
    estado_prop, _ = _poll_hasta(adaptador, oid_prop, ESTADOS_TERMINALES, None, reloj, dormir)
    estado_hedge, _ = _poll_hasta(adaptador, oid_hedge, ESTADOS_TERMINALES, None, reloj, dormir)
    eventos.append(dict(tipo='cierre_ingenuo', estado_prop=estado_prop, estado_hedge=estado_hedge))
    return dict(cerrado=(estado_prop == 'LLENA' and estado_hedge == 'LLENA'),
                estado_prop=estado_prop, estado_hedge=estado_hedge)
