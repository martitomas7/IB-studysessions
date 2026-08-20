# -*- coding: utf-8 -*-
"""Fase 7 (R3) · Escenario (d) del plan de pruebas -- vigía detectando un
`latido.json` rancio, en dos partes que aíslan capas distintas:

  (d1) el CLIENTE mismo no se cuelga -- ya demostrado de verdad en
       verificacion_R3/integracion_proceso_real/prueba_ganchos_control.py
       (Fase 3): `test_congelar()` + `TimeoutOrden` acotado, con la
       reconstrucción explícita de la versión SIN `settimeout()` viéndose
       colgar de verdad antes de aceptar la versión real. No se repite
       aquí -- referenciado, no reimplementado.

  (d2) el VIGÍA atrapa un bot REALMENTE colgado, por una causa EXTERNA
       (no cooperativa): `os.kill(pid, SIGSTOP)` sobre `arnes_bot_minimo.py`
       ya en marcha -- el proceso sigue existiendo (visible en `ps`) pero
       el kernel no le da CPU nunca más hasta un SIGCONT; ni el bot ni el
       simulador cooperan con esto, es exactamente lo que un cuelgue real
       (deadlock, bucle infinito con el GIL retenido, hijo zombi que nunca
       libera al padre) parece desde fuera. `latido.json` deja de
       refrescarse SOLO porque el proceso ya no ejecuta nada -- no hay
       ningún gancho de prueba de por medio, a diferencia de (d1).

R3: primero se confirma que el vigía NO dispara en falso mientras el bot
sigue vivo y refrescando (evita el "grita lobo" que 09_DESPLIEGUE.md §1.2
señala como peor que no avisar). Solo después se aplica SIGSTOP y se
confirma que el vigía SÍ dispara, dentro de su umbral, ni antes ni
después."""
import json
import os
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, ING)
sys.path.insert(0, AQUI)   # logica_watchdog.py vive en este mismo directorio, no bajo ING

from logica_watchdog import revisa_latido

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def arranca_servidor():
    dir_sockets = f"/tmp/nt8sim_vigia_{os.getpid()}"
    fichero_info = f"/tmp/nt8sim_vigia_info_{os.getpid()}.json"
    proc = subprocess.Popen(
        [sys.executable, "-m", "simulador_nt8", "--entorno=pruebas",
         "--dir-sockets", dir_sockets, "--fichero-info", fichero_info],
        cwd=ING, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5.0 and not os.path.exists(fichero_info):
        time.sleep(0.02)
    if not os.path.exists(fichero_info):
        raise RuntimeError("el servidor no arrancó dentro de 5s")
    return proc, dir_sockets, fichero_info


def mata_si_vivo(proc, señal=signal.SIGTERM, espera=3):
    if proc.poll() is None:
        proc.send_signal(señal)
        try:
            proc.wait(timeout=espera)
        except subprocess.TimeoutExpired:
            proc.kill()


UMBRAL_PRUEBA_S = 1.0   # SOLO para esta prueba -- no es el umbral de produccion
                          # de 09_DESPLIEGUE.md (provisional 90s = 3x el intervalo
                          # de 30s); aqui hace falta que la prueba termine en
                          # segundos, no en minutos, y lo que se prueba es la
                          # LOGICA de comparacion edad>umbral, no el numero en si.

print("=== (d1) referencia -- ya demostrado en prueba_ganchos_control.py (Fase 3), no repetido ===")
ok("(d1) cliente-no-se-cuelga: ver verificacion_R3/integracion_proceso_real/prueba_ganchos_control.py",
   True, "referencia, no ejecutado aqui")

print("\n=== (d2) vigia real contra un bot REALMENTE detenido con SIGSTOP (no cooperativo) ===")
srv, dir_sockets, fichero_info = arranca_servidor()
ruta_datos = os.path.join(dir_sockets, "nt8.sock")
fichero_estado = f"/tmp/nt8sim_vigia_estado_{os.getpid()}.json"
fichero_latido = f"/tmp/nt8sim_vigia_latido_{os.getpid()}.json"
for f in (fichero_estado, fichero_latido):
    try: os.remove(f)
    except FileNotFoundError: pass

bot = None
try:
    bot = subprocess.Popen(
        [sys.executable, os.path.join(AQUI, "arnes_bot_minimo.py"),
         "--socket-datos", ruta_datos, "--fichero-estado", fichero_estado,
         "--fichero-latido", fichero_latido, "--intervalo-latido", "0.15"],
        cwd=ING, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    t0 = time.monotonic()
    while time.monotonic() - t0 < 5.0 and not os.path.exists(fichero_latido):
        time.sleep(0.02)
    ok("el bot escribio latido.json por primera vez", os.path.exists(fichero_latido),
       fichero_latido)

    print("\n-- control: bot VIVO y refrescando -- el vigia NO debe disparar en falso --")
    time.sleep(0.5)
    rancio, edad, motivo = revisa_latido(fichero_latido, UMBRAL_PRUEBA_S)
    ok("con el bot vivo y refrescando cada 0.15s, el vigia NO lo marca rancio "
       f"(umbral de prueba={UMBRAL_PRUEBA_S}s)", rancio is False, motivo)

    print(f"\n-- SIGSTOP real al bot (pid={bot.pid}) -- sigue existiendo, deja de ejecutar TODO --")
    os.kill(bot.pid, signal.SIGSTOP)
    ts_congelado = json.load(open(fichero_latido))
    rancio_justo_tras_stop, edad0, motivo0 = revisa_latido(fichero_latido, UMBRAL_PRUEBA_S)
    ok("justo tras SIGSTOP (antes de agotar el umbral), el vigia AUN NO lo marca rancio "
       "-- no dispara antes de tiempo", rancio_justo_tras_stop is False, motivo0)

    time.sleep(UMBRAL_PRUEBA_S + 0.5)
    ts_tras_espera = json.load(open(fichero_latido))
    ok("mientras esta detenido (SIGSTOP), latido.json NO avanza -- el proceso no ejecuta nada, "
       "ni siquiera su propio bucle de latido",
       ts_tras_espera == ts_congelado, (ts_congelado, ts_tras_espera))

    rancio_final, edad_final, motivo_final = revisa_latido(fichero_latido, UMBRAL_PRUEBA_S)
    ok(f"pasado el umbral de {UMBRAL_PRUEBA_S}s, el vigia SI marca el latido como rancio "
       "-- proceso realmente detenido, sin ninguna cooperacion suya ni del simulador",
       rancio_final is True, motivo_final)

    print("\n-- verificacion adicional: el proceso SIGUE existiendo (visible, no zombi/muerto) --")
    existe = True
    try:
        os.kill(bot.pid, 0)  # señal 0: no mata, solo comprueba que el pid existe
    except ProcessLookupError:
        existe = False
    ok("el proceso detenido SIGUE en la tabla de procesos -- es 'colgado', no 'muerto': "
       "exactamente el caso que un simple 'sigue en la lista de ps' no distinguiría",
       existe, f"os.kill(pid, 0) -- existe={existe}")

    os.kill(bot.pid, signal.SIGCONT)  # liberar antes de matar limpio, buena higiene de proceso
    time.sleep(0.3)

finally:
    if bot is not None:
        mata_si_vivo(bot)
    mata_si_vivo(srv)
    for f in (fichero_info, fichero_estado, fichero_latido):
        try: os.remove(f)
        except FileNotFoundError: pass

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
