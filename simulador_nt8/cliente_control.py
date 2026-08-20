# -*- coding: utf-8 -*-
"""cliente_control.py · simulador_nt8

`ClienteControl`: habla el canal de CONTROL (`nt8.control.sock`) para
fabricar a propósito los escenarios que R3 exige poder ver -- SOLO lo usan
los arneses de prueba, NUNCA el bot (que solo conoce `cliente.py` /
`AdaptadorSimuladorNT8`, indistinguible de `AdaptadorFalso` desde su punto
de vista). Misma idea que `bot/adaptador_falso.py::programa_abrir()` /
`desconecta()` / `fuerza_fill()`, ahora accionables desde OTRO proceso
mientras el servidor sigue corriendo -- lo que hace posible apretar un
gatillo (congelar, desconectar, forzar un fill) DESDE FUERA del proceso
que está siendo puesto a prueba, sin que ese proceso sepa que existe este
canal."""
import itertools
import socket

from .errores import ConexionPerdida, ProtocoloCorrupto, ServidorNoDisponible, TimeoutOrden
from .protocolo import LectorLineas, escribir_mensaje


class ClienteControl:
    def __init__(self, ruta_socket_control, timeout_conexion=2.0, timeout_operacion=5.0):
        self._ruta = ruta_socket_control
        self._timeout_operacion = timeout_operacion
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout_conexion)
        try:
            s.connect(ruta_socket_control)
        except (FileNotFoundError, ConnectionRefusedError, OSError) as ex:
            raise ServidorNoDisponible(f"no se pudo conectar al canal de control: {ex}") from ex
        s.settimeout(timeout_operacion)
        self._sock = s
        self._lector = LectorLineas(s)
        self._contador_id = itertools.count(1)

    def cerrar(self):
        try:
            self._sock.close()
        except OSError:
            pass

    # --- núcleo genérico, por reflexión en el servidor -----------------
    def _llamar(self, nombre_sin_prefijo, **kwargs):
        metodo = f"test_{nombre_sin_prefijo}"
        id_ = next(self._contador_id)
        try:
            escribir_mensaje(self._sock, {"id": id_, "metodo": metodo, "args": kwargs})
            resp = self._lector.leer_mensaje()
        except socket.timeout as ex:
            raise TimeoutOrden(metodo, self._timeout_operacion) from ex
        except ConexionPerdida:
            raise
        if resp.get("id") != id_:
            raise ProtocoloCorrupto(f"id desincronizado en canal de control: esperaba {id_}, "
                                     f"llegó {resp.get('id')!r}")
        if resp.get("ok"):
            return resp.get("resultado")
        error = resp.get("error", {})
        raise RuntimeError(f"{error.get('tipo')}: {error.get('mensaje')}")

    # --- envoltorios ergonómicos -- mismos nombres que AdaptadorFalso ---
    def programa_abrir(self, cuenta, instrumento, **comportamiento):
        return self._llamar("programa_abrir", cuenta=cuenta, instrumento=instrumento, **comportamiento)

    def programa_aplanar(self, cuenta, instrumento, resultados):
        return self._llamar("programa_aplanar", cuenta=cuenta, instrumento=instrumento,
                             resultados=list(resultados))

    def desconecta(self, cuenta):
        return self._llamar("desconecta", cuenta=cuenta)

    def fuerza_fill(self, order_id, precio=100.0):
        return self._llamar("fuerza_fill", order_id=order_id, precio=precio)

    def fuerza_posicion_externa(self, cuenta, instrumento, cantidad):
        return self._llamar("fuerza_posicion_externa", cuenta=cuenta,
                             instrumento=instrumento, cantidad=cantidad)

    def activa_rechazo_cantidad_cero(self, activo=True):
        return self._llamar("activa_rechazo_cantidad_cero", activo=activo)

    def congelar(self):
        return self._llamar("congelar")

    def liberar_congelacion(self):
        return self._llamar("liberar_congelacion")

    def retrasar_respuesta(self, metodo, segundos):
        return self._llamar("retrasar_respuesta", metodo=metodo, segundos=segundos)
