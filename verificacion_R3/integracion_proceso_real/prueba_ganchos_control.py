# -*- coding: utf-8 -*-
"""Fase 3 (R3): ClienteControl + los ganchos test_congelar()/
test_retrasar_respuesta() de motor.py -- y el escenario (d1) del plan de
pruebas: el CLIENTE de datos no se cuelga nunca, aunque el servidor sí
esté "congelado" (peer conectado pero mudo) más allá del timeout.

R3: antes de aceptar que `AdaptadorSimuladorNT8` "no se cuelga nunca", se
reconstruye a propósito una versión SIN `settimeout()` en el socket de
operación -- exactamente el bug que la regla no negociable de §5 (docstring
de cliente.py) existe para prohibir -- y se ve bloquearse de verdad (acotado
con un hilo + join(timeout) para que ESTA prueba no se cuelgue ella misma).
Solo entonces se confirma que la versión real, con el timeout puesto,
termina en TimeoutOrden dentro de la ventana esperada."""
import os
import signal
import socket
import subprocess
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, ING)

from simulador_nt8.cliente import AdaptadorSimuladorNT8
from simulador_nt8.cliente_control import ClienteControl
from simulador_nt8.errores import TimeoutOrden
from simulador_nt8.protocolo import LectorLineas, escribir_mensaje

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def arranca_servidor():
    dir_sockets = f"/tmp/nt8sim_ganchos_{os.getpid()}"
    fichero_info = f"/tmp/nt8sim_ganchos_info_{os.getpid()}.json"
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


class _ClienteSinTimeout:
    """ANTES (reconstrucción deliberada del bug que §5 prohíbe): mismo
    protocolo que AdaptadorSimuladorNT8, pero SIN volver a fijar
    settimeout() tras el connect() inicial -- el socket queda con el
    timeout de conexión (2s) para SIEMPRE, o sin límite si no se fija
    ninguno. Aquí se fija explícitamente None (bloqueante puro) para
    que la demostración sea inequívoca."""
    def __init__(self, ruta):
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(ruta)
        self._sock.settimeout(None)   # BUG: bloqueante puro, sin límite
        self._lector = LectorLineas(self._sock)

    def hay_conexion(self, cuenta):
        escribir_mensaje(self._sock, {"id": 1, "metodo": "hay_conexion", "args": {"cuenta": cuenta}})
        return self._lector.leer_mensaje()  # bloquea aquí sin límite si el servidor está congelado


print("=== Fase 3: congelar() bloquea de verdad al hilo que atiende la peticion ===")
proc, dir_sockets, fichero_info = arranca_servidor()
ruta_datos = os.path.join(dir_sockets, "nt8.sock")
ruta_control = os.path.join(dir_sockets, "nt8.control.sock")
try:
    control = ClienteControl(ruta_control)

    # el cliente "DESPUES" se conecta y arranca ANTES de congelar -- si se
    # arrancara con el motor ya congelado, arrancar() mismo bloquearía (es
    # una llamada mas que pasa por invocar(), correctamente sujeta al mismo
    # gancho) y devolveria False, que no es lo que esta prueba quiere medir.
    cliente = AdaptadorSimuladorNT8(ruta_datos, timeout_operacion=1.0)
    assert cliente.arrancar() is True

    control.congelar()

    print("\n-- ANTES (cliente reconstruido SIN settimeout(), acotado con hilo+join para no colgar esta prueba) --")
    resultado_hilo = {}
    def intenta_sin_timeout():
        t0 = time.monotonic()
        try:
            c = _ClienteSinTimeout(ruta_datos)
            c.hay_conexion("X")
            resultado_hilo["completo"] = True
        except Exception as ex:
            resultado_hilo["completo"] = True
            resultado_hilo["error"] = ex
        resultado_hilo["dt"] = time.monotonic() - t0
    h = threading.Thread(target=intenta_sin_timeout, daemon=True)
    h.start()
    h.join(timeout=3.0)   # cota de la PRUEBA, no del cliente -- el cliente no tiene ninguna
    sigue_bloqueado = h.is_alive()
    print(f"  tras esperar 3.0s: hilo sigue bloqueado = {sigue_bloqueado}  resultado_hilo={resultado_hilo}")
    ok("SIN settimeout(), la llamada sigue bloqueada pasados 3s (el bug que §5 prohíbe, visto de verdad)",
       sigue_bloqueado and "completo" not in resultado_hilo, resultado_hilo)

    print("\n-- DESPUÉS (AdaptadorSimuladorNT8 real, ya arrancado antes de congelar, timeout_operacion=1.0s) --")
    # hay_conexion() está diseñado para NUNCA lanzar -- usamos leer_cuenta()
    # (un método normal del puerto) para observar el TimeoutOrden de verdad.
    t0 = time.monotonic()
    try:
        cliente.leer_cuenta("X")
        lanzo_timeout = False
        detalle = "no lanzo nada -- inesperado"
    except TimeoutOrden as ex:
        lanzo_timeout = True
        detalle = str(ex)
    dt = time.monotonic() - t0
    print(f"  tiempo real hasta TimeoutOrden: {dt:.2f}s  ({detalle})")
    ok("CON settimeout(), la misma congelacion termina en TimeoutOrden dentro de ~1s (no antes, no nunca)",
       lanzo_timeout and 0.9 <= dt <= 2.5, f"dt={dt:.2f}s")

    # hay_conexion() en concreto: NUNCA debe lanzar, siempre False ante timeout
    t0 = time.monotonic()
    r = cliente.hay_conexion("X")
    dt2 = time.monotonic() - t0
    ok("hay_conexion() en particular NUNCA lanza -- devuelve False ante el mismo timeout",
       r is False, f"resultado={r} dt={dt2:.2f}s")

    control.liberar_congelacion()

    print("\n=== Fase 3: retrasar_respuesta() añade un retraso real observable ===")
    control.retrasar_respuesta("leer_cuenta", 0.5)
    cliente2 = AdaptadorSimuladorNT8(ruta_datos, timeout_operacion=5.0)
    assert cliente2.arrancar() is True
    t0 = time.monotonic()
    cliente2.leer_cuenta("Y")
    dt3 = time.monotonic() - t0
    # cota superior añadida (revisión adversarial 20-08-2026, lente
    # calidad_pruebas_r3): una aserción unilateral (solo >=) no distingue
    # "0.5s reales" de "el retraso se disparó dos veces" o "quedó pegado" --
    # acota también por arriba, banda análoga a prueba_timeout_reloj_real.py.
    ok("retrasar_respuesta(0.5s) produce un retraso real medible, ni instantáneo ni excesivo",
       0.45 <= dt3 <= 1.5, f"dt={dt3:.3f}s")

finally:
    para_servidor(proc, fichero_info)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
