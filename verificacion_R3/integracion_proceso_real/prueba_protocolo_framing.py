# -*- coding: utf-8 -*-
"""Fase 0 (R3): simulador_nt8/protocolo.py, unitario puro, sin subprocesos ni
sockets reales -- un socket falso de pruebas que entrega los bytes de un
mensaje TROCEADOS a propósito en varias llamadas a `recv()`, exactamente lo
que un socket real puede hacer y un mock ingenuo (una sola llamada a
`recv()`) nunca demuestra.

R3: antes de aceptar `LectorLineas` como correcto, este mismo fichero se
corrió contra una reconstrucción literal de una implementación INGENUA
(parsea tras un único `recv()`, sin acumular buffer) -- ver la sección
"ANTES" más abajo, con salida real pegada en el docstring de cada prueba.
No se narra que fallaría: se hizo fallar de verdad."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, ING)

from simulador_nt8 import protocolo as P
from simulador_nt8.errores import ConexionPerdida, LineaDemasiadoLarga

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


class SocketFalsoTroceado:
    """Simula un socket real que entrega los bytes de un mensaje en varios
    `recv()` sucesivos -- el kernel puede fragmentar así de verdad; un
    LectorLineas correcto tiene que acumular hasta ver el `\\n`."""
    def __init__(self, trozos):
        self._trozos = list(trozos)

    def recv(self, n):
        if not self._trozos:
            return b""  # EOF
        return self._trozos.pop(0)


class SocketFalsoLineaSinFin:
    """Simula un peer que manda datos sin terminar NUNCA la línea con
    `\\n` -- debe disparar LineaDemasiadoLarga antes de agotar memoria,
    nunca colgarse ni MemoryError."""
    def __init__(self, tamano_trozo=4096):
        self._tamano = tamano_trozo

    def recv(self, n):
        return b"x" * self._tamano  # nunca manda \n -- infinito a propósito


class ImplementacionIngenuaLectorLineas:
    """ANTES (reconstrucción literal de una implementación "obvia" que
    parsea tras un único recv() -- exactamente el bug que Fase 0 de R3
    exige ver fallar antes de aceptar la implementación real de
    protocolo.py::LectorLineas)."""
    def __init__(self, sock):
        self._sock = sock

    def leer_mensaje(self):
        import json
        trozo = self._sock.recv(4096)
        if trozo == b"":
            raise ConexionPerdida("EOF")
        linea = trozo.split(b"\n", 1)[0]
        return json.loads(linea.decode("utf-8"))  # revienta si el mensaje llego troceado


print("=== Fase 0: framing JSONL — mensaje fragmentado en varios recv() ===")
mensaje = {"id": 1, "metodo": "abrir", "args": {"cuenta": "MFF-1", "instrumento": "MES",
                                                  "direccion": 1, "cantidad": 4}}
import json as _json
linea_completa = (_json.dumps(mensaje) + "\n").encode("utf-8")
# la trocea a propósito en 5 pedazos pequeños, ni siquiera respetando límites de caracter UTF-8
mitad = len(linea_completa) // 5 or 1
trozos = [linea_completa[i:i+mitad] for i in range(0, len(linea_completa), mitad)]
assert len(trozos) >= 3, "la trama de prueba debe partirse en varios recv() de verdad"

print("\n-- ANTES (implementación ingenua, un único recv()) --")
try:
    ing = ImplementacionIngenuaLectorLineas(SocketFalsoTroceado(list(trozos)))
    resultado_ingenuo = ing.leer_mensaje()
    fallo_como_se_esperaba = False
    detalle = f"NO FALLÓ (leyó {resultado_ingenuo!r} de un mensaje troceado -- inesperado)"
except Exception as ex:
    fallo_como_se_esperaba = True
    detalle = f"{type(ex).__name__}: {ex}"
print(f"  resultado: {detalle}")
ok("la implementación ingenua FALLA con un mensaje fragmentado (como se esperaba)",
   fallo_como_se_esperaba, detalle)

print("\n-- DESPUÉS (simulador_nt8.protocolo.LectorLineas real) --")
lector = P.LectorLineas(SocketFalsoTroceado(list(trozos)))
resultado_real = lector.leer_mensaje()
ok("LectorLineas real reconstruye el mensaje completo pese al fragmentado",
   resultado_real == mensaje, resultado_real)

print("\n=== Fase 0: dos mensajes coalescidos en un solo recv() ===")
m1 = {"id": 1, "metodo": "hay_conexion", "args": {"cuenta": "A"}}
m2 = {"id": 2, "metodo": "hay_conexion", "args": {"cuenta": "B"}}
coalescido = (_json.dumps(m1) + "\n" + _json.dumps(m2) + "\n").encode("utf-8")
lector2 = P.LectorLineas(SocketFalsoTroceado([coalescido]))
r1 = lector2.leer_mensaje()
r2 = lector2.leer_mensaje()
ok("dos mensajes en un solo recv() se separan correctamente (primero)", r1 == m1, r1)
ok("dos mensajes en un solo recv() se separan correctamente (segundo, del buffer)", r2 == m2, r2)

print("\n=== Fase 0: línea que nunca termina con \\n -- cota de 1 MiB ===")
lector3 = P.LectorLineas(SocketFalsoLineaSinFin())
try:
    lector3.leer_mensaje()
    disparo_limite = False
    detalle3 = "NO lanzó nada -- se habría colgado/agotado memoria en producción"
except LineaDemasiadoLarga as ex:
    disparo_limite = True
    detalle3 = f"LineaDemasiadoLarga: {ex}"
except Exception as ex:
    disparo_limite = False
    detalle3 = f"lanzó {type(ex).__name__} en vez de LineaDemasiadoLarga: {ex}"
print(f"  resultado: {detalle3}")
ok("una línea sin fin dispara LineaDemasiadoLarga antes de agotar memoria",
   disparo_limite, detalle3)

print("\n=== Fase 0: EOF a mitad de mensaje -> ConexionPerdida, no un JSON corrupto silencioso ===")
lector4 = P.LectorLineas(SocketFalsoTroceado([b'{"id": 1, "met']))  # se corta ahí, EOF
try:
    lector4.leer_mensaje()
    detecta_eof = False
    detalle4 = "NO lanzó nada"
except ConexionPerdida as ex:
    detecta_eof = True
    detalle4 = f"ConexionPerdida: {ex}"
except Exception as ex:
    detecta_eof = False
    detalle4 = f"lanzó {type(ex).__name__} en vez de ConexionPerdida: {ex}"
ok("EOF a mitad de mensaje da ConexionPerdida", detecta_eof, detalle4)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
