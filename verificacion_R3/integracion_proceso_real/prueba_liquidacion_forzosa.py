# -*- coding: utf-8 -*-
"""D8.3 · ORDEN_DE_TRABAJO_D8.md §1 · puerta R3 EXACTA que pide el pedido de
trabajo: "desde el canal de control del simulador, poner la posición prop a
cero sin orden del bot. El bot tiene que cerrar el hedge y no quedarse
esperando." Cruza la frontera de proceso real (servidor `simulador_nt8`
aparte, socket AF_UNIX) -- mismo patrón que
`prueba_carrera_cancelar_vs_fill.py`."""
import os
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, ING)

from bot.deteccion_liquidacion import detecta_liquidacion_forzosa, resuelve_liquidacion_forzosa
from simulador_nt8.cliente import AdaptadorSimuladorNT8
from simulador_nt8.cliente_control import ClienteControl

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def arranca_servidor():
    dir_sockets = f"/tmp/nt8sim_liq_{os.getpid()}"
    fichero_info = f"/tmp/nt8sim_liq_info_{os.getpid()}.json"
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


print("=== D8.3 end-to-end: liquidación forzosa detectada y resuelta cruzando el socket real ===")
proc, dir_sockets, fichero_info = arranca_servidor()
try:
    ruta_datos = os.path.join(dir_sockets, "nt8.sock")
    ruta_control = os.path.join(dir_sockets, "nt8.control.sock")
    control = ClienteControl(ruta_control)
    cliente = AdaptadorSimuladorNT8(ruta_datos, timeout_operacion=10.0)
    assert cliente.arrancar() is True

    # abre las dos patas de verdad, por el puerto real (canal de datos)
    oid_hedge = cliente.abrir("CTA-HEDGE", "MES", -1, 4)
    oid_prop = cliente.abrir("CTA-PROP", "MES", 1, 10)
    cliente.leer_estado_orden(oid_hedge)
    cliente.leer_estado_orden(oid_prop)
    ok("las dos patas están abiertas de verdad antes de la liquidación",
       cliente.leer_posicion("CTA-HEDGE", "MES")[0] == -4
       and cliente.leer_posicion("CTA-PROP", "MES")[0] == 10)

    # el bot NO ha mandado ninguna orden de cierre todavía (D8.2 -- el
    # bracket en reposo -- aún no existe como pieza integrada) -- el canal
    # de CONTROL pone la posición a cero DIRECTAMENTE, sin pasar por
    # ninguna orden: exactamente "el proveedor liquidó por su cuenta",
    # que es el escenario que D8.3 tiene que cazar. La lista de "órdenes de
    # cierre propias conocidas" que se le pasa al detector está vacía a
    # propósito -- es justo lo que D8.4 vería si la liquidación llega antes
    # de que el bot alcance a colocar ningún bracket de salida.
    control.fuerza_posicion_externa("CTA-PROP", "MES", 0)
    ok("el canal de CONTROL puso la posición prop a cero SIN ninguna orden del bot",
       cliente.leer_posicion("CTA-PROP", "MES")[0] == 0)

    t0 = time.monotonic()
    es_liq = detecta_liquidacion_forzosa(cliente, "CTA-PROP", "MES",
                                          cantidad_esperada=10,
                                          ordenes_propias_conocidas=[])
    ok("el bot DETECTA la liquidación forzosa por el puerto real (leer_posicion)",
       es_liq is True, es_liq)

    r = resuelve_liquidacion_forzosa(cliente, "CTA-HEDGE", "MES")
    dt = time.monotonic() - t0
    ok("el bot cierra el hedge de inmediato -- NO se queda esperando ningún timeout "
       "(la vuelta completa detectar+cerrar tarda muy poco, no algo del orden de N/N_hedge)",
       dt < 2.0, f"dt={dt:.3f}s")
    ok("el hedge queda confirmado en cero por el puerto real",
       r['cerrado'] is True and cliente.leer_posicion("CTA-HEDGE", "MES")[0] == 0, r)
    ok("se anotó el evento LIQUIDACION_FORZOSA (nivel_propuesto='N2')",
       any(e.get('tipo') == 'LIQUIDACION_FORZOSA' for e in r['eventos']), r['eventos'])
finally:
    para_servidor(proc, fichero_info)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
