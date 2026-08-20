# -*- coding: utf-8 -*-
"""R3 (10_SEGURIDAD.md §4.G, hueco #7 #4): dos instancias del bot a la vez
es "el fallo más tonto y más caro posible" -- `bot/bloqueo_proceso.py` lo
previene con un fichero de bloqueo por PID. Probado con PROCESOS REALES
(subprocess), no con dos objetos en el mismo hilo -- la garantía que
importa es justo la que solo se ve cruzando una frontera de proceso real."""
import os
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import bloqueo_proceso as B

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


RUTA_LOCK = "/tmp/prueba_bloqueo_proceso.lock"

try:
    os.remove(RUTA_LOCK)
except FileNotFoundError:
    pass

print("=== 1. una instancia sola adquiere y libera limpio ===")
with B.adquiere(RUTA_LOCK):
    ok("mientras está adquirido, el fichero existe con el PID propio",
       os.path.exists(RUTA_LOCK) and open(RUTA_LOCK).read().strip() == str(os.getpid()),
       open(RUTA_LOCK).read() if os.path.exists(RUTA_LOCK) else "no existe")
ok("al salir del `with`, el fichero se borra solo", not os.path.exists(RUTA_LOCK), RUTA_LOCK)

print("\n=== 2. DOS PROCESOS REALES -- el segundo NO arranca ===")
_ruta_script_hijo = "/tmp/_mantiene_bloqueo_proceso_hijo.py"
with open(_ruta_script_hijo, "w") as fh:
    fh.write(
        "import sys, time\n"
        f"sys.path.insert(0, {ING!r})\n"
        "from bot import bloqueo_proceso as B\n"
        f"with B.adquiere({RUTA_LOCK!r}):\n"
        "    time.sleep(5)\n"
    )
proc1 = subprocess.Popen([sys.executable, _ruta_script_hijo], cwd=ING)
t0 = time.time()
while time.time() - t0 < 3.0 and not os.path.exists(RUTA_LOCK):
    time.sleep(0.02)
ok("el primer proceso adquirió el bloqueo de verdad (fichero visible desde fuera)",
   os.path.exists(RUTA_LOCK), RUTA_LOCK)

try:
    with B.adquiere(RUTA_LOCK):
        segunda_arranco = True
except B.ErrorInstanciaDuplicada as ex:
    segunda_arranco = False
    detalle_dup = str(ex)
ok("la SEGUNDA instancia (mismo proceso de prueba, mientras el primero sigue vivo) "
   "NO arranca -- ErrorInstanciaDuplicada", not segunda_arranco, detalle_dup)

proc1.send_signal(signal.SIGKILL)
proc1.wait(timeout=3)

print("\n=== 3. bloqueo HUÉRFANO (proceso que lo tenía murió con SIGKILL, sin limpiar) ===")
ok("tras matar el primer proceso con SIGKILL, el fichero de bloqueo QUEDA (huérfano, "
   "no se limpió solo -- justo el caso que hay que detectar)",
   os.path.exists(RUTA_LOCK), RUTA_LOCK)
pid_huerfano = int(open(RUTA_LOCK).read().strip())
ok("el PID que quedó en el fichero YA NO está vivo",
   not B._pid_vivo(pid_huerfano), pid_huerfano)

with B.adquiere(RUTA_LOCK) as bloqueo:
    ok("una instancia NUEVA SÍ arranca contra un bloqueo huérfano -- lo limpia y sigue "
       "(CONOCIDO-SEGURO, 10_SEGURIDAD.md §3, no un fallo)",
       open(RUTA_LOCK).read().strip() == str(os.getpid()), open(RUTA_LOCK).read())
ok("y libera limpio al salir", not os.path.exists(RUTA_LOCK), RUTA_LOCK)

try:
    os.remove(_ruta_script_hijo)
except FileNotFoundError:
    pass

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
