# -*- coding: utf-8 -*-
"""servidor.py · simulador_nt8

`ServidorNT8Simulado`: el PROCESO independiente que "responde como NT8" --
ver `simulador_nt8/LEEME.md` para el aviso de qué es y qué NO es esto.
Escucha en DOS sockets `AF_UNIX` (nunca TCP -- inalcanzable desde fuera de
esta máquina por diseño, no solo por configuración):

  - `nt8.sock`         -- canal de DATOS: solo los diez métodos del puerto
                          de `07_ADAPTADOR_NT8.md` §1.
  - `nt8.control.sock` -- canal de CONTROL: solo métodos `test_*`
                          (fábricas de escenario de `AdaptadorFalso` +
                          `test_congelar`/`test_retrasar_respuesta` de
                          `motor.py`). Solo lo usan los arneses de prueba,
                          NUNCA el bot.

El estado (cuentas, órdenes, posiciones) vive en `MotorSimulado`, dentro de
la memoria de ESTE proceso -- independiente de cualquier conexión. Es la
propiedad que hace posible el escenario (b) del plan de pruebas: matar el
proceso del bot no toca este proceso ni su estado.

Arranca con `python -m simulador_nt8 --entorno=pruebas ...` -- se niega a
arrancar sin ese flag exacto (ver `main()`), salvaguarda en código, no solo
en prosa, contra usarlo por error fuera de un arnés de pruebas."""
import argparse
import json
import os
import signal
import socket
import sys
import threading
import time

from .motor import MotorSimulado
from .protocolo import LectorLineas, escribir_mensaje
from .errores import ErrorSimuladorNT8

METODOS_CONTRATO = frozenset({
    "arrancar", "parar", "hay_conexion", "leer_cuenta", "abrir",
    "aplanar", "cancelar", "leer_estado_orden", "leer_fill", "leer_posicion",
    "coloca_bracket",  # D8.2, ORDEN_DE_TRABAJO_D8.md §1: operación de salida en reposo
    "leer_fill_detalle",  # D9 §3.4/3.6 fusionadas: feed_origen + cadena de timestamps
})

# métodos del puerto cuyo resultado es una TUPLA en AdaptadorFalso -- JSON no
# tiene tuplas, así que se serializan como objeto con claves nombradas (el
# cliente las reconstruye a tupla, ver cliente.py).
_SERIALIZADORES_TUPLA = {
    "leer_fill": lambda r: {"llena": r[0], "cantidad_llenada": r[1], "precio_medio": r[2]},
    "leer_posicion": lambda r: {"cantidad_neta": r[0], "precio_referencia": r[1]},
}


def _serializa_resultado(metodo, resultado):
    serializador = _SERIALIZADORES_TUPLA.get(metodo)
    return serializador(resultado) if serializador else resultado


def _args_serializables(args):
    """Serializa `excepcion.args` tal cual, para que el cliente pueda
    reconstruir `cls(*args)` -- NO `str(excepcion)`: varias excepciones de
    builtins (KeyError es el caso que lo cazó en R3, Fase 2 -- ver
    verificacion_R3/integracion_proceso_real/prueba_paridad_adaptador_falso.py)
    aplican repr() a sus propios args en __str__(), así que reconstruir a
    partir del string ya-representado y volver a formatear produce un
    repr() anidado -- la única reconstrucción fiel es a partir de los
    argumentos originales del constructor, no de su representación textual."""
    try:
        json.dumps(list(args))
        return list(args)
    except TypeError:
        return [str(args[0]) if args else ""]


class ServidorNT8Simulado:
    def __init__(self, dir_sockets, entorno):
        if entorno != "pruebas":
            raise ValueError(
                "ServidorNT8Simulado se niega a arrancar sin entorno='pruebas' explícito -- "
                "esto es una herramienta de pruebas (verificacion_R3/), NUNCA una vía hacia "
                "una cuenta real. Ver simulador_nt8/LEEME.md.")
        self.dir_sockets = dir_sockets
        self.ruta_datos = os.path.join(dir_sockets, "nt8.sock")
        self.ruta_control = os.path.join(dir_sockets, "nt8.control.sock")
        self.ruta_pid = os.path.join(dir_sockets, "nt8.pid")
        self.ruta_latido = os.path.join(dir_sockets, "nt8.latido.json")
        self.motor = MotorSimulado()
        self._sock_datos = None
        self._sock_control = None
        self._parando = threading.Event()
        self._hilos_conexion = []

    # --- arranque / limpieza de sockets huérfanos ------------------------
    def _limpia_si_huerfano(self, ruta):
        if not os.path.exists(ruta):
            return
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(ruta)
            s.close()
            raise RuntimeError(
                f"ya hay un servidor vivo escuchando en {ruta} -- no se arranca un segundo")
        except ConnectionRefusedError:
            os.remove(ruta)  # confirmado huérfano: nadie escucha ahí ya
        except FileNotFoundError:
            pass

    def _escucha(self, ruta):
        self._limpia_si_huerfano(ruta)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(ruta)
        os.chmod(ruta, 0o600)
        s.listen(8)
        return s

    def arranca(self):
        os.makedirs(self.dir_sockets, exist_ok=True)
        os.chmod(self.dir_sockets, 0o700)
        self._sock_datos = self._escucha(self.ruta_datos)
        self._sock_control = self._escucha(self.ruta_control)
        with open(self.ruta_pid, "w") as fh:
            fh.write(str(os.getpid()))
        hilo_latido = threading.Thread(target=self._bucle_latido, daemon=True)
        hilo_latido.start()
        hilo_datos = threading.Thread(target=self._bucle_acepta,
                                       args=(self._sock_datos, METODOS_CONTRATO, False), daemon=True)
        hilo_control = threading.Thread(target=self._bucle_acepta,
                                         args=(self._sock_control, None, True), daemon=True)
        hilo_datos.start()
        hilo_control.start()
        return hilo_datos, hilo_control

    # --- latido del propio proceso servidor (distinto de hay_conexion) --
    def _bucle_latido(self):
        # Sin fsync a propósito: es un fichero diagnóstico de refresco muy
        # rápido (~200 ms), no estado de negocio durable como estado.json
        # (bot/estado.py::guardar() SÍ hace fsync, y con razón: eso es
        # dinero). Aquí el rename ya es atómico en el mismo filesystem;
        # perder el último latido en un crash de la propia máquina no
        # importa, porque el próximo se escribe 200 ms después.
        tmp = self.ruta_latido + ".tmp"
        while not self._parando.is_set():
            obj = {"pid": os.getpid(), "ts": time.time()}
            with open(tmp, "w") as fh:
                json.dump(obj, fh)
            os.replace(tmp, self.ruta_latido)
            self._parando.wait(0.2)

    # --- aceptar conexiones -----------------------------------------------
    def _bucle_acepta(self, sock_escucha, metodos_permitidos, es_control):
        while not self._parando.is_set():
            try:
                conn, _ = sock_escucha.accept()
            except OSError:
                return  # el socket se cerró (parada ordenada)
            h = threading.Thread(target=self._atiende_conexion,
                                  args=(conn, metodos_permitidos, es_control), daemon=True)
            h.start()
            self._hilos_conexion.append(h)

    def _atiende_conexion(self, conn, metodos_permitidos, es_control):
        lector = LectorLineas(conn)
        try:
            while True:
                peticion = lector.leer_mensaje()
                self._despacha(conn, peticion, metodos_permitidos, es_control)
        except ErrorSimuladorNT8:
            pass  # conexión cerrada por el peer -- fin normal de esta conexión
        except Exception:
            pass  # cualquier otra rotura de framing: cerrar y ya
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _despacha(self, conn, peticion, metodos_permitidos, es_control):
        id_ = peticion.get("id")
        metodo = peticion.get("metodo", "")
        args = peticion.get("args", {})
        if es_control:
            if not metodo.startswith("test_"):
                escribir_mensaje(conn, {"id": id_, "ok": False,
                                  "error": {"tipo": "metodo_no_permitido_en_este_puerto",
                                            "mensaje": f"'{metodo}' no es un metodo test_* del canal de control"}})
                return
            objetivo = self.motor
        else:
            if metodo not in metodos_permitidos:
                escribir_mensaje(conn, {"id": id_, "ok": False,
                                  "error": {"tipo": "metodo_no_permitido_en_este_puerto",
                                            "mensaje": f"'{metodo}' no es un metodo del puerto de "
                                                       "07_ADAPTADOR_NT8.md §1 (o pertenece al canal de control)"}})
                return
            objetivo = self.motor
        try:
            if es_control:
                # invocar_control(), NUNCA getattr(objetivo, metodo)(**args) directo --
                # ver MotorSimulado.invocar_control(): mismo lock que el canal de
                # datos (revisión adversarial, lente concurrencia_y_estado), y la
                # exclusión explícita de test_congelar/test_liberar_congelacion que
                # evita el deadlock que ese lock introduciría si no se excluyeran.
                resultado = objetivo.invocar_control(metodo, args)
            else:
                resultado = objetivo.invocar(metodo, args)
            escribir_mensaje(conn, {"id": id_, "ok": True,
                                     "resultado": _serializa_resultado(metodo, resultado)})
        except Exception as ex:
            escribir_mensaje(conn, {"id": id_, "ok": False,
                              "error": {"tipo": type(ex).__name__, "modulo": type(ex).__module__,
                                        "mensaje": str(ex), "args": _args_serializables(ex.args)}})

    # --- parada ordenada (SIGTERM) -- deliberadamente SIN protección ----
    # contra SIGKILL: el diseño necesita poder infligir justo eso (escenario a).
    def para(self):
        self._parando.set()
        for s in (self._sock_datos, self._sock_control):
            try:
                s.close()
            except OSError:
                pass
        for ruta in (self.ruta_datos, self.ruta_control, self.ruta_pid, self.ruta_latido):
            try:
                os.remove(ruta)
            except FileNotFoundError:
                pass


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entorno", required=True,
                     help="DEBE ser 'pruebas' -- el servidor se niega a arrancar con cualquier otro valor")
    ap.add_argument("--dir-sockets", default=None,
                     help="directorio para los sockets/pid/latido -- por defecto uno nuevo bajo /dev/shm")
    ap.add_argument("--fichero-info", default=None,
                     help="si se da, se escribe aquí {\"dir_sockets\": ...} en cuanto el servidor "
                          "está escuchando -- señal de 'listo' para el arnés de pruebas, más "
                          "robusta que hacer polling ciego contra un socket que podría no existir "
                          "todavía por otro motivo")
    args = ap.parse_args(argv)

    dir_sockets = args.dir_sockets
    if dir_sockets is None:
        base = "/dev/shm" if os.path.isdir("/dev/shm") else __import__("tempfile").gettempdir()
        dir_sockets = os.path.join(base, f"nt8sim-{os.urandom(4).hex()}")

    srv = ServidorNT8Simulado(dir_sockets, args.entorno)
    hilo_datos, hilo_control = srv.arranca()
    print(f"simulador_nt8: escuchando en {dir_sockets}", flush=True)

    if args.fichero_info:
        tmp = args.fichero_info + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"dir_sockets": dir_sockets, "pid": os.getpid()}, fh)
        os.replace(tmp, args.fichero_info)

    detener = threading.Event()
    def _maneja_sigterm(signum, frame):
        detener.set()
    signal.signal(signal.SIGTERM, _maneja_sigterm)

    try:
        while not detener.is_set():
            detener.wait(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        srv.para()
        print("simulador_nt8: parado", flush=True)


if __name__ == "__main__":
    main()
