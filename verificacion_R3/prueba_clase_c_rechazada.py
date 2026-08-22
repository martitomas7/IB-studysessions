# -*- coding: utf-8 -*-
"""Verificación R3 dedicada -- DECISION_CREDENCIALES_Y_FASE.md punto 4:

"Añade un test que meta un comando de tipo `fase` (y otro de `credenciales`)
por el camino del dashboard y compruebe que se rechaza con el error de Clase
C. Cero código de producción, y la garantía deja de depender de que nadie se
despiste."

08_LABORATORIO.md §7.2: Clase C (aumentar exposición o tocar la norma) NO
tiene comandos -- `bot/comandos.py::clase_de()` no reconoce ningún tipo de
Clase C, así que CUALQUIER `tipo` fuera de CLASE_A/CLASE_B cae por el mismo
camino: `escribe_comando()` lo rechaza con `ComandoInvalidoError` antes de
escribir nada a disco. `fase` (D9 §3.2, tope de fase) y `credenciales` (D9
§3.5, descriptor NT8) son dos ejemplos concretos de "tocar la norma" que
D9 introduce -- ninguno de los dos debe poder colarse por el dashboard, ni
hoy (que ninguno de los dos existe como tipo reconocido) ni en el futuro (si
algún día alguien los añadiera a CLASE_A/CLASE_B por error, este test lo
detectaría).

Esto es CERO código de producción: no se toca `bot/comandos.py`. La garantía
que pide el operador es justo esta -- que no dependa de que nadie se
despiste, sino de un test que la ejercite de verdad."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import comandos as C

DIR = os.path.join(AQUI, '_prueba_clase_c_rechazada')
shutil.rmtree(DIR, ignore_errors=True)

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def comando_de(tipo, id_):
    return dict(id=id_, ts_pared='2026-08-22T10:00:00+00:00', tipo=tipo,
                parametros={}, caduca_en='2026-08-22T23:59:59+00:00', quien='op')


print("=== clase_de(): ni 'fase' ni 'credenciales' se reconocen como A/B ===")
ok("clase_de('fase') is None", C.clase_de('fase') is None)
ok("clase_de('credenciales') is None", C.clase_de('credenciales') is None)
ok("'fase' no está en CLASE_A", 'fase' not in C.CLASE_A)
ok("'fase' no está en CLASE_B", 'fase' not in C.CLASE_B)
ok("'credenciales' no está en CLASE_A", 'credenciales' not in C.CLASE_A)
ok("'credenciales' no está en CLASE_B", 'credenciales' not in C.CLASE_B)

print("\n=== escribe_comando(tipo='fase') -- camino del dashboard -- se rechaza ===")
try:
    C.escribe_comando(DIR, comando_de('fase', 'c_fase_1'))
    ok("tipo='fase' -> ComandoInvalidoError", False, "NO se lanzó excepción")
except C.ComandoInvalidoError as ex:
    ok("tipo='fase' -> ComandoInvalidoError", True, str(ex))
    ok("el mensaje cita 'Clase C'", 'Clase C' in str(ex), str(ex))
    ok("el mensaje cita el tipo ofensor ('fase')", "'fase'" in str(ex), str(ex))
ok("NO se escribió comandos/c_fase_1.json (rechazado antes de tocar disco)",
   not os.path.exists(os.path.join(DIR, 'c_fase_1.json')))

print("\n=== escribe_comando(tipo='credenciales') -- camino del dashboard -- se rechaza ===")
try:
    C.escribe_comando(DIR, comando_de('credenciales', 'c_cred_1'))
    ok("tipo='credenciales' -> ComandoInvalidoError", False, "NO se lanzó excepción")
except C.ComandoInvalidoError as ex:
    ok("tipo='credenciales' -> ComandoInvalidoError", True, str(ex))
    ok("el mensaje cita 'Clase C'", 'Clase C' in str(ex), str(ex))
    ok("el mensaje cita el tipo ofensor ('credenciales')", "'credenciales'" in str(ex), str(ex))
ok("NO se escribió comandos/c_cred_1.json (rechazado antes de tocar disco)",
   not os.path.exists(os.path.join(DIR, 'c_cred_1.json')))

print("\n=== control: un tipo de Clase A real SÍ se acepta por el mismo camino ===")
ruta = C.escribe_comando(DIR, comando_de('parada_total', 'c_control_1'))
ok("tipo='parada_total' (Clase A) -> se escribe sin excepción", os.path.exists(ruta), ruta)

print("\n=== lee_pendientes() nunca puede devolver un comando de Clase C ===")
# ninguno de los dos comandos rechazados llegó a escribirse -- lee_pendientes()
# solo puede leer lo que exista en disco, así que esto reconfirma por el otro
# extremo del camino (lo que el bot LEE, no solo lo que el dashboard ESCRIBE).
pendientes = C.lee_pendientes(DIR)
tipos_pendientes = sorted(p['tipo'] for p in pendientes)
ok("lee_pendientes() no contiene 'fase' ni 'credenciales'",
   'fase' not in tipos_pendientes and 'credenciales' not in tipos_pendientes, tipos_pendientes)
ok("lee_pendientes() sí contiene el control de Clase A", tipos_pendientes == ['parada_total'],
   tipos_pendientes)

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
sys.exit(0 if n_ok == len(resultados) else 1)
