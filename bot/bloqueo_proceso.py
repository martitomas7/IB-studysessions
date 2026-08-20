# -*- coding: utf-8 -*-
"""bloqueo_proceso.py · D8/D9 · 10_SEGURIDAD.md §4.G, hueco #4 de §7

**"Dos instancias del bot a la vez" -- el fallo más tonto y más caro
posible.** Dos procesos leyendo el mismo `estado.json`, cada uno creyendo
que decide solo, pueden abrir la misma sesión dos veces, o cerrar una
posición que el otro cree viva -- exactamente el tipo de corrupción
silenciosa que 10_SEGURIDAD.md §3 (DESCONOCIDO → aplanar y parar) existe
para evitar, salvo que aquí ni siquiera hace falta llegar a DESCONOCIDO:
se puede prevenir estructuralmente, y es barato.

Mismo patrón que `bot/comandos.py` (marcador `<id>.tomado`): apertura
EXCLUSIVA con `O_CREAT|O_EXCL`, atómica a nivel de sistema de ficheros --
si dos procesos la intentan a la vez, el sistema operativo garantiza que
solo uno gana, sin ninguna carrera posible entre "comprobar si existe" y
"crear" (que sí tendría una ventana de carrera real).

**10_SEGURIDAD.md §3, la regla que gobierna esto:** si el fichero de
bloqueo existe pero el PID que contiene ya no está vivo, es un bloqueo
HUÉRFANO de una caída anterior (el proceso murió sin poder limpiar tras
de sí -- mismo caso que `simulador_nt8/servidor.py::_limpia_si_huerfano`
ya resuelve para sus sockets) -- CONOCIDO-SEGURO, se limpia y se sigue. Si
el PID sigue vivo, es una segunda instancia de verdad -- CONOCIDO-INSEGURO
en su forma más simple: no arrancar (N4, ni se opera ni se toca nada del
proceso que ya está corriendo)."""
import os


class ErrorInstanciaDuplicada(RuntimeError):
    """Ya hay un proceso vivo con este fichero de bloqueo. No se arranca --
    10_SEGURIDAD.md §3/§4.G: dos instancias a la vez es el fallo más caro y
    más tonto posible, y es enteramente evitable."""


def _pid_vivo(pid):
    """`os.kill(pid, 0)` no manda ninguna señal -- solo comprueba si el
    proceso existe y si tenemos permiso para señalizarlo. `ProcessLookupError`
    = no existe (muerto, PID reciclado o nunca existió). `PermissionError`
    = existe pero de otro usuario -- se trata como VIVO (no se puede
    confirmar que esté muerto, y 10_SEGURIDAD.md dice "ante la duda no se
    aplana/actúa", aquí "ante la duda, no se arranca")."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True  # cualquier otro fallo al preguntar: por seguridad, se asume vivo
    return True


def _lee_pid(ruta):
    try:
        with open(ruta) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None  # fichero ilegible o con contenido corrupto -- no se puede confirmar
                      # que esté muerto; el llamador lo tratará como "sigue bloqueado"


class BloqueoProceso:
    """Uso:
        with bloqueo_proceso.adquiere(ruta_lock):
            ... el bot corre ...
        # el fichero se borra solo al salir del bloque, incluso si hay excepción

    Lanza `ErrorInstanciaDuplicada` en el `with` si ya hay una instancia viva
    -- eso, y solo eso, es lo que hace que el bot "no arranque" (10_SEGURIDAD.md
    §4.G): el propio `with` nunca llega a entrar."""

    def __init__(self, ruta):
        self.ruta = ruta
        self._adquirido = False

    def __enter__(self):
        self._intenta_adquirir()
        return self

    def __exit__(self, tipo_exc, exc, tb):
        if self._adquirido:
            try:
                os.remove(self.ruta)
            except FileNotFoundError:
                pass
        return False  # nunca suprime la excepción que estuviera en curso

    def _intenta_adquirir(self, ya_limpio_una_vez=False):
        try:
            fd = os.open(self.ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            pid_existente = _lee_pid(self.ruta)
            if pid_existente is not None and not _pid_vivo(pid_existente):
                if ya_limpio_una_vez:
                    # ya se limpió una vez en esta misma llamada y VOLVIÓ a
                    # existir -- otro proceso ganó la carrera de limpieza
                    # justo en medio; no se insiste más, se trata como
                    # ocupado de verdad (conservador, nunca en bucle).
                    raise ErrorInstanciaDuplicada(
                        f"bloqueo {self.ruta!r} en disputa con otro proceso durante el arranque "
                        "-- no se arranca, se reintenta más tarde")
                try:
                    os.remove(self.ruta)
                except FileNotFoundError:
                    pass  # otro proceso ya lo limpió -- bien, seguimos igual
                return self._intenta_adquirir(ya_limpio_una_vez=True)
            raise ErrorInstanciaDuplicada(
                f"ya hay una instancia viva usando {self.ruta!r}"
                + (f" (pid {pid_existente})" if pid_existente is not None else " (pid ilegible)")
                + " -- 10_SEGURIDAD.md §4.G: no se arranca una segunda instancia")
        else:
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            self._adquirido = True


def adquiere(ruta):
    """Punto de entrada normal -- ver `BloqueoProceso`."""
    return BloqueoProceso(ruta)
