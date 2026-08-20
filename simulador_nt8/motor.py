# -*- coding: utf-8 -*-
"""motor.py · simulador_nt8

`MotorSimulado` ENVUELVE `bot/adaptador_falso.py::AdaptadorFalso` -- no
reimplementa su máquina de estados (§4 de `07_ADAPTADOR_NT8.md`: ENVIADA →
ACEPTADA → {LLENA, PARCIAL→LLENA, CANCELADA} / ENVIADA → RECHAZADA). Eso
evita la deriva entre el doble EN PROCESO (`AdaptadorFalso`, usado por
`verificacion_R3/prueba_protocolo_dos_patas.py` con reloj lógico falso) y
este doble FUERA DE PROCESO: los dos comparten exactamente la misma lógica
de negocio de simulación, solo cambia si se llama en memoria o por red.

Diferencia deliberada: aquí el reloj es REAL (`time.monotonic`), no el
reloj lógico inyectable de las pruebas unitarias -- es la pieza central
para poder probar timeouts de reloj de pared de verdad (escenario (c) del
plan de pruebas) y ganchos de retraso/congelación con tiempo real
(escenario (d1)).

Los ganchos `test_congelar()`/`test_retrasar_respuesta()` son NUEVOS aquí
-- no existen en `AdaptadorFalso` porque solo tienen sentido cruzando una
frontera de proceso real: `test_congelar()` bloquea el HILO DEL SERVIDOR
que atiende la petición, dejando el socket abierto pero mudo -- un "peer
conectado pero que no contesta", el escenario que expone si el cliente de
verdad tiene un timeout de socket configurado (si no lo tiene, esto cuelga
el cliente para siempre, que es justo la prueba)."""
import threading
import time

from bot.adaptador_falso import AdaptadorFalso


class MotorSimulado:
    """Delegado directo (`__getattr__`) a `AdaptadorFalso` para los diez
    métodos del puerto Y para sus fábricas de escenario (`programa_abrir`,
    `programa_aplanar`, `desconecta`, `fuerza_fill`) -- cero reimplementación,
    cero mapeo manual método a método, para que una fábrica nueva que gane
    `AdaptadorFalso` el día de mañana funcione aquí sin tocar este fichero."""

    # Únicas fábricas de escenario de AdaptadorFalso que el canal de control
    # puede alcanzar por reflexión -- lista CERRADA (revisión adversarial
    # 20-08-2026, lente seguridad_robustez: sin esta lista, __getattr__
    # exponía CUALQUIER atributo de AdaptadorFalso con el prefijo test_,
    # incluidos los dunder -- reproducido en vivo: 'test___init__' resetea
    # todo el estado simulado en caliente, sin aviso, ok:true; 'test___getstate__'
    # extrae el __dict__ interno completo. Ver 07_ADAPTADOR_NT8.md §12,
    # revisión 5 (o su continuación) para el detalle).
    _FABRICAS_PERMITIDAS = frozenset({"programa_abrir", "programa_aplanar",
                                       "desconecta", "fuerza_fill",
                                       "fuerza_posicion_externa"})

    def __init__(self):
        self._falso = AdaptadorFalso(reloj=time.monotonic)
        self._congelado = threading.Event()
        self._congelado.set()          # set() = NO bloquea (Event "libre" por defecto)
        self._retraso_pendiente = None  # (metodo, segundos, armado_en) | None
        self._lock_retraso = threading.Lock()
        # Revisión adversarial 20-08-2026, lente concurrencia_y_estado:
        # AdaptadorFalso no es thread-safe (posiciones/ordenes/contador se
        # leen-modifican-escriben sin protección) y el canal de datos (el
        # bot) y el canal de control (un arnés de pruebas) pueden llamar
        # simultáneamente desde hilos distintos -- reproducido de forma
        # determinista (interleaving forzado) como "lost update" real sobre
        # self.posiciones. Todo acceso al estado de AdaptadorFalso pasa por
        # este lock, tanto desde invocar() (canal de datos) como desde
        # invocar_control() (canal de control) -- NUNCA se accede a
        # self._falso fuera de estos dos puntos de entrada.
        self._lock_estado = threading.RLock()

    # --- ganchos de prueba, exclusivos del canal de control -------------
    def test_congelar(self):
        """El HILO DEL SERVIDOR que procese la siguiente `invocar()` se
        queda bloqueado aquí sin límite -- simula 'NT8 sigue vivo, la
        conexión sigue abierta, pero no responde nada'. Se libera con
        `test_liberar_congelacion()` o matando el proceso servidor."""
        self._congelado.clear()
        return True

    def test_liberar_congelacion(self):
        self._congelado.set()
        return True

    def test_retrasar_respuesta(self, metodo, segundos):
        """La PRÓXIMA llamada a `metodo` espera `segundos` (reloj real)
        antes de delegar en AdaptadorFalso -- para fabricar a propósito un
        timeout de N/N_hedge con reloj de pared real, o una ventana
        determinista en la que matar el proceso servidor a mitad de la
        orden (escenario (a)).

        Revisión adversarial 20-08-2026 (lente anti_confusion_r1, hallazgo
        propio): se guarda también el instante en que se ARMA el retraso.
        Sin eso, un hilo que ya estaba EN VUELO (bloqueado en
        `self._congelado.wait()` de una llamada anterior al mismo
        `metodo`, p.ej. tras `test_congelar()`) podía "robarse" el retraso
        armado para una petición NUEVA en cuanto se despertaba -- carrera
        real, reproducida de forma intermitente (~25% de las corridas) en
        `verificacion_R3/integracion_proceso_real/prueba_ganchos_control.py`.
        La condición de `invocar()` de abajo exige que la invocación haya
        ENTRADO en o después de este instante para poder consumirlo."""
        with self._lock_retraso:
            self._retraso_pendiente = (metodo, float(segundos), time.monotonic())
        return True

    def test_activa_rechazo_cantidad_cero(self, activo):
        """`AdaptadorFalso.rechaza_aplanar_cantidad_cero` es un atributo de
        instancia, no un método -- este wrapper es la única forma de
        tocarlo desde el canal de control sin reimplementar el flag."""
        self._falso.rechaza_aplanar_cantidad_cero = bool(activo)
        return True

    # --- despacho de las operaciones reales del puerto -------------------
    def invocar(self, metodo, args):
        """Punto único de entrada que `servidor.py` llama para CUALQUIER
        método del puerto (canal de datos). Aplica congelación y retraso
        ANTES de delegar -- así ambos ganchos funcionan para los diez
        métodos sin que cada uno tenga que saber de ellos."""
        t_entrada = time.monotonic()   # ANTES de esperar la congelacion -- ver
                                         # nota de test_retrasar_respuesta() sobre
                                         # la carrera con hilos ya en vuelo
        self._congelado.wait()   # bloquea aquí si test_congelar() está activo
        with self._lock_retraso:
            pendiente = self._retraso_pendiente
            if (pendiente is not None and pendiente[0] == metodo
                    and t_entrada >= pendiente[2]):
                self._retraso_pendiente = None
            else:
                pendiente = None
        if pendiente is not None:
            time.sleep(pendiente[1])
        with self._lock_estado:
            return getattr(self._falso, metodo)(**args)

    def invocar_control(self, metodo, args):
        """Punto único de entrada que `servidor.py` llama para el canal de
        CONTROL (métodos `test_*`) -- espejo de `invocar()` para el canal
        de datos, mismo `self._lock_estado` para que las dos vías nunca
        toquen `AdaptadorFalso` a la vez (ver docstring de `__init__`).

        `test_congelar`/`test_liberar_congelacion` quedan EXPLÍCITAMENTE
        fuera del lock: si `invocar()` se queda bloqueado en
        `self._congelado.wait()` DENTRO de `self._lock_estado`, el propio
        hilo de control que necesita llamar a `test_liberar_congelacion()`
        para desbloquearlo se quedaría esperando ese mismo lock --
        deadlock. Esos dos métodos solo tocan el `Event`, nunca
        `AdaptadorFalso`, así que no necesitan la protección de todos
        modos."""
        if metodo in ("test_congelar", "test_liberar_congelacion"):
            return getattr(self, metodo)(**args)
        with self._lock_estado:
            return getattr(self, metodo)(**args)

    def __getattr__(self, nombre):
        # fábricas de AdaptadorFalso (programa_abrir, programa_aplanar,
        # desconecta, fuerza_fill) delegadas -- ver docstring de la clase.
        # __getattr__ solo se llama cuando el atributo NO se encontró por
        # la vía normal (los métodos test_* definidos arriba en esta
        # propia clase siguen resolviéndose primero, sin pasar por aquí).
        #
        # El canal de control (servidor.py) exige el prefijo 'test_' en
        # TODO lo que llama, para poder distinguirlo de los métodos del
        # puerto con una única regla ("empieza por test_") -- pero
        # AdaptadorFalso.desconecta()/fuerza_fill()/programa_abrir()/
        # programa_aplanar() no llevan ese prefijo en su propio nombre.
        # Se quita aquí antes de delegar -- es la ÚNICA capa que conoce
        # esa traducción de nombres; ni el servidor ni AdaptadorFalso
        # tienen que saber nada de esto.
        #
        # SOLO las fábricas de _FABRICAS_PERMITIDAS son alcanzables --
        # cualquier otro nombre (incluidos los dunder de AdaptadorFalso)
        # se rechaza con AttributeError, que servidor.py ya convierte en
        # un ok:false limpio. Ver nota de seguridad en _FABRICAS_PERMITIDAS.
        if nombre.startswith("test_"):
            objetivo = nombre[len("test_"):]
            if objetivo not in self._FABRICAS_PERMITIDAS:
                raise AttributeError(
                    f"'{nombre}' no es una fabrica de escenario permitida en el canal de control "
                    f"(permitidas: {sorted(self._FABRICAS_PERMITIDAS)})")
            return getattr(self._falso, objetivo)
        raise AttributeError(nombre)
