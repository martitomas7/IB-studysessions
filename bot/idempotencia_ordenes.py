# -*- coding: utf-8 -*-
"""idempotencia_ordenes.py · D8.5 · ORDEN_DE_TRABAJO_D8.md §1 · diseño
grounded de D8.4 §2.5

"Idempotencia de órdenes: por order_id, como ya hacen los comandos.
Puerta R3: matar el bot justo después de mandar una orden y antes de
registrarla; al reiniciar no puede mandarla otra vez."

**Precisión importante, que la síntesis del diseño deja explícita porque
ninguna versión anterior la cerraba del todo:** `abrir()`/`coloca_bracket()`
NO son idempotentes -- a diferencia de los ejecutores de `bot/comandos.py`
(aplanar sobre una posición ya plana es un no-op del propio puerto; fijar
`parada_total=True` dos veces es lo mismo que una vez), volver a llamar
`abrir()` manda una SEGUNDA orden real. Por eso este módulo NUNCA
"reclama y reintenta" tras una caída -- solo deja un TESTIGO
(intención/resultado) para que quien reinicia pueda distinguir "nunca se
mandó" de "se mandó, pero no se llegó a registrar el order_id". La
ambigüedad genuina (proceso muerto entre las dos escrituras, order_id
desconocido) NO la resuelve reintentando -- la resuelve
`bot/reconciliacion.py` mirando la posición REAL del bróker."""
import json
import os


def _ruta_intencion(directorio, intent_id):
    return os.path.join(directorio, f"{intent_id}.intencion.json")


def _ruta_resultado(directorio, intent_id):
    return os.path.join(directorio, f"{intent_id}.resultado.json")


def _escribe_atomico(ruta, obj):
    directorio = os.path.dirname(os.path.abspath(ruta)) or '.'
    os.makedirs(directorio, exist_ok=True)
    tmp = os.path.join(directorio, f".{os.path.basename(ruta)}.tmp")
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)


def escribe_intencion(directorio, intent_id, payload):
    """Se escribe SIEMPRE antes de llamar al adaptador -- el testigo de
    "estuve a punto de mandar esto". Escritura atómica (tmp+fsync+
    replace), mismo patrón que `bot/comandos.py::escribe_comando`.
    Sobrescribir una intención ya existente con el mismo `intent_id` es
    un error de uso (mismo principio que `comandos.py`: los `intent_id`
    no se reciclan) -- se deja pasar sin comprobación aquí porque
    `intent_id` ya incluye día/slot/intento/fase (ver
    `ResuelveDiaEnVivo`), así que un choque real indicaría un bug de
    construcción del propio `intent_id`, no un caso de uso legítimo."""
    ruta = _ruta_intencion(directorio, intent_id)
    _escribe_atomico(ruta, dict(intent_id=intent_id, payload=payload))
    return ruta


def marca_resultado(directorio, intent_id, resultado):
    """Se escribe DESPUÉS de que el adaptador confirme (p.ej.
    `{'order_id': ...}` de `abrir()`, o `{'order_id_stop':...,
    'order_id_limite':..., 'id_grupo_oco':...}` de `coloca_bracket()`).
    En cuanto esto existe, `resultado_de()` deja de ser `None` para ese
    `intent_id` -- la señal de "esto YA se hizo, nunca reenviar."""
    ruta = _ruta_resultado(directorio, intent_id)
    _escribe_atomico(ruta, dict(intent_id=intent_id, resultado=resultado))
    return ruta


def resultado_de(directorio, intent_id):
    """`None` si el resultado todavía no se registró -- ambiguo: puede
    ser que la intención nunca se procesó, o que se procesó pero el
    proceso murió antes de `marca_resultado()`. Quien llama (`reconciliacion.py`)
    es responsable de desambiguar mirando el bróker, nunca reintentando
    a ciegas."""
    ruta = _ruta_resultado(directorio, intent_id)
    if not os.path.isfile(ruta):
        return None
    with open(ruta, encoding='utf-8') as fh:
        return json.load(fh)['resultado']


def intenciones_sin_resultado(directorio, dia_negociacion):
    """Lista los `intent_id` de HOY (por convención, `intent_id` empieza
    por `f"{dia_negociacion}:"`) que tienen intención pero NO resultado
    -- exactamente el conjunto ambiguo que `reconciliacion.reconcilia_arranque`
    tiene que resolver (o retro-completar, si logra determinar con
    certeza qué pasó) antes de que el bucle vuelva a operar."""
    if not os.path.isdir(directorio):
        return []
    prefijo = f"{dia_negociacion}:"
    pendientes = []
    for nombre in sorted(os.listdir(directorio)):
        if not nombre.endswith('.intencion.json'):
            continue
        intent_id = nombre[:-len('.intencion.json')]
        if not intent_id.startswith(prefijo):
            continue
        if resultado_de(directorio, intent_id) is None:
            pendientes.append(intent_id)
    return pendientes
