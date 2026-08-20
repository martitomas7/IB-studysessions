# -*- coding: utf-8 -*-
"""D8.2 · ORDEN_DE_TRABAJO_D8.md §1 · puerta R3 EXACTA que pide el pedido de
trabajo: "fabrica en el simulador un día en que las DOS órdenes en reposo
podrían dispararse, y demuestra que solo una queda y la otra se cancela
confirmada." Cruza la frontera de proceso real (servidor `simulador_nt8`
aparte, socket AF_UNIX)."""
import os
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, ING)

from simulador_nt8.cliente import AdaptadorSimuladorNT8
from simulador_nt8.cliente_control import ClienteControl

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def arranca_servidor():
    dir_sockets = f"/tmp/nt8sim_bracket_{os.getpid()}"
    fichero_info = f"/tmp/nt8sim_bracket_info_{os.getpid()}.json"
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


print("=== D8.2 end-to-end: un día en que las DOS podrían dispararse -- solo una queda, "
      "la otra se cancela CONFIRMADA ===")
proc, dir_sockets, fichero_info = arranca_servidor()
try:
    ruta_datos = os.path.join(dir_sockets, "nt8.sock")
    ruta_control = os.path.join(dir_sockets, "nt8.control.sock")
    control = ClienteControl(ruta_control)
    cliente = AdaptadorSimuladorNT8(ruta_datos, timeout_operacion=10.0)
    assert cliente.arrancar() is True

    # abre la pata prop de verdad (p0 = precio de cierre de la barra de
    # entrada, aquí un valor de prueba cualquiera -- lo que importa es la
    # relación con precio_stop/precio_limite)
    oid_prop = cliente.abrir("CTA-PROP", "MES", 1, 10)
    cliente.leer_estado_orden(oid_prop)
    ok("la prop está abierta antes de colocar el bracket",
       cliente.leer_posicion("CTA-PROP", "MES")[0] == 10)

    b = cliente.coloca_bracket("CTA-PROP", "MES", direccion_cierre=-1, cantidad=10,
                                precio_stop=4990.0, precio_limite=5010.0)
    ok("coloca_bracket() por el puerto real devuelve las dos patas + el grupo",
       {"order_id_stop", "order_id_limite", "id_grupo_oco"} <= set(b), b)
    ok("las dos patas están vivas (ACEPTADA) -- 'podrían dispararse las dos'",
       cliente.leer_estado_orden(b["order_id_stop"]) == "ACEPTADA"
       and cliente.leer_estado_orden(b["order_id_limite"]) == "ACEPTADA")

    # el "día" resuelve: el precio toca el suelo primero (mismo criterio que
    # R-3.3 del modelo -- el suelo gana el empate si las dos tocan la misma
    # barra) -- se fabrica desde el canal de CONTROL, cruzando el socket real
    control.fabrica_resolucion_bracket(b["id_grupo_oco"], "stop")

    estado_stop = cliente.leer_estado_orden(b["order_id_stop"])
    estado_lim = cliente.leer_estado_orden(b["order_id_limite"])
    ok("solo UNA pata queda LLENA (el stop)", estado_stop == "LLENA", estado_stop)
    ok("la OTRA queda CANCELADA -- confirmada por el puerto real, no solo en el simulador",
       estado_lim == "CANCELADA", estado_lim)

    # confirmación EXPLÍCITA vía cancelar() -- D8.4 la llamará como defensa
    # idempotente de respaldo tras ver la pata ganadora LLENA (ver la
    # síntesis de diseño: "D8 vigila igualmente y cancela por su cuenta")
    r_confirmacion = cliente.cancelar(b["order_id_limite"])
    ok("cancelar() de respaldo sobre la ya-cancelada es idempotente (sigue CANCELADA, "
       "no lanza, no cambia nada)", r_confirmacion == "CANCELADA", r_confirmacion)

    llena, cantidad_llenada, precio_fill = cliente.leer_fill(b["order_id_stop"])
    ok("el fill del stop es EXACTO al nivel pedido (pass 1: sin deslizamiento)",
       llena is True and precio_fill == 4990.0, (llena, cantidad_llenada, precio_fill))
finally:
    para_servidor(proc, fichero_info)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
