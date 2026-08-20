# -*- coding: utf-8 -*-
"""cliente.py · simulador_nt8

`AdaptadorSimuladorNT8`: implementa el mismo contrato de puerto que
`bot/adaptador_falso.py::AdaptadorFalso` (`07_ADAPTADOR_NT8.md` §1), pero
cada llamada hace una IDA Y VUELTA real por un socket `AF_UNIX` contra un
proceso `simulador_nt8.servidor` aparte -- sustituto inyectable de
`AdaptadorFalso` en el mismo punto de `bot/protocolo_dos_patas.py` que ya
recibe `adaptador=` como primer argumento.

ESTO NO ES adaptadores/ (el adaptador real de D-A, bloqueado por D-A1
contra NT8 real) -- ver `simulador_nt8/LEEME.md`. Esta clase no habla con
NT8 ni con la ATI: habla con `simulador_nt8.servidor`, que a su vez envuelve
`AdaptadorFalso`. Lo que SÍ prueba de verdad, que `AdaptadorFalso` en
proceso estructuralmente no puede: el protocolo de las dos patas, el
vigía de conexión, y la reconciliación de arranque bajo una frontera de
proceso/red real -- matando procesos, con reloj de pared real.

Regla de diseño NO NEGOCIABLE (ver errores.py): el socket de operación
SIEMPRE tiene `settimeout()` finito tras conectar. Un servidor congelado o
muerto degrada a `TimeoutOrden`/`ConexionPerdida`, capturables, nunca a un
bloqueo indefinido del hilo que llama."""
import builtins
import itertools
import socket

from .errores import (ConexionPerdida, ErrorSimuladorNT8, LineaDemasiadoLarga,
                       ProtocoloCorrupto, ServidorNoDisponible, TimeoutOrden)
from .protocolo import LectorLineas, escribir_mensaje


class ErrorRemotoDominio(Exception):
    """Envoltorio para un error de dominio devuelto por el servidor cuyo
    tipo NO es una excepción de `builtins` reconstruible (p.ej.
    'metodo_no_permitido_en_este_puerto') -- se conserva el tipo/mensaje
    originales como atributos en vez de perderlos."""
    def __init__(self, tipo, mensaje):
        super().__init__(f"{tipo}: {mensaje}")
        self.tipo_remoto = tipo
        self.mensaje_remoto = mensaje


class AdaptadorSimuladorNT8:
    def __init__(self, ruta_socket_datos, timeout_conexion=2.0, timeout_operacion=5.0):
        self._ruta = ruta_socket_datos
        self._timeout_conexion = timeout_conexion
        self._timeout_operacion = timeout_operacion
        self._sock = None
        self._lector = None
        self._conectado = False
        self._contador_id = itertools.count(1)

    # --- ciclo de vida (07_ADAPTADOR_NT8.md §1: arrancar/parar) ----------
    def arrancar(self):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(self._timeout_conexion)
            s.connect(self._ruta)
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            return False
        s.settimeout(self._timeout_operacion)   # SIEMPRE finito de aquí en adelante -- no negociable
        self._sock, self._lector, self._conectado = s, LectorLineas(s), True
        try:
            return bool(self._enviar("arrancar", {}))   # delega también a AdaptadorFalso.arrancar()
        except ErrorSimuladorNT8:
            self._cierra_local()
            return False

    def parar(self):
        if not self._conectado:
            return True
        try:
            resultado = bool(self._enviar("parar", {}))
        except ErrorSimuladorNT8:
            resultado = True   # ya no hay nadie al otro lado -- "parado" es un estado correcto
        finally:
            self._cierra_local()
        return resultado

    def _cierra_local(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock, self._lector, self._conectado = None, None, False

    # --- puerto -----------------------------------------------------------
    def hay_conexion(self, cuenta):
        """A diferencia de las demás operaciones, ESTA NUNCA lanza por un
        fallo de transporte -- es la propia comprobación que el resto del
        bot usa para decidir si algo más es seguro; lanzar aquí sería
        contradecir su propio propósito (07_ADAPTADOR_NT8.md §1: 'se
        comprueba antes de cada operación; nunca se asume')."""
        if not self._conectado:
            return False
        try:
            return bool(self._enviar("hay_conexion", {"cuenta": cuenta}))
        except (ConexionPerdida, TimeoutOrden, ServidorNoDisponible):
            return False

    def leer_cuenta(self, cuenta):
        return self._enviar("leer_cuenta", {"cuenta": cuenta})

    def abrir(self, cuenta, instrumento, direccion, cantidad, comportamiento=None):
        return self._enviar("abrir", {"cuenta": cuenta, "instrumento": instrumento,
                             "direccion": direccion, "cantidad": cantidad,
                             "comportamiento": comportamiento})

    def aplanar(self, cuenta, instrumento, comportamiento=None):
        return self._enviar("aplanar", {"cuenta": cuenta, "instrumento": instrumento,
                             "comportamiento": comportamiento})

    def cancelar(self, order_id):
        return self._enviar("cancelar", {"order_id": order_id})

    def leer_estado_orden(self, order_id):
        return self._enviar("leer_estado_orden", {"order_id": order_id})

    def leer_fill(self, order_id):
        r = self._enviar("leer_fill", {"order_id": order_id})
        return (r["llena"], r["cantidad_llenada"], r["precio_medio"])

    def leer_posicion(self, cuenta, instrumento):
        r = self._enviar("leer_posicion", {"cuenta": cuenta, "instrumento": instrumento})
        return (r["cantidad_neta"], r["precio_referencia"])

    # --- núcleo compartido -------------------------------------------------
    def _enviar(self, metodo, args):
        if not self._conectado:
            raise ServidorNoDisponible(f"no conectado -- llama a arrancar() antes de '{metodo}'")
        id_ = next(self._contador_id)
        try:
            escribir_mensaje(self._sock, {"id": id_, "metodo": metodo, "args": args})
        except LineaDemasiadoLarga:
            raise
        except (BrokenPipeError, ConnectionResetError, OSError) as ex:
            self._cierra_local()
            raise ConexionPerdida(f"fallo al mandar '{metodo}': {ex}") from ex
        try:
            resp = self._lector.leer_mensaje()
        except socket.timeout as ex:
            # el servidor puede seguir vivo (p.ej. congelado a proposito) --
            # NO se cierra la conexion local: quien llama debe reconsultar
            # leer_estado_orden()/leer_posicion() para saber que paso de
            # verdad, nunca asumir que la orden no se mando (errores.py).
            raise TimeoutOrden(metodo, self._timeout_operacion) from ex
        except ConexionPerdida:
            self._cierra_local()
            raise
        if resp.get("id") != id_:
            self._cierra_local()
            raise ProtocoloCorrupto(
                f"id de respuesta {resp.get('id')!r} no corresponde a la peticion {id_!r} "
                f"('{metodo}') -- framing roto, no se puede seguir usando esta conexion")
        if resp.get("ok"):
            return resp.get("resultado")
        error = resp.get("error", {})
        raise self._reconstruye_error(error)

    def _reconstruye_error(self, error):
        tipo = error.get("tipo", "ErrorDesconocido")
        modulo = error.get("modulo", "")
        mensaje = error.get("mensaje", "")
        args = error.get("args", [mensaje])
        if modulo == "builtins":
            cls = getattr(builtins, tipo, None)
            if isinstance(cls, type) and issubclass(cls, BaseException):
                # cls(*args), NUNCA cls(mensaje) -- ver _args_serializables()
                # en servidor.py: reconstruir a partir del str() ya
                # formateado produce un repr() anidado en excepciones como
                # KeyError, que aplican repr() a sus propios args en
                # __str__(). Reconstruir desde los args originales del
                # constructor es la vía más fiel -- PERO no es infalible:
                # servidor.py::_args_serializables solo garantiza que los
                # args son serializables a JSON, no que sean los tipos
                # exactos que el constructor de `cls` espera (revisión
                # adversarial 20-08-2026, lente fidelidad_puerto:
                # UnicodeDecodeError exige tipos concretos -- bytes, dos
                # int -- que un roundtrip por JSON/str() no reconstruye;
                # reproducido en vivo, cls(*args) lanzaba TypeError de
                # aridad, sustituyendo el error de dominio real por uno de
                # transporte confuso). Si la reconstrucción falla, se
                # degrada con pérdida de fidelidad documentada (se pierde
                # el tipo exacto, se conservan tipo+mensaje originales como
                # atributos) en vez de dejar escapar un TypeError ajeno.
                try:
                    return cls(*args)
                except Exception:
                    pass
        return ErrorRemotoDominio(tipo, mensaje)
