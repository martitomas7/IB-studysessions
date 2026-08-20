# -*- coding: utf-8 -*-
"""Puerta de D2 (05_ORDEN_DE_CONSTRUCCION.md): 'matar el proceso en 10 puntos
distintos del dia y comprobar que al arrancar reconstruye o aborta, nunca sigue
con estado ambiguo'.

Mata (SIGKILL real, subprocess.Popen + os.kill, no una excepcion simulada) al
escritor de _d2_escritor.py en 10 offsets de tiempo distintos -- cubriendo,
gracias a la pausa artificial que ese script inserta entre fsync del temporal
y el os.replace, tanto el punto 'temporal a medio escribir' como 'temporal ya
completo, esperando a publicarse' como 'justo despues de publicar, antes de la
siguiente vuelta'. Tras cada muerte, en un proceso NUEVO, se llama a
estado.cargar() sobre el mismo estado.json y se exige UNA de dos: carga un
estado completo y con los 8 invariantes intactos, o aborta con
EstadoInvalidoError -- nunca un tercer resultado (JSON truncado, excepcion de
parseo sin controlar, etc.)."""
import json
import os
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)  # ing/ es el padre de verificacion_R3/ en el paquete entregado
sys.path.insert(0, ING)
from bot import estado as E

RUTA = os.path.join(AQUI, '_d2_estado.json')
PAUSA_S = 0.03          # ventana artificial dentro de guardar(); ver _d2_escritor.py
if os.path.exists(RUTA):
    os.remove(RUTA)

# 10 offsets, repartidos para que caigan en fases distintas del bucle del
# escritor (parte alta cerca de una pausa/replace, parte baja a media escritura
# del propio json.dump, que para un dict tan pequeno es casi instantaneo).
OFFSETS = [0.005, 0.012, 0.018, 0.025, 0.032, 0.040, 0.050, 0.065, 0.085, 0.110]

resultados = []
caja_anterior = None
for punto, offset in enumerate(OFFSETS, 1):
    proc = subprocess.Popen(
        [sys.executable, os.path.join(AQUI, '_d2_escritor.py'), ING, RUTA, str(PAUSA_S)],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    pid_line = proc.stdout.readline().strip()
    time.sleep(offset)
    try:
        os.kill(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=5)

    tmp = os.path.join(AQUI, f".{os.path.basename(RUTA)}.tmp")
    tmp_huerfano = os.path.exists(tmp)

    try:
        st = E.cargar(RUTA)
        resultado = f"RECONSTRUYE: carga OK, caja={st['caja']}, dia={st['dia_negociacion']}"
        ok = True
        # monotonia: la caja nunca puede RETROCEDER respecto al ultimo estado
        # confirmado -- si retrocediera, `guardar` habria publicado algo mas
        # viejo que lo ya publicado, y eso SI seria estado ambiguo.
        if caja_anterior is not None and st['caja'] < caja_anterior:
            resultado += f"  <- RETROCEDIO respecto a {caja_anterior} (FALLO)"
            ok = False
        caja_anterior = st['caja']
    except E.EstadoInvalidoError as ex:
        resultado = f"ABORTA limpio: {str(ex).splitlines()[0]}"
        ok = True   # abortar limpio es el otro resultado aceptable
    except Exception as ex:
        resultado = f"FALLO DE LA PRUEBA -- excepcion no controlada: {type(ex).__name__}: {ex}"
        ok = False

    print(f"punto {punto:2d} (kill a los {offset*1000:.0f} ms, pid {pid_line}, "
          f".tmp huerfano={tmp_huerfano}): {resultado}")
    resultados.append(ok)

if os.path.exists(tmp):
    os.remove(tmp)
if os.path.exists(RUTA):
    os.remove(RUTA)

print()
print(f"{sum(resultados)}/{len(resultados)} puntos OK "
      f"(reconstruye con estado valido, o aborta limpio -- nunca estado ambiguo)")
sys.exit(0 if all(resultados) else 1)
