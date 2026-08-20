# -*- coding: utf-8 -*-
"""Fase 8 (R3) · cierra el hueco de cobertura que la revisión adversarial
del 20-08-2026 (lente fidelidad_puerto) encontró: la carrera
cancelar-vs-fill de `07_ADAPTADOR_NT8.md §5.3` (la que motivó la revisión
2 de ese documento -- "el fallo operativo más caro posible") nunca se
había fabricado CRUZANDO la frontera de proceso real de `simulador_nt8/`
-- solo en proceso, contra `AdaptadorFalso` directo, vía el hook
`en_cancelar` (un callable Python que no puede cruzar JSON).

Primero se confirma que intentarlo con `en_cancelar` de verdad falla LIMPIO
(`ArgumentoNoSerializable`, no un `TypeError` crudo de `json` -- el arreglo
de la propia revisión adversarial). Después se fabrica la MISMA carrera con
un mecanismo que sí cruza el cable: `test_retrasar_respuesta("cancelar", …)`
mantiene el `cancelar()` real bloqueado del lado servidor mientras, desde
OTRA conexión de control, `test_fuerza_fill()` hace que el fill gane la
carrera -- exactamente 07_ADAPTADOR_NT8.md §5.3, rama "2b-LLENA" ("la
cancelación llegó tarde: el hedge SÍ se ejecutó")."""
import os
import signal
import subprocess
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, ING)

from simulador_nt8.cliente import AdaptadorSimuladorNT8
from simulador_nt8.cliente_control import ClienteControl
from simulador_nt8.errores import ArgumentoNoSerializable

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def arranca_servidor():
    dir_sockets = f"/tmp/nt8sim_carrera_{os.getpid()}"
    fichero_info = f"/tmp/nt8sim_carrera_info_{os.getpid()}.json"
    proc = subprocess.Popen(
        [sys.executable, "-m", "simulador_nt8", "--entorno=pruebas",
         "--dir-sockets", dir_sockets, "--fichero-info", fichero_info],
        cwd=ING, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5.0 and not os.path.exists(fichero_info):
        time.sleep(0.02)
    if not os.path.exists(fichero_info):
        raise RuntimeError("el servidor no arrancó dentro de 5s")
    return proc, dir_sockets, fichero_info


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


print("=== Fase 8a: en_cancelar (callable) por el canal de control -- ArgumentoNoSerializable, no TypeError crudo ===")
proc, dir_sockets, fichero_info = arranca_servidor()
try:
    ruta_control = os.path.join(dir_sockets, "nt8.control.sock")
    control = ClienteControl(ruta_control)
    try:
        control.programa_abrir("CTA-HEDGE", "MES", fill_en_s=999.0, en_cancelar=lambda a, o: None)
        lanzo_correcto = False
        detalle = "no lanzo nada -- inesperado"
    except ArgumentoNoSerializable as ex:
        lanzo_correcto = True
        detalle = f"ArgumentoNoSerializable: {ex}"
    except Exception as ex:
        lanzo_correcto = False
        detalle = f"lanzo {type(ex).__name__} en vez de ArgumentoNoSerializable: {ex}"
    print(f"  resultado: {detalle}")
    ok("un callable (en_cancelar) por el canal de control da ArgumentoNoSerializable, "
       "con tipo conocido -- NO un TypeError crudo de json", lanzo_correcto, detalle)

    # la conexion de control sigue sana tras el error -- no se corrompio el framing
    r = control.congelar()
    control.liberar_congelacion()
    ok("la conexion de control SIGUE funcionando tras el error (no se corrompio el framing)",
       r is True, r)
finally:
    para_servidor(proc, fichero_info)


print("\n=== Fase 8b: la MISMA carrera cancelar-vs-fill de 07_ADAPTADOR_NT8.md §5.3, "
      "fabricada cruzando la frontera de proceso real ===")
proc, dir_sockets, fichero_info = arranca_servidor()
try:
    ruta_datos = os.path.join(dir_sockets, "nt8.sock")
    ruta_control = os.path.join(dir_sockets, "nt8.control.sock")
    control = ClienteControl(ruta_control)
    cliente = AdaptadorSimuladorNT8(ruta_datos, timeout_operacion=10.0)
    assert cliente.arrancar() is True

    control.programa_abrir("CTA-HEDGE", "MES", fill_en_s=999.0)  # nunca llena por si sola
    oid = cliente.abrir("CTA-HEDGE", "MES", -1, 4)
    estado_inicial = cliente.leer_estado_orden(oid)
    ok("la orden esta viva (ACEPTADA, no LLENA) antes de la carrera",
       estado_inicial == "ACEPTADA", estado_inicial)

    # el cancelar() real queda retenido 0.8s del lado servidor -- ventana
    # determinista para que el fill gane la carrera desde OTRA conexion
    control.retrasar_respuesta("cancelar", 0.8)

    resultado_hilo = {}
    def hilo_cancelar():
        t0 = time.monotonic()
        resultado_hilo["estado_devuelto"] = cliente.cancelar(oid)
        resultado_hilo["dt"] = time.monotonic() - t0

    h = threading.Thread(target=hilo_cancelar, daemon=True)
    h.start()
    time.sleep(0.3)   # asegurar que el hilo servidor ya esta dormido dentro del retraso
    control.fuerza_fill(oid, precio=5432.25)   # el fill gana la carrera, desde OTRA conexion
    h.join(timeout=5.0)

    print(f"  resultado_hilo: {resultado_hilo}")
    ok("cancelar() tardo aproximadamente los 0.8s del retraso fabricado (no antes)",
       resultado_hilo.get("dt", 0) >= 0.7, resultado_hilo.get("dt"))
    ok("cancelar() devuelve 'LLENA' -- la cancelacion llego tarde, el fill SI se ejecuto "
       "(07_ADAPTADOR_NT8.md §5.3, rama 2b-LLENA)",
       resultado_hilo.get("estado_devuelto") == "LLENA", resultado_hilo.get("estado_devuelto"))

    estado_final = cliente.leer_estado_orden(oid)
    # OJO (verificado contra bot/adaptador_falso.py::leer_posicion): el segundo
    # valor que devuelve leer_posicion() es un 100.0 fijo siempre que la
    # cantidad no sea cero -- NO el precio real de fill (eso es una
    # simplificacion del propio AdaptadorFalso, igual en el doble en
    # proceso y aqui -- paridad correcta, no un defecto de este simulador).
    # El precio real de fill se lee con leer_fill(), que si expone
    # o['precio_medio'] de verdad.
    pos_final, _placeholder_no_es_precio_real = cliente.leer_posicion("CTA-HEDGE", "MES")
    llena, cantidad_llenada, precio_fill_real = cliente.leer_fill(oid)
    ok("el estado final de la orden es LLENA, consistente con el resultado de cancelar()",
       estado_final == "LLENA", estado_final)
    ok("la posicion final refleja el fill que gano la carrera (no quedo en cero)",
       pos_final != 0, pos_final)
    ok("leer_fill() SI expone el precio real (5432.25) que fuerza_fill() fijo -- "
       "a diferencia del 100.0 fijo que leer_posicion() siempre devuelve",
       llena is True and cantidad_llenada == 4 and precio_fill_real == 5432.25,
       (llena, cantidad_llenada, precio_fill_real))
finally:
    para_servidor(proc, fichero_info)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
