# -*- coding: utf-8 -*-
"""R3 (10_SEGURIDAD.md §4.D): `bot/estado.py::guarda_instantanea` -- rota
correctamente (se queda con como mucho `dias_retenidos` ficheros), escribe
atómicamente, y sirve para lo que existe: detectar que un `estado.json`
válido empezó a divergir de sí mismo en algún punto del pasado."""
import json
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import config, estado as E

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


DIR = "/tmp/prueba_instantanea_estado"
shutil.rmtree(DIR, ignore_errors=True)

_, checksum = config.cargar()
st = E.nuevo(version_config="v10", checksum_config=checksum)

print("=== 1. escribe una instantánea por día, con nombre legible ===")
for dia in range(1, 6):
    st["dia_negociacion"] = dia
    st["caja"] = float(dia) * 10.0
    E.guarda_instantanea(st, DIR, dia, dias_retenidos=3)

ficheros = sorted(os.listdir(DIR))
ok("con dias_retenidos=3 tras 5 escrituras, quedan exactamente 3 ficheros (rotado)",
   len(ficheros) == 3, ficheros)
ok("son los 3 MÁS RECIENTES (días 3, 4, 5) -- no los primeros",
   ficheros == ["estado_dia_0003.json", "estado_dia_0004.json", "estado_dia_0005.json"], ficheros)

print("\n=== 2. cada instantánea es un JSON completo y válido, con el contenido de SU día ===")
contenido_dia5 = json.load(open(os.path.join(DIR, "estado_dia_0005.json")))
ok("la instantánea del día 5 tiene caja=50.0 (la del día 5, no una mezcla)",
   contenido_dia5["caja"] == 50.0, contenido_dia5["caja"])

print("\n=== 3. dias_retenidos=0 no borra nada (retención desactivada explícitamente) ===")
shutil.rmtree(DIR, ignore_errors=True)
for dia in range(1, 4):
    st["dia_negociacion"] = dia
    E.guarda_instantanea(st, DIR, dia, dias_retenidos=0)
ok("con dias_retenidos=0, se conservan TODAS (0 = sin poda, no 'cero retenidas')",
   len(os.listdir(DIR)) == 3, sorted(os.listdir(DIR)))

print("\n=== 4. no hay fichero .tmp huérfano tras una escritura normal (atomicidad real) ===")
tmp_huerfanos = [f for f in os.listdir(DIR) if f.startswith(".") and f.endswith(".tmp")]
ok("ningún .tmp huérfano queda tras varias escrituras normales", len(tmp_huerfanos) == 0, tmp_huerfanos)

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
