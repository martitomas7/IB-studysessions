# -*- coding: utf-8 -*-
"""calendario.py · D3 · 05_ORDEN_DE_CONSTRUCCION.md · norma R-6 (01_ESPECIFICACION_E2E.md §6)

Responsabilidad (02_ARQUITECTURA.md §2): R-6 -- dirección (sorteo + CONTRA), ventana
RTH/22h, campana T-20. PROHIBIDO: mirar precios (para decidir nada de negocio -- la
reflexión de dirección de abajo no "mira" el precio para decidir, traduce una
dirección ya decidida a la forma que espera `sesion.py`).

Todo aquí son funciones puras: nada de reloj, nada de fichero, nada de red. El "azar"
(el sorteo en sí) entra como argumento -- quien llama decide si viene de un generador
real (bot en vivo) o de un valor forzado (replay, Arquitectura §9: "--replay <fichero>
fuerza dirección, ventana, resets y barras desde el pack").
"""

from bot import config, comandos


def sortea_direccion(candidata, direccion_anterior, contra_pendiente_anterior, hubo_muerte_ayer,
                      estado=None, dia_actual=None):
    """R-6.1 · sorteo 50/50 CADA DÍA + regla CONTRA.

    `candidata` es el resultado YA SORTEADO de una moneda 50/50 para hoy (+1/-1) --
    esta función no tira la moneda, la aplica: R2 prohíbe que un número de negocio
    salga de la cabeza, y "0.5" de probabilidad no es un número de config, es la
    propia definición del sorteo (igual que el `< 1` de la regla de bloqueo en
    sizing.py) -- pero el ACTO de tirar la moneda vive en el llamador (bot.py o el
    arnés de replay), no aquí, para que esta función sea pura y testeable sin RNG.

    `estado`/`dia_actual` (opcionales, recomendación 1 de RECOMENDACIONES.md, revisión
    operador 20-08-2026): si se pasan, la palanca de Clase B "desactivar CONTRA"
    (08_LABORATORIO.md §7.2) se consulta vía `comandos.valor_efectivo('contra', ...,
    valor_apagado=0)` -- desactivar CONTRA es forzar `contra_dias` a 0 el día que la
    desviación esté activa. Omitidos (`None`), la función se comporta exactamente
    como antes: sigue siendo pura y testeable sin estado, para pruebas aisladas.

    Devuelve (direccion, contra_pendiente_nuevo).

    La regla, tal como la fija R-6.1 y Arquitectura §5: hay sorteo diario SIEMPRE,
    y el contador CONTRA lo vetoa mientras está vivo. Si ayer murió alguna cuenta,
    el contador se REARMA a `contra_dias` (no se decrementa primero); si no, se
    decrementa hacia 0. Con el contador > 0, la dirección de HOY es la de AYER
    (se ignora la candidata); con el contador en 0, la dirección de hoy es la
    candidata recién sorteada.
    """
    contra_dias_certificado = config.obtener().sesion.direccion.contra_dias.valor()
    if estado is not None:
        contra_dias = comandos.valor_efectivo('contra', contra_dias_certificado, estado,
                                               dia_actual, valor_apagado=0)
    else:
        contra_dias = contra_dias_certificado
    if hubo_muerte_ayer:
        contra_pendiente = contra_dias
    else:
        contra_pendiente = max(contra_pendiente_anterior - 1, 0)
    direccion = direccion_anterior if contra_pendiente > 0 else candidata
    return direccion, contra_pendiente


def ventana_del_dia(es_dia_de_dato):
    """R-6.2 · ventana RTH/22h. `es_dia_de_dato` es un booleano YA SORTEADO (con
    probabilidad `sesion.cal_rth.frac_dias_dato`) -- mismo principio que arriba: el
    sorteo lo hace el llamador, esto solo traduce el resultado a `barra_inicio`.

    Devuelve (ventana: '22h'|'RTH', barra_inicio).
    """
    if es_dia_de_dato:
        b0_rth = config.obtener().sesion.cal_rth.b0_rth.valor()
        return 'RTH', int(b0_rth)
    return '22h', 0


def refleja_camino(ph_crudo, pl_crudo, pc_crudo, direccion):
    """R-6.1 (nota de arquitectura) · si `direccion` es corta, el día entero se
    refleja alrededor del precio de apertura -- así `sesion.py` siempre barre un
    camino "largo-equivalente" y no necesita saber nada de dirección (Arquitectura
    §1: sesion.py no importa nada salvo config, y desde luego no decide direcciones).

    p0 = cierre de la barra 0 del camino CRUDO (antes de reflejar -- es el mismo
    valor se refleje o no, es el ancla). Si direccion >= 0 (largo), se devuelve el
    camino tal cual. Si direccion < 0 (corto), cada punto x se refleja a 2*p0 - x:
    lo que en el camino real era una bajada se lee como una subida y viceversa, y
    el máximo/mínimo de cada barra se intercambian.

    `replay_v10.json` guarda los caminos SIN reflejar (los cruda de HG22, ver su
    propio campo `convencion.barras`), así que esta función es imprescindible para
    reproducir la traza -- no es una comodidad, es parte del contrato de datos.
    """
    p0 = pc_crudo[0]
    if direccion >= 0:
        return list(ph_crudo), list(pl_crudo), list(pc_crudo)
    ph = [2.0 * p0 - x for x in pl_crudo]   # el máximo reflejado sale del MÍNIMO crudo
    pl = [2.0 * p0 - x for x in ph_crudo]   # y viceversa
    pc = [2.0 * p0 - x for x in pc_crudo]
    return ph, pl, pc


def recorta_campana(ph, pl, pc):
    """R-6.3 · campana: se opera `sesion.barras_por_dia` de las `sesion.barras_de_la_serie`
    que trae la serie -- se dejan de operar los últimos minutos (T-20). Recorta al
    principio del array, que es donde vive la barra 0 (la barra de entrada) y todo
    lo que sigue; los últimos minutos son las barras finales, así que se recorta el
    final. Si el camino ya viene recortado (como los de `replay_v10.json`, que
    almacenan directamente `NB=86` barras), esto es un no-op."""
    nb = config.obtener().sesion.barras_por_dia.valor()
    return ph[:nb], pl[:nb], pc[:nb]
