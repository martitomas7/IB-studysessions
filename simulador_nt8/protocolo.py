# -*- coding: utf-8 -*-
"""protocolo.py · simulador_nt8 (herramienta de pruebas, NO es adaptadores/)

Framing JSON Lines compartido por `servidor.py` y los dos clientes
(`cliente.py`, `cliente_control.py`): un objeto JSON UTF-8 por línea,
terminado en `\\n`. Se elige framing por delimitador (no por prefijo de
longitud) para que el protocolo se pueda hablar a mano con
`socat - UNIX-CONNECT:nt8.sock` o `nc -U` mientras se depura -- coherente
con el principio de este simulador: "se puede fabricar a propósito, de
forma determinista, cualquier escenario que R3 exija ver fallar" (mismo
principio que `bot/adaptador_falso.py`, ahora cruzando una frontera real de
proceso).

ESTE MÓDULO NO ES adaptadores/ (D-A, bloqueado por D-A1 contra NT8 real) --
ver `simulador_nt8/LEEME.md`.
"""
import json

from .errores import ArgumentoNoSerializable, ConexionPerdida, LineaDemasiadoLarga

LIMITE_LINEA = 1_048_576  # 1 MiB -- cota de cordura, no un numero de negocio (R2 no aplica: es
                           # ingenieria interna del transporte, no una cifra citada por la norma)


def escribir_mensaje(sock, obj):
    """Serializa `obj` a una línea JSON y la manda entera por el socket.
    `sendall` ya garantiza que se manda todo o lanza -- no hace falta bucle
    propio de escritura.

    Revisión adversarial 20-08-2026 (lente fidelidad_puerto): `json.dumps`
    puede fallar (un `comportamiento`/`args` con algo no serializable,
    p.ej. un callable) -- antes esto dejaba escapar un `TypeError` crudo
    de `json`, sin relación con la jerarquía de `errores.py`. Se envuelve
    y se relanza como `ArgumentoNoSerializable`, con tipo conocido."""
    try:
        datos = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
    except TypeError as ex:
        raise ArgumentoNoSerializable(f"argumento no serializable a JSON: {ex}") from ex
    if len(datos) > LIMITE_LINEA:
        raise LineaDemasiadoLarga(len(datos))
    sock.sendall(datos)


class LectorLineas:
    """Envuelve un socket y entrega mensajes JSON completos, uno por línea --
    acumulando en un buffer propio hasta que aparece el delimitador, porque
    NADA garantiza que un mensaje llegue en una sola llamada a `recv()`: el
    kernel puede fragmentar un envío en varios trozos, o coalescer varios
    mensajes en un solo `recv()` (el resto queda en el buffer para la
    siguiente llamada a `leer_mensaje()`). Una implementación que solo mira
    el primer `recv()` funciona en el caso feliz de loopback con mensajes
    pequeños y falla exactamente cuando más hace falta que no falle -- por
    eso esto tiene su propia prueba R3 antes que cualquier otra pieza del
    simulador (ver verificacion_R3/integracion_proceso_real/
    prueba_protocolo_framing.py, Fase 0)."""

    def __init__(self, sock):
        self._sock = sock
        self._buf = bytearray()

    def leer_mensaje(self):
        while b"\n" not in self._buf:
            if len(self._buf) > LIMITE_LINEA:
                raise LineaDemasiadoLarga(len(self._buf))
            trozo = self._sock.recv(4096)
            if trozo == b"":
                raise ConexionPerdida("EOF del peer (conexion cerrada)")
            self._buf.extend(trozo)
        linea, resto = self._buf.split(b"\n", 1)
        self._buf = resto
        return json.loads(linea.decode("utf-8"))
