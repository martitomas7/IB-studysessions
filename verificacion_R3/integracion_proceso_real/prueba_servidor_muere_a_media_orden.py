# -*- coding: utf-8 -*-
"""Fase 4 (R3) · Escenario (a) del plan de pruebas: matar el proceso
"NT8" (el servidor de simulador_nt8) con SIGKILL de verdad mientras hay
una orden en curso -- lo que NINGUNA prueba en proceso con
bot/adaptador_falso.py puede demostrar (matar el proceso de test mataría
también su propio estado; aquí el servidor es un PROCESO APARTE de
verdad).

R3: primero se corre el camino feliz (sin SIGKILL) para confirmar verde.
Luego se repite el MISMO escenario con SIGKILL real a mitad de la ventana
de `retrasar_respuesta()`, y se ve la excepción real que produce -- no se
narra que sería ConexionPerdida, se comprueba con el proceso muerto de
verdad."""
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
from simulador_nt8.errores import ConexionPerdida

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def arranca_servidor(sufijo):
    dir_sockets = f"/tmp/nt8sim_muere_{sufijo}_{os.getpid()}"
    fichero_info = f"/tmp/nt8sim_muere_{sufijo}_info_{os.getpid()}.json"
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


def para_servidor_si_vivo(proc, fichero_info):
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    for f in (fichero_info,):
        try: os.remove(f)
        except FileNotFoundError: pass


print("=== Fase 4a: camino feliz, retraso real pero SIN matar el servidor ===")
proc, dir_sockets, fichero_info = arranca_servidor("feliz")
try:
    ruta_datos = os.path.join(dir_sockets, "nt8.sock")
    ruta_control = os.path.join(dir_sockets, "nt8.control.sock")
    control = ClienteControl(ruta_control)
    cliente = AdaptadorSimuladorNT8(ruta_datos, timeout_operacion=5.0)
    assert cliente.arrancar() is True
    control.retrasar_respuesta("abrir", 1.0)
    t0 = time.monotonic()
    oid = cliente.abrir("CTA-HEDGE", "MES", -1, 4)
    dt = time.monotonic() - t0
    # cota superior añadida (revisión adversarial 20-08-2026, lente
    # calidad_pruebas_r3): mismo motivo que prueba_ganchos_control.py --
    # una aserción solo->= no distingue "1s real" de un retraso pegado.
    ok("camino feliz: abrir() con retraso de 1s SIGUE respondiendo (servidor vivo)",
       isinstance(oid, str) and 0.9 <= dt <= 2.5, f"oid={oid} dt={dt:.2f}s")
finally:
    para_servidor_si_vivo(proc, fichero_info)

print("\n=== Fase 4b: MISMO escenario, pero el servidor recibe SIGKILL a mitad de la orden ===")
proc, dir_sockets, fichero_info = arranca_servidor("kill")
try:
    ruta_datos = os.path.join(dir_sockets, "nt8.sock")
    ruta_control = os.path.join(dir_sockets, "nt8.control.sock")
    control = ClienteControl(ruta_control)
    cliente = AdaptadorSimuladorNT8(ruta_datos, timeout_operacion=5.0)
    assert cliente.arrancar() is True
    control.retrasar_respuesta("abrir", 2.0)
    control.cerrar()   # ya no hace falta el canal de control -- lo cerramos limpio antes del kill

    resultado_hilo = {}
    def intenta_abrir():
        try:
            resultado_hilo["oid"] = cliente.abrir("CTA-HEDGE", "MES", -1, 4)
        except Exception as ex:
            resultado_hilo["excepcion"] = ex

    h = threading.Thread(target=intenta_abrir, daemon=True)
    t0 = time.monotonic()
    h.start()
    time.sleep(0.4)   # asegurar que el hilo servidor ya está dormido dentro de retrasar_respuesta
    assert proc.poll() is None, "el servidor no debería haber muerto todavia"
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=3)
    h.join(timeout=5.0)
    dt = time.monotonic() - t0

    print(f"  tras SIGKILL: resultado_hilo={resultado_hilo}  dt={dt:.2f}s  proc.returncode={proc.returncode}")
    ok("el proceso servidor murió de verdad (SIGKILL, returncode negativo = señal)",
       proc.returncode is not None and proc.returncode < 0, proc.returncode)
    ok("abrir() propaga ConexionPerdida (no se cuelga, no da un resultado fantasma)",
       "excepcion" in resultado_hilo and isinstance(resultado_hilo["excepcion"], ConexionPerdida),
       resultado_hilo.get("excepcion"))
    ok("la excepcion llega en un tiempo acotado, MUCHO antes del timeout_operacion=5s "
       "(el kernel cierra el socket en cuanto muere el proceso, no hace falta esperar el timeout)",
       dt < 2.5, f"dt={dt:.2f}s")

    t0 = time.monotonic()
    r = cliente.hay_conexion("CTA-HEDGE")
    dt2 = time.monotonic() - t0
    ok("hay_conexion() tras la caida real: False, y RAPIDO (no espera ningun timeout)",
       r is False and dt2 < 1.0, f"resultado={r} dt={dt2:.2f}s")

finally:
    para_servidor_si_vivo(proc, fichero_info)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
