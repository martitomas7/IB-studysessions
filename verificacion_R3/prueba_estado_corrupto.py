# -*- coding: utf-8 -*-
"""R3 (10_SEGURIDAD.md §4.D, §7 hueco #3): un `estado.json` corrupto o
incompleto tiene que dar SIEMPRE `EstadoInvalidoError` -- nunca una
excepción cruda de Python (`JSONDecodeError`, `KeyError`) que quien llama
no pueda distinguir de un bug en su propio código. "Estado corrupto" y
"bug propio" exigen reacciones distintas (10_SEGURIDAD.md §3: estado
corrupto o ausente → N4, nunca se adivina ni se reconstruye a la brava).

Antes del arreglo (20-08-2026), un fichero truncado lanzaba
`json.JSONDecodeError` y uno con un campo ausente lanzaba `KeyError` desde
`estado.validar()` -- reproducido aquí primero (viéndolo fallar de
verdad, no narrado) contra una reconstrucción de la versión sin blindar,
y solo después se confirma que la versión real ya no lo hace."""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import estado as E

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def _cargar_viejo_sin_blindar(ruta):
    """ANTES (reconstrucción literal de estado.cargar() previa al arreglo):
    json.load()/validar() sin envolver -- ver qué excepción cruda deja
    escapar de verdad."""
    if not os.path.isfile(ruta):
        raise E.EstadoInvalidoError(f"no existe estado en {ruta}")
    with open(ruta, 'r', encoding='utf-8') as fh:
        estado = json.load(fh)          # <- sin try/except, la version rota
    from bot import config
    _, checksum_actual = config.cargar()
    fallos = E.validar(estado, checksum_actual)   # <- sin try/except tampoco
    if fallos:
        raise E.EstadoInvalidoError("invariantes violados:\n" + "\n".join(fallos))
    return estado


DIR_TMP = "/tmp/prueba_estado_corrupto"
os.makedirs(DIR_TMP, exist_ok=True)

print("=== 1. JSON truncado ===")
ruta1 = os.path.join(DIR_TMP, "truncado.json")
with open(ruta1, "w") as fh:
    fh.write('{"caja": 100.0, "recamara')  # cortado a mitad, JSON invalido

print("\n-- ANTES (reconstrucción sin blindar) --")
try:
    _cargar_viejo_sin_blindar(ruta1)
    fallo_como_se_esperaba = False
    detalle = "no lanzo nada -- inesperado"
except E.EstadoInvalidoError:
    fallo_como_se_esperaba = False
    detalle = "ya daba EstadoInvalidoError -- inesperado para la version 'vieja'"
except Exception as ex:
    fallo_como_se_esperaba = True
    detalle = f"{type(ex).__name__}: {ex}"
print(f"  resultado: {detalle}")
ok("la version SIN blindar deja escapar una excepcion cruda (no EstadoInvalidoError)",
   fallo_como_se_esperaba, detalle)

print("\n-- DESPUÉS (bot/estado.py::cargar real) --")
try:
    E.cargar(ruta1)
    corregido = False
    detalle2 = "no lanzo nada -- inesperado"
except E.EstadoInvalidoError as ex:
    corregido = True
    detalle2 = str(ex)
except Exception as ex:
    corregido = False
    detalle2 = f"{type(ex).__name__}: {ex} -- SIGUE sin ser EstadoInvalidoError"
print(f"  resultado: {detalle2}")
ok("JSON truncado -> EstadoInvalidoError, con tipo conocido", corregido, detalle2)

print("\n=== 2. Campo esperado ausente (recamara borrada del fichero) ===")
ruta2 = os.path.join(DIR_TMP, "incompleto.json")
json.dump({"caja": 100.0, "version_esquema": 1, "checksum_config": "x"}, open(ruta2, "w"))

print("\n-- ANTES (reconstrucción sin blindar) --")
try:
    _cargar_viejo_sin_blindar(ruta2)
    fallo2 = False
    detalle3 = "no lanzo nada"
except E.EstadoInvalidoError:
    fallo2 = False
    detalle3 = "ya daba EstadoInvalidoError -- inesperado"
except Exception as ex:
    fallo2 = True
    detalle3 = f"{type(ex).__name__}: {ex}"
print(f"  resultado: {detalle3}")
ok("la version SIN blindar deja escapar KeyError crudo desde validar()",
   fallo2, detalle3)

print("\n-- DESPUÉS (bot/estado.py::cargar real) --")
try:
    E.cargar(ruta2)
    corregido2 = False
    detalle4 = "no lanzo nada"
except E.EstadoInvalidoError as ex:
    corregido2 = True
    detalle4 = str(ex)
except Exception as ex:
    corregido2 = False
    detalle4 = f"{type(ex).__name__}: {ex} -- SIGUE sin ser EstadoInvalidoError"
print(f"  resultado: {detalle4}")
ok("campo ausente -> EstadoInvalidoError, con tipo conocido", corregido2, detalle4)

print("\n=== 3. control: un estado.json VALIDO sigue cargando con normalidad ===")
from bot import config
_, checksum = config.cargar()
ruta3 = os.path.join(DIR_TMP, "valido.json")
E.guardar(E.nuevo(version_config="v10", checksum_config=checksum), ruta3)
try:
    st = E.cargar(ruta3)
    ok("un estado.json valido sigue cargando sin excepcion", st is not None, st.get("caja"))
except Exception as ex:
    ok("un estado.json valido sigue cargando sin excepcion", False, f"{type(ex).__name__}: {ex}")

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
