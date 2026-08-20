# -*- coding: utf-8 -*-
"""Subproceso de la puerta D2. Escribe estado.json en un bucle, uno por
iteracion, con una pausa artificial DENTRO de la escritura atomica (entre el
fsync del temporal y el os.replace) para ensanchar la ventana en la que un
`kill -9` externo (el script padre, d2_mata_el_proceso.py) puede aterrizar a
media escritura. El padre lo mata en 10 puntos distintos; este script no se
protege de nada -- si lo matan, muere sin limpiar, tal cual haria el bot real
si se va la luz."""
import os
import sys
import time

sys.path.insert(0, sys.argv[1])
from bot import config, estado as E

RUTA = sys.argv[2]
PAUSA_S = float(sys.argv[3])

_replace_real = os.replace
def _replace_lento(src, dst):
    time.sleep(PAUSA_S)   # la ventana vulnerable: temporal ya en disco, aun sin
                           # publicar -- si nos matan AQUI, el .tmp queda huerfano
                           # y `ruta` NUNCA se toco (es justo lo que hay que probar)
    _replace_real(src, dst)
os.replace = _replace_lento

cfg, checksum = config.cargar()
if not os.path.isfile(RUTA):
    st = E.nuevo(cfg.meta.version, checksum)
    E.guardar(st, RUTA)
else:
    st = E.cargar(RUTA)

print(os.getpid(), flush=True)   # el padre lee esto para saber a quien matar
for i in range(400):
    st = dict(st)
    st["caja"] = float(i + 1)       # mutacion simple, monotona, facil de verificar
    st["dia_negociacion"] = i + 1
    E.guardar(st, RUTA)
    time.sleep(PAUSA_S)
