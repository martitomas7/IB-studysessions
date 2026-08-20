# -*- coding: utf-8 -*-
"""lector_laboratorio.py · D-C · 08_LABORATORIO.md §1-§2

Lector de las corrientes JSONL del laboratorio: `mercado_<dia>.jsonl`,
`ordenes_<dia>.jsonl`, `incidencias_<dia>.jsonl` (rotadas por
`dia_negociacion`, con cabecera -- §2), y el diario del orquestador (una
línea por día, SIN cabecera, formato de `02_ARQUITECTURA.md` §6 -- ya lo
escribe `bot/orquestador.py::corre_replay`).

Hasta ahora `bot/contexto_dashboard.py::construye()` solo aceptaba estas
listas YA CARGADAS EN MEMORIA (`mercado_snapshots=[...]`, etc.) -- cómodo
para pruebas y para el replay (que las construye sobre la marcha), pero el
laboratorio real las persiste en disco como JSONL (§2: "append-only
puro"). Este módulo es el puente: lee esos ficheros reales y produce
EXACTAMENTE las estructuras que `contexto_dashboard.construye()` ya
espera -- no inventa un contrato nuevo, no decide cómo agregar/derivar
nada de negocio (eso sigue siendo responsabilidad de `contexto_dashboard.py`).
"""
import glob
import json
import os


def lee_jsonl(ruta):
    """Lee un fichero JSONL, tolerando la ÚLTIMA línea incompleta (§2:
    "si el proceso se cae a media escritura de una línea JSONL, esa línea
    parcial se descarta al leer -- JSONL tolera líneas incompletas al
    final: se ignoran, no invalidan las anteriores"). Una línea rota que
    NO sea la última SÍ es un error real (el fichero está corrupto en
    medio, no cortado a media escritura al final) -- se propaga tal cual,
    nunca se oculta.

    Fichero ausente -> lista vacía (mismo principio que `lee_pendientes`
    de `comandos.py`: "no existe todavía" es una lectura legítima, no un
    error). Devuelve la lista de objetos decodificados, en orden."""
    if not os.path.isfile(ruta):
        return []
    with open(ruta, encoding='utf-8') as fh:
        contenido = fh.read()
    lineas = contenido.split('\n')
    # un fichero bien terminado acaba en '\n', así que el último elemento
    # de split('\n') es '' -- si NO lo es, la última línea real puede
    # estar a medio escribir.
    ultima_puede_estar_a_medias = lineas and lineas[-1] != ''
    if not ultima_puede_estar_a_medias and lineas:
        lineas = lineas[:-1]   # descarta el '' final, no es una línea real
    objetos = []
    for i, linea in enumerate(lineas):
        if not linea:
            continue
        try:
            objetos.append(json.loads(linea))
        except json.JSONDecodeError:
            es_la_ultima = (i == len(lineas) - 1)
            if es_la_ultima and ultima_puede_estar_a_medias:
                continue   # tolerada -- corte a media escritura, §2
            raise
    return objetos


def lee_corriente_con_cabecera(ruta):
    """§2: la primera línea de `mercado_*`/`ordenes_*`/`incidencias_*.jsonl`
    es SIEMPRE la cabecera (`version_config`, `checksum_config`,
    `dia_negociacion`, `hora_arranque_pared`, `hora_arranque_monotona`),
    nunca un registro de negocio. Devuelve `(cabecera: dict|None,
    registros: list)` -- cabecera es `None` si el fichero no existe o
    está vacío."""
    objetos = lee_jsonl(ruta)
    if not objetos:
        return None, []
    return objetos[0], objetos[1:]


def _rutas_por_dia(directorio, prefijo, dia_desde=None, dia_hasta=None):
    """Encuentra `<directorio>/<prefijo>_<N>.jsonl`, opcionalmente
    acotado a `[dia_desde, dia_hasta]` (ambos inclusive; `None` = sin
    límite por ese lado). Orden ASCENDENTE por `N` -- así las
    agregaciones de varios días (y "últimas incidencias") salen ya en
    orden cronológico, sin que quien llama tenga que ordenar nada."""
    if not os.path.isdir(directorio):
        return []
    patron = os.path.join(directorio, f"{prefijo}_*.jsonl")
    hallados = []
    for ruta in glob.glob(patron):
        nombre = os.path.basename(ruta)
        cuerpo = nombre[len(prefijo) + 1:-len('.jsonl')]
        if not cuerpo.isdigit():
            continue   # nombre que no sigue la convención -- se ignora, no es un error fatal
        dia = int(cuerpo)
        if dia_desde is not None and dia < dia_desde:
            continue
        if dia_hasta is not None and dia > dia_hasta:
            continue
        hallados.append((dia, ruta))
    hallados.sort()
    return [ruta for _, ruta in hallados]


def lee_mercado_snapshots(directorio, dia_desde=None, dia_hasta=None):
    """Agrega `mercado_<N>.jsonl` de varios días, en orden -- exactamente
    la forma que `contexto_dashboard.construye(mercado_snapshots=...)`
    espera: dicts con `ts_pared`/`ts_monotono`/`instrumento`/`bid`/`ask`/
    `last`/`estado_feed` (08_LABORATORIO.md §1.1)."""
    snapshots = []
    for ruta in _rutas_por_dia(directorio, 'mercado', dia_desde, dia_hasta):
        _, registros = lee_corriente_con_cabecera(ruta)
        snapshots.extend(registros)
    return snapshots


def lee_eventos_orden(directorio, dia_desde=None, dia_hasta=None):
    """Agrega `ordenes_<N>.jsonl` -- eventos de transición de estado de
    orden (08_LABORATORIO.md §1.2: `ts_pared`/`ts_monotono`/`order_id`/
    `cuenta`/`instrumento`/`estado`/`precio`/`cantidad`)."""
    eventos = []
    for ruta in _rutas_por_dia(directorio, 'ordenes', dia_desde, dia_hasta):
        _, registros = lee_corriente_con_cabecera(ruta)
        eventos.extend(registros)
    return eventos


def lee_incidencias(directorio, dia_desde=None, dia_hasta=None):
    """Agrega `incidencias_<N>.jsonl` -- exactamente la forma que
    `contexto_dashboard.construye(incidencias_recientes=...)` espera
    (08_LABORATORIO.md §1.4: `ts_pared`/`ts_monotono`/`tipo`/`cuenta`/
    `detalle`)."""
    incidencias = []
    for ruta in _rutas_por_dia(directorio, 'incidencias', dia_desde, dia_hasta):
        _, registros = lee_corriente_con_cabecera(ruta)
        incidencias.extend(registros)
    return incidencias


def cuenta_incidencias_por_tipo(incidencias):
    """Ayuda de agregación -- la forma que
    `contexto_dashboard.construye(incidencias_contadores=...)` espera:
    `{tipo: n}`."""
    contadores = {}
    for it in incidencias:
        tipo = it.get('tipo', 'desconocido')
        contadores[tipo] = contadores.get(tipo, 0) + 1
    return contadores


def lee_diario(ruta):
    """El diario del orquestador (`02_ARQUITECTURA.md` §6, ya lo escribe
    `bot/orquestador.py::corre_replay`) -- UNA línea por día, SIN
    cabecera (a diferencia de mercado/ordenes/incidencias: es un único
    fichero acumulativo, no rotado por día -- 08_LABORATORIO.md §1.3:
    "el laboratorio lee y agrega ese diario, no inventa un segundo
    formato paralelo"). Devuelve la lista de líneas ya decodificadas, en
    el mismo orden que `contexto_dashboard.construye(historial_diario=...)`
    espera."""
    return lee_jsonl(ruta)
