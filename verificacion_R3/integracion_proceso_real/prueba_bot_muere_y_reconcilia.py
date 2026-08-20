# -*- coding: utf-8 -*-
"""Fase 5 (R3) · Escenario (b) del plan de pruebas: matar el proceso del
BOT (aquí, `arnes_bot_minimo.py`) con SIGKILL mientras hay una posición
real abierta en el simulador, confirmar que el servidor (el "NT8" de
mentira) sigue vivo y con la MISMA posición -- imposible de demostrar con
`AdaptadorFalso` en proceso, porque matar el proceso de test mataría
también su propio estado -- y reiniciar el bot para probar la
reconciliación de `07_ADAPTADOR_NT8.md` §6 de verdad, en las DOS
direcciones: el caso feliz ("todo cuadra") Y el caso de descuadre
("una sola pata"), viendo el segundo fallar de forma segura antes de
aceptar que el primero basta."""
import json
import os
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, ING)

from bot import config
from simulador_nt8.cliente import AdaptadorSimuladorNT8

# el MISMO instrumento que usa bot/protocolo_dos_patas.py::abre_las_dos_patas
# de verdad (cfg.hedge_broker.instrumento) -- NUNCA un literal "MES" propio,
# ver la nota de R3 en arnes_bot_minimo.py::reconcilia().
INSTRUMENTO_HEDGE = config.obtener().hedge_broker.instrumento

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def arranca_servidor():
    dir_sockets = f"/tmp/nt8sim_reconc_{os.getpid()}"
    fichero_info = f"/tmp/nt8sim_reconc_info_{os.getpid()}.json"
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


def arranca_bot(ruta_datos, fichero_estado, fichero_latido,
                 cuenta_hedge="CTA-HEDGE", cuenta_prop="CTA-PROP"):
    return subprocess.Popen(
        [sys.executable, os.path.join(AQUI, "arnes_bot_minimo.py"),
         "--socket-datos", ruta_datos, "--fichero-estado", fichero_estado,
         "--fichero-latido", fichero_latido, "--cuenta-hedge", cuenta_hedge,
         "--cuenta-prop", cuenta_prop, "--instrumento-prop", "instrumento-prop-demo",
         "--direccion", "1", "--m", "4", "--k", "10"],
        cwd=ING, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def espera_fichero(ruta, timeout=5.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if os.path.exists(ruta):
            try:
                return json.load(open(ruta))
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.02)
    return None


def espera_fase_latido(ruta, fase_esperada, timeout=5.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if os.path.exists(ruta):
            try:
                d = json.load(open(ruta))
                if d.get("fase") == fase_esperada:
                    return d
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.02)
    return None


def mata_si_vivo(proc, señal=signal.SIGTERM, espera=3):
    if proc.poll() is None:
        proc.send_signal(señal)
        try:
            proc.wait(timeout=espera)
        except subprocess.TimeoutExpired:
            proc.kill()


srv, dir_sockets, fichero_info = arranca_servidor()
ruta_datos = os.path.join(dir_sockets, "nt8.sock")
fichero_estado = f"/tmp/nt8sim_reconc_estado_{os.getpid()}.json"
fichero_latido = f"/tmp/nt8sim_reconc_latido_{os.getpid()}.json"
for f in (fichero_estado, fichero_latido):
    try: os.remove(f)
    except FileNotFoundError: pass

bot1 = bot2 = bot3 = bot4 = None   # revisión adversarial 20-08-2026 (lente calidad_pruebas_r3):
                                     # declarados ANTES del try -- si algo falla a mitad (una
                                     # aserción, una excepción), el finally de abajo necesita
                                     # poder referenciarlos para matarlos. Sin esto, un fallo a
                                     # mitad de la prueba dejaba el proceso del bot huérfano,
                                     # reparentado a init, vivo -- reproducido en vivo forzando
                                     # un fallo justo antes del kill de la Fase 5b.
try:
    print("=== Fase 5a: arranca el bot, abre las dos patas, escribe estado+latido ===")
    bot1 = arranca_bot(ruta_datos, fichero_estado, fichero_latido)
    estado1 = espera_fichero(fichero_estado)
    ok("el bot abrió las dos patas y persistió estado.json", estado1 is not None and estado1.get("abierto") is True, estado1)
    lat1 = espera_fase_latido(fichero_latido, "abierto")
    ok("el bot escribió latido.json con fase='abierto'", lat1 is not None, lat1)
    pid_bot1 = bot1.pid

    print("\n=== Fase 5b: kill -9 al bot, CON POSICION ABIERTA -- el servidor sigue vivo ===")
    verificador = AdaptadorSimuladorNT8(ruta_datos)
    assert verificador.arrancar() is True
    pos_hedge_antes, _ = verificador.leer_posicion("CTA-HEDGE", INSTRUMENTO_HEDGE)
    pos_prop_antes, _ = verificador.leer_posicion("CTA-PROP", "instrumento-prop-demo")
    ok("posicion real ANTES de matar el bot: hedge y prop ambas viven",
       pos_hedge_antes != 0 and pos_prop_antes != 0, (pos_hedge_antes, pos_prop_antes))

    os.kill(pid_bot1, signal.SIGKILL)
    bot1.wait(timeout=3)
    ok("el proceso del bot murió de verdad con SIGKILL", bot1.returncode is not None and bot1.returncode < 0,
       bot1.returncode)

    assert srv.poll() is None, "el servidor NO deberia haber muerto -- es un proceso aparte"
    pos_hedge_despues, _ = verificador.leer_posicion("CTA-HEDGE", INSTRUMENTO_HEDGE)
    pos_prop_despues, _ = verificador.leer_posicion("CTA-PROP", "instrumento-prop-demo")
    ok("el SERVIDOR sigue vivo y con la MISMA posicion tras matar el bot -- "
       "imposible de demostrar con AdaptadorFalso en proceso",
       (pos_hedge_despues, pos_prop_despues) == (pos_hedge_antes, pos_prop_antes),
       (pos_hedge_despues, pos_prop_despues))
    verificador.parar()

    print("\n=== Fase 5c: reiniciar el bot -- reconciliacion CASO FELIZ (07_ADAPTADOR_NT8.md §6, fila 5) ===")
    bot2 = arranca_bot(ruta_datos, fichero_estado, fichero_latido)
    lat2 = espera_fase_latido(fichero_latido, "reconciliado")
    ok("tras reiniciar con todo cuadrando, el bot llega a fase='reconciliado' "
       "(NO re-abre, NO re-ejecuta la entrada de b0 -- R-3.7)", lat2 is not None, lat2)
    mata_si_vivo(bot2)
    salida2 = (bot2.stdout.read() if bot2.stdout else "") or ""
    ok("el log del bot dice literalmente 'RECONCILIADO' y cita la fila de §6",
       "RECONCILIADO" in salida2 and "fila 5" in salida2,
       [l for l in salida2.splitlines() if "RECONCILIA" in l or "fila 5" in l])

    print("\n=== Fase 5d: descuadre real (una sola pata) -- debe verse FALLAR de forma segura ===")
    # se aplana a mano SOLO el hedge, dejando la prop todavia viva -- un
    # descuadre real, fabricado desde fuera, mientras estado.json (que el
    # siguiente arranque del bot va a leer) SIGUE diciendo "las dos abiertas"
    romper = AdaptadorSimuladorNT8(ruta_datos)
    assert romper.arrancar() is True
    oid_rotura = romper.aplanar("CTA-HEDGE", INSTRUMENTO_HEDGE)
    romper.leer_estado_orden(oid_rotura)  # dispara el avance/fill -- ver nota de R3 en
                                            # prueba_servidor_arranque_basico.py: leer_posicion()
                                            # NO avanza el estado de la orden por si sola
    pos_hedge_roto, _ = romper.leer_posicion("CTA-HEDGE", INSTRUMENTO_HEDGE)
    ok("fabricado el descuadre: hedge aplanado a mano, prop sigue viva",
       pos_hedge_roto == 0, pos_hedge_roto)
    romper.parar()

    bot3 = arranca_bot(ruta_datos, fichero_estado, fichero_latido)
    lat3 = espera_fase_latido(fichero_latido, "bloqueado_por_descuadre")
    ok("con el descuadre fabricado, el bot llega a fase='bloqueado_por_descuadre' "
       "-- NO opera, NO intenta arreglar nada por su cuenta", lat3 is not None, lat3)
    mata_si_vivo(bot3)
    salida3 = (bot3.stdout.read() if bot3.stdout else "") or ""
    ok("el log del bot dice literalmente 'DESCUADRE FATAL' y cita §6 fila 1",
       "DESCUADRE FATAL" in salida3 and "fila 1" in salida3,
       [l for l in salida3.splitlines() if "DESCUADRE" in l])

    print("\n=== Fase 5e: posicion RESIDUAL (07_ADAPTADOR_NT8.md §6, fila 2) -- "
          "estado.json dice abierto=False, pero hay posicion viva y coincidente con m/k ===")
    # Revisión adversarial 20-08-2026 (lente calidad_pruebas_r3): reconcilia()
    # ignoraba estado_previo["abierto"] -- este escenario, con cuentas nuevas
    # para que ninguna posicion residual de las fases anteriores interfiera,
    # demuestra la correccion: abrir de verdad (abierto=True real), matar el
    # bot, y luego CORROMPER a mano el propio fichero de estado a
    # abierto=False -- exactamente "un cierre anterior no se completo o no
    # se registro" (07_ADAPTADOR_NT8.md §6, fila 2) -- para ver que el bot
    # NO lo confunde con "todo cuadra" (fila 5).
    fichero_estado_5e = f"/tmp/nt8sim_reconc_estado5e_{os.getpid()}.json"
    fichero_latido_5e = f"/tmp/nt8sim_reconc_latido5e_{os.getpid()}.json"
    for f in (fichero_estado_5e, fichero_latido_5e):
        try: os.remove(f)
        except FileNotFoundError: pass
    bot4 = arranca_bot(ruta_datos, fichero_estado_5e, fichero_latido_5e,
                        cuenta_hedge="CTA-HEDGE-5E", cuenta_prop="CTA-PROP-5E")
    estado4 = espera_fichero(fichero_estado_5e)
    ok("Fase 5e: el bot abrio de verdad (abierto=True) antes de corromper el estado",
       estado4 is not None and estado4.get("abierto") is True, estado4)
    mata_si_vivo(bot4, señal=signal.SIGKILL)

    estado4["abierto"] = False   # CORRUPCION deliberada: la posicion real sigue viva en el
                                   # simulador, pero el fichero persistido ahora dice que no
    with open(fichero_estado_5e, "w") as fh:
        json.dump(estado4, fh)

    bot4 = arranca_bot(ruta_datos, fichero_estado_5e, fichero_latido_5e,
                        cuenta_hedge="CTA-HEDGE-5E", cuenta_prop="CTA-PROP-5E")
    lat4 = espera_fase_latido(fichero_latido_5e, "bloqueado_por_descuadre")
    ok("Fase 5e: con abierto=False corrompido pero posicion real viva, el bot llega a "
       "fase='bloqueado_por_descuadre' -- NO lo confunde con reconciliacion feliz",
       lat4 is not None, lat4)
    mata_si_vivo(bot4)
    salida4 = (bot4.stdout.read() if bot4.stdout else "") or ""
    ok("Fase 5e: el log dice literalmente 'POSICION RESIDUAL' y cita §6 fila 2 (NO 'RECONCILIADO')",
       "POSICION RESIDUAL" in salida4 and "fila 2" in salida4 and "RECONCILIADO" not in salida4,
       [l for l in salida4.splitlines() if "POSICION" in l or "RECONCILIA" in l])

finally:
    for p in (bot1, bot2, bot3, bot4):
        if p is not None:
            mata_si_vivo(p)
    mata_si_vivo(srv)
    for f in (fichero_info, fichero_estado, fichero_latido,
              f"/tmp/nt8sim_reconc_estado5e_{os.getpid()}.json",
              f"/tmp/nt8sim_reconc_latido5e_{os.getpid()}.json"):
        try: os.remove(f)
        except FileNotFoundError: pass

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
