# -*- coding: utf-8 -*-
"""Fase 1 (R3): simulador_nt8.servidor arrancado como PROCESO APARTE de
verdad (subprocess.Popen), hablado a mano por socket AF_UNIX -- sin pasar
por cliente.py todavía, para verificar el protocolo con independencia de
si el cliente está bien escrito.

R3: antes de que `servidor.py` existiera, este mismo guion de conexión daba
`FileNotFoundError` al intentar conectar -- confirma que el arnés detecta
correctamente la ausencia del servidor, no un falso verde. Con el servidor
real arrancado, debe conectar y responder al protocolo tal cual está
documentado en la síntesis de diseño."""
import json
import os
import signal
import socket
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, ING)

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def habla_a_mano(ruta_socket, mensaje, timeout=3.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(ruta_socket)
    s.sendall((json.dumps(mensaje) + "\n").encode("utf-8"))
    buf = b""
    while b"\n" not in buf:
        buf += s.recv(4096)
    s.close()
    return json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))


print("=== Fase 1a: ANTES de arrancar el servidor -- conectar debe fallar limpio ===")
dir_prueba = f"/tmp/nt8sim_prueba_{os.getpid()}"
ruta_datos_hipotetica = os.path.join(dir_prueba, "nt8.sock")
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1.0)
    s.connect(ruta_datos_hipotetica)
    fallo_limpio = False
    detalle = "conectó -- inesperado, no debería haber ningun servidor todavia"
except FileNotFoundError as ex:
    fallo_limpio = True
    detalle = f"FileNotFoundError: {ex}"
except Exception as ex:
    fallo_limpio = False
    detalle = f"{type(ex).__name__}: {ex}"
ok("conectar sin servidor arrancado da FileNotFoundError (arnes detecta ausencia real)",
   fallo_limpio, detalle)

print("\n=== Fase 1b: arrancar el servidor REAL como subproceso, hablar el protocolo a mano ===")
fichero_info = os.path.join("/tmp", f"nt8sim_info_{os.getpid()}.json")
proc = subprocess.Popen(
    [sys.executable, "-m", "simulador_nt8", "--entorno=pruebas",
     "--dir-sockets", dir_prueba, "--fichero-info", fichero_info],
    cwd=ING, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    t0 = time.monotonic()
    info = None
    while time.monotonic() - t0 < 5.0:
        if os.path.exists(fichero_info):
            try:
                info = json.load(open(fichero_info))
                break
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.02)
    ok("el fichero de info aparece dentro de 5s (servidor arrancó de verdad)", info is not None, info)

    ruta_datos = os.path.join(dir_prueba, "nt8.sock")
    ruta_control = os.path.join(dir_prueba, "nt8.control.sock")

    r = habla_a_mano(ruta_datos, {"id": 1, "metodo": "arrancar", "args": {}})
    ok("arrancar() por el canal de datos responde ok=true, resultado=true",
       r == {"id": 1, "ok": True, "resultado": True}, r)

    r = habla_a_mano(ruta_datos, {"id": 2, "metodo": "hay_conexion", "args": {"cuenta": "MFF-1"}})
    ok("hay_conexion() responde True por defecto (sin desconectar nada)",
       r.get("ok") is True and r.get("resultado") is True, r)

    r = habla_a_mano(ruta_datos, {
        "id": 3, "metodo": "abrir",
        "args": {"cuenta": "MFF-1", "instrumento": "MES", "direccion": 1, "cantidad": 4, "comportamiento": None}})
    ok("abrir() por el canal de datos devuelve un order_id string",
       r.get("ok") is True and isinstance(r.get("resultado"), str), r)
    oid = r["resultado"]

    # AdaptadorFalso solo AVANZA el estado de una orden (y por tanto la
    # posición) cuando se lee su estado/fill -- leer_posicion() en si no
    # dispara el avance (fiel al AdaptadorFalso real, no un defecto del
    # simulador: se confirmó leyendo bot/adaptador_falso.py antes de
    # escribir esta prueba). Por eso se sondea el estado primero, tal
    # como ya hace bot/protocolo_dos_patas.py::_poll_hasta en producción.
    r = habla_a_mano(ruta_datos, {"id": 31, "metodo": "leer_estado_orden", "args": {"order_id": oid}})
    ok("leer_estado_orden() dispara el avance de la orden (LLENA, fill_en_s=0 por defecto)",
       r.get("resultado") == "LLENA", r)

    r = habla_a_mano(ruta_datos, {"id": 4, "metodo": "leer_posicion",
                                   "args": {"cuenta": "MFF-1", "instrumento": "MES"}})
    ok("leer_posicion() serializa la tupla como objeto {cantidad_neta, precio_referencia}",
       r.get("resultado") == {"cantidad_neta": 4, "precio_referencia": 100.0}, r)

    r = habla_a_mano(ruta_datos, {"id": 5, "metodo": "test_congelar", "args": {}})
    ok("un metodo test_* en el canal de DATOS se rechaza (frontera de canales real)",
       r.get("ok") is False and r["error"]["tipo"] == "metodo_no_permitido_en_este_puerto", r)

    r = habla_a_mano(ruta_control, {"id": 6, "metodo": "hay_conexion", "args": {"cuenta": "X"}})
    ok("un metodo del PUERTO en el canal de CONTROL se rechaza (frontera al reves tambien)",
       r.get("ok") is False and r["error"]["tipo"] == "metodo_no_permitido_en_este_puerto", r)

    r = habla_a_mano(ruta_control, {"id": 7, "metodo": "test_desconecta", "args": {"cuenta": "MFF-1"}})
    ok("test_desconecta() por el canal de control funciona (fabrica de AdaptadorFalso, por reflexion)",
       r.get("ok") is True, r)
    r = habla_a_mano(ruta_datos, {"id": 8, "metodo": "hay_conexion", "args": {"cuenta": "MFF-1"}})
    ok("tras test_desconecta(), hay_conexion() en el canal de datos ve la desconexion",
       r.get("resultado") is False, r)

    # Revisión adversarial 20-08-2026 (lente seguridad_robustez): antes del
    # arreglo, CUALQUIER atributo de AdaptadorFalso con el prefijo test_ era
    # alcanzable por reflexión sin filtrar -- incluidos los dunder.
    # test___init__ reseteaba TODO el estado simulado en caliente, sin
    # aviso, ok:true -- reproducido en vivo antes de cerrarlo. Ahora
    # MotorSimulado._FABRICAS_PERMITIDAS es una lista cerrada.
    for i70, metodo_prohibido in enumerate(("test___init__", "test___repr__",
                                             "test___getstate__", "test___class__")):
        r = habla_a_mano(ruta_control, {"id": 70 + i70, "metodo": metodo_prohibido, "args": {}})
        ok(f"'{metodo_prohibido}' (dunder de AdaptadorFalso) rechazado por la lista blanca del canal "
           "de control -- NO alcanzable solo por llevar el prefijo test_",
           r.get("ok") is False and r["error"]["tipo"] == "AttributeError", r)

    r = habla_a_mano(ruta_datos, {"id": 9, "metodo": "leer_estado_orden", "args": {"order_id": "NO-EXISTE"}})
    ok("un order_id inexistente da ok=false con tipo de error de dominio (KeyError), no crashea la conexion",
       r.get("ok") is False and r["error"]["tipo"] == "KeyError", r)

    # tras el error de arriba la conexion sigue viva -- una segunda peticion en la MISMA conexion funciona
    s2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s2.settimeout(3.0); s2.connect(ruta_datos)
    s2.sendall((json.dumps({"id": 10, "metodo": "hay_conexion", "args": {"cuenta": "MFF-1"}}) + "\n").encode())
    buf = b""
    while b"\n" not in buf: buf += s2.recv(4096)
    r10 = json.loads(buf.split(b"\n",1)[0].decode())
    s2.sendall((json.dumps({"id": 11, "metodo": "hay_conexion", "args": {"cuenta": "MFF-1"}}) + "\n").encode())
    buf = b""
    while b"\n" not in buf: buf += s2.recv(4096)
    r11 = json.loads(buf.split(b"\n",1)[0].decode())
    s2.close()
    ok("una conexion soporta multiples peticiones secuenciales (id correlacionado en cada una)",
       r10["id"] == 10 and r11["id"] == 11, (r10, r11))

    ok("nt8.pid escrito de verdad con el PID del subproceso",
       os.path.exists(os.path.join(dir_prueba, "nt8.pid")) and
       open(os.path.join(dir_prueba, "nt8.pid")).read().strip() == str(proc.pid),
       open(os.path.join(dir_prueba, "nt8.pid")).read() if os.path.exists(os.path.join(dir_prueba,"nt8.pid")) else "no existe")

    ruta_latido = os.path.join(dir_prueba, "nt8.latido.json")
    lat1 = json.load(open(ruta_latido))
    time.sleep(0.5)
    lat2 = json.load(open(ruta_latido))
    ok("nt8.latido.json se refresca de verdad (ts avanza entre dos lecturas separadas 0.5s)",
       lat2["ts"] > lat1["ts"], (lat1, lat2))

finally:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    for f in (fichero_info,):
        try: os.remove(f)
        except FileNotFoundError: pass

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
