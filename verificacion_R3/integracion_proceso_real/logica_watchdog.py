# -*- coding: utf-8 -*-
"""logica_watchdog.py · verificacion_R3/integracion_proceso_real

Puerto a Python, SOLO PARA PODER PROBARLO EN ESTE ENTORNO LINUX, de la
lógica de decisión de `watchdog_bot.ps1` (09_DESPLIEGUE.md §1.2): leer
`latido.json`, calcular su edad, decidir si está rancio. `watchdog_bot.ps1`
es -- y sigue siendo -- el artefacto real de despliegue (PowerShell +
Task Scheduler, para una máquina Windows real); este módulo NO lo
sustituye, y NO se toca `watchdog_bot.ps1` para que "quepa" en esta prueba
(R1: la especificación de despliegue vive en `09_DESPLIEGUE.md` y su
script, no aquí). Lo que este módulo prueba es la LÓGICA DE DECISIÓN en
sí -- ¿un latido con esta edad se considera rancio o no, con este umbral?
-- que es idéntica en las dos implementaciones porque las dos parten de
la misma tabla de `09_DESPLIEGUE.md` §1.2. Si algún día
`09_DESPLIEGUE.md` cambia esa tabla, las dos se actualizan juntas."""
import json
import time


def revisa_latido(ruta_latido, umbral_rancio_s, ahora=None):
    """Devuelve (rancio: bool, edad_s: float|None, motivo: str) -- espejo
    de la sección 1 de `watchdog_bot.ps1`: fichero ausente o sin `ts_iso`
    parseable se trata como "proceso muerto" (rancio=True), igual que
    hace el script real."""
    ahora = ahora if ahora is not None else time.time()
    try:
        with open(ruta_latido) as fh:
            obj = json.load(fh)
        ts = obj["ts"] if "ts" in obj else None  # arnes_bot_minimo usa ts_iso; el
                                                    # servidor usa "ts" epoch -- se acepta
                                                    # cualquiera de los dos formatos
        if ts is None and "ts_iso" in obj:
            import datetime
            ts = datetime.datetime.fromisoformat(obj["ts_iso"]).timestamp()
        if ts is None:
            return True, None, "latido.json sin ts/ts_iso -- tratado como proceso muerto"
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError, OSError) as ex:
        return True, None, f"latido.json ausente o corrupto ({type(ex).__name__}) -- tratado como proceso muerto"
    edad = ahora - ts
    rancio = edad > umbral_rancio_s
    return rancio, edad, (f"edad {edad:.2f}s > umbral {umbral_rancio_s}s" if rancio
                           else f"edad {edad:.2f}s <= umbral {umbral_rancio_s}s")
