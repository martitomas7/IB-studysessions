# -*- coding: utf-8 -*-
"""errores.py · simulador_nt8

Jerarquía de excepciones de TRANSPORTE del simulador fuera de proceso.
`07_ADAPTADOR_NT8.md` §1 (el puerto) no fija ninguna jerarquía de
excepciones -- describe el contrato solo en términos de valores de
retorno -- así que estas excepciones son infraestructura NUEVA, propia de
este simulador (la frontera de proceso/red que `bot/adaptador_falso.py`,
en memoria, nunca necesitó), no una violación de la especificación. Si en
el futuro `07_ADAPTADOR_NT8.md` fija una jerarquía concreta para
`adaptadores/`, esa manda (R1) y esta se revisa contra ella -- por ahora
no existe tal jerarquía que citar.

Regla de diseño no negociable (ver `cliente.py`): el socket de operación
SIEMPRE tiene `settimeout()` finito -- un servidor congelado o muerto
degrada a una de estas excepciones, capturable y con tipo conocido, nunca
a un bloqueo indefinido del hilo que llama."""


class ErrorSimuladorNT8(Exception):
    """Raíz común -- nunca se lanza directamente."""


class ServidorNoDisponible(ErrorSimuladorNT8):
    """`arrancar()` no pudo ni conectar: el socket no existe (el servidor
    nunca arrancó) o el connect() fue rechazado (socket huérfano de un
    servidor muerto sin limpiar)."""


class ConexionPerdida(ErrorSimuladorNT8):
    """El transporte se rompió a media conversación: EOF inesperado,
    `BrokenPipeError`/`ConnectionResetError` al escribir. Tras esto la
    conexión se da por muerta -- quien llama debe volver a `arrancar()`
    antes de seguir."""


class TimeoutOrden(ErrorSimuladorNT8):
    """No hubo respuesta dentro de `timeout_operacion`. A diferencia de
    `ConexionPerdida`, esto NO significa que la orden se perdiera -- el
    servidor puede seguir vivo y procesándola (p.ej. congelado a
    propósito via `test_congelar`). Quien recibe esto debe reconsultar
    `leer_estado_orden()`/`leer_posicion()` para saber el estado real,
    nunca asumir que la orden no se mandó."""

    def __init__(self, metodo, segundos):
        super().__init__(f"sin respuesta a '{metodo}' en {segundos:.1f}s")
        self.metodo = metodo
        self.segundos = segundos


class ProtocoloCorrupto(ErrorSimuladorNT8):
    """JSON inválido, o el `id` de la respuesta no corresponde al de la
    petición -- señal inequívoca de un bug de framing, no de un fallo de
    red transitorio. Fatal: no se reintenta, se cierra la conexión."""


class LineaDemasiadoLarga(ConexionPerdida):
    """Una línea superó `protocolo.LIMITE_LINEA` sin encontrar el
    delimitador `\\n` -- protege contra un peer que nunca cierra el
    mensaje (bug, o un ataque de agotamiento de memoria si esto llegara a
    exponerse más allá de localhost, que por diseño no debe pasar nunca --
    ver `servidor.py`)."""


class ArgumentoNoSerializable(ErrorSimuladorNT8):
    """Un `args` pasado a `escribir_mensaje()` contiene algo que
    `json.dumps()` no puede codificar (p.ej. un callable -- `en_cancelar`
    de `bot/adaptador_falso.py::programa_abrir()` es exactamente ese caso:
    solo tiene sentido para el doble EN PROCESO, nunca cruzando esta
    frontera de proceso, ver `cliente_control.py::programa_abrir`).

    Revisión adversarial 20-08-2026 (lente fidelidad_puerto): antes de
    esto, un argumento no serializable dejaba escapar un `TypeError`
    crudo de `json`, sin relación con esta jerarquía -- reproducido en
    vivo. Ahora se degrada a una excepción con tipo conocido, capturable,
    igual que cualquier otro fallo de este módulo."""
