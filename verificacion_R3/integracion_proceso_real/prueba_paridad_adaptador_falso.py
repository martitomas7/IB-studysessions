# -*- coding: utf-8 -*-
"""Fase 2 (R3): la MISMA secuencia de operaciones, corrida dos veces --
una contra `AdaptadorFalso` en proceso directo, otra contra
`AdaptadorSimuladorNT8` a través de un `simulador_nt8.servidor` real -- y
se comparan los resultados uno a uno. Un caso por cada uno de los diez
métodos del puerto (07_ADAPTADOR_NT8.md §1), más el caso de error de
dominio (KeyError sobre un order_id inexistente) para confirmar que
`AdaptadorSimuladorNT8` reconstruye la MISMA excepción que lanzaría
`AdaptadorFalso` directamente, no una genérica de transporte.

R3, Fase 2 tal como la fija la síntesis de diseño: antes de que `cliente.py`
tuviera un método dado implementado, el caso correspondiente fallaba con
`AttributeError` (método inexistente) -- confirma que el test ejercita ese
método de verdad y no pasa vacuamente. `cliente.py` ya se escribió con los
diez métodos completos (verificacion_R3/integracion_proceso_real/
prueba_servidor_arranque_basico.py ya demostró el servidor + protocolo por
separado, hablando el socket a mano) -- esta prueba es la que demuestra
PARIDAD FUNCIONAL end-to-end, incluido el cliente real."""
import json
import os
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, ING)

from bot.adaptador_falso import AdaptadorFalso
from simulador_nt8.cliente import AdaptadorSimuladorNT8

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def arranca_servidor():
    dir_sockets = f"/tmp/nt8sim_paridad_{os.getpid()}"
    fichero_info = f"/tmp/nt8sim_paridad_info_{os.getpid()}.json"
    proc = subprocess.Popen(
        [sys.executable, "-m", "simulador_nt8", "--entorno=pruebas",
         "--dir-sockets", dir_sockets, "--fichero-info", fichero_info],
        cwd=ING, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5.0 and not os.path.exists(fichero_info):
        time.sleep(0.02)
    if not os.path.exists(fichero_info):
        raise RuntimeError("el servidor no arrancó dentro de 5s")
    ruta_datos = os.path.join(dir_sockets, "nt8.sock")
    return proc, ruta_datos, fichero_info


def para_servidor(proc, fichero_info):
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    try:
        os.remove(fichero_info)
    except FileNotFoundError:
        pass


def ejecuta_guion(adaptador):
    """La MISMA secuencia de operaciones, sea `adaptador` un AdaptadorFalso
    directo o un AdaptadorSimuladorNT8 -- toca los diez métodos del puerto
    más el caso de error de dominio. Devuelve un dict con cada paso
    etiquetado, para comparar campo a campo (no solo "iguales o no")."""
    r = {}
    r["arrancar"] = adaptador.arrancar()
    r["hay_conexion_antes"] = adaptador.hay_conexion("MFF-EVAL-1")
    r["leer_cuenta"] = adaptador.leer_cuenta("MFF-EVAL-1")
    oid_hedge = adaptador.abrir("CTA-HEDGE", "MES", -1, 4)
    r["abrir_hedge"] = oid_hedge
    r["leer_estado_orden_tras_abrir"] = adaptador.leer_estado_orden(oid_hedge)
    r["leer_fill"] = adaptador.leer_fill(oid_hedge)
    r["leer_posicion_hedge"] = adaptador.leer_posicion("CTA-HEDGE", "MES")
    oid_prop = adaptador.abrir("CTA-PROP", "instrumento-prop", 1, 10)
    r["abrir_prop"] = oid_prop
    adaptador.leer_estado_orden(oid_prop)  # dispara el avance/fill
    oid_cierre = adaptador.aplanar("CTA-HEDGE", "MES")
    r["aplanar_hedge"] = oid_cierre
    r["leer_estado_orden_aplanar"] = adaptador.leer_estado_orden(oid_cierre)
    r["leer_posicion_hedge_tras_aplanar"] = adaptador.leer_posicion("CTA-HEDGE", "MES")
    oid_para_cancelar = adaptador.abrir("CTA-PROP", "instrumento-prop", 1, 1)
    r["cancelar"] = adaptador.cancelar(oid_para_cancelar)
    try:
        adaptador.leer_estado_orden("NO-EXISTE-JAMAS")
        r["error_order_id_inexistente"] = ("sin_excepcion", None)
    except Exception as ex:
        r["error_order_id_inexistente"] = (type(ex).__name__, str(ex))
    r["parar"] = adaptador.parar()
    return r


print("=== Fase 2: guion identico contra AdaptadorFalso EN PROCESO ===")
directo = AdaptadorFalso()
r_directo = ejecuta_guion(directo)
for k, v in r_directo.items():
    print(f"  {k}: {v}")

print("\n=== Fase 2: MISMO guion contra AdaptadorSimuladorNT8 (servidor real aparte) ===")
proc, ruta_datos, fichero_info = arranca_servidor()
try:
    remoto = AdaptadorSimuladorNT8(ruta_datos)
    r_remoto = ejecuta_guion(remoto)
    for k, v in r_remoto.items():
        print(f"  {k}: {v}")
finally:
    para_servidor(proc, fichero_info)

print("\n=== comparacion campo a campo ===")
for k in r_directo:
    coincide = r_directo[k] == r_remoto.get(k, "<<AUSENTE>>")
    ok(f"paridad '{k}'", coincide, f"directo={r_directo[k]!r}  remoto={r_remoto.get(k)!r}")

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
