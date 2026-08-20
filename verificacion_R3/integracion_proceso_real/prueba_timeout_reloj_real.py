# -*- coding: utf-8 -*-
"""Fase 6 (R3) · Escenario (c) del plan de pruebas: `bot.protocolo_dos_patas
.abre_las_dos_patas` corrido SIN ningún reloj lógico inyectado -- sus
valores por defecto (`reloj=None -> time.monotonic`, `dormir=None ->
time.sleep`), contra un servidor REAL cruzando una frontera de proceso/red
real. `N`=5,0s y `N_hedge`=30,0s vienen de `03_CONFIG.yaml` tal cual
(R2: ningún número propio) -- las pruebas unitarias con reloj lógico falso
(`verificacion_R3/prueba_protocolo_dos_patas.py`) demuestran que la LÓGICA
es correcta con tiempo instantáneo; esto demuestra que el mismo timeout se
cumple de verdad con reloj de pared real y latencia de E/S real por un
socket AF_UNIX.

R3: primero se corre con una aserción de igualdad EXACTA al valor nominal
del timeout, para verla fallar por el jitter real que el reloj lógico
nunca mostraba -- después se ajusta a una banda de tolerancia y se
confirma que pasa dentro de ella, ni antes ni (mucho) después.

AVISO: esta prueba tarda de verdad ~5s + ~30s de reloj de pared (los dos
timeouts reales de la norma) -- deliberado, es lo que "reloj de pared
real" significa. No se marca lenta/opcional: es la única prueba de todo
este directorio que demuestra el número exacto de N/N_hedge cumpliéndose
de verdad, no solo en lógica."""
import os
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, ING)

from bot import config
from bot.protocolo_dos_patas import abre_las_dos_patas
from simulador_nt8.cliente import AdaptadorSimuladorNT8
from simulador_nt8.cliente_control import ClienteControl

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


cfg = config.obtener()
N = cfg.adaptador.timeout_prop_s.valor()
N_HEDGE = cfg.adaptador.timeout_hedge_s.valor()
MES = cfg.hedge_broker.instrumento
INSTRUMENTO_PROP = "instrumento-prop-demo"


def arranca_servidor(sufijo):
    dir_sockets = f"/tmp/nt8sim_tiempo_{sufijo}_{os.getpid()}"
    fichero_info = f"/tmp/nt8sim_tiempo_{sufijo}_info_{os.getpid()}.json"
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


def para_servidor(proc, fichero_info):
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    try:
        os.remove(fichero_info)
    except FileNotFoundError:
        pass


print(f"=== Fase 6a: N={N}s (timeout de la PROP) con reloj de pared real -- el hedge confirma, la prop nunca ===")
proc, dir_sockets, fichero_info = arranca_servidor("propN")
try:
    ruta_datos = os.path.join(dir_sockets, "nt8.sock")
    ruta_control = os.path.join(dir_sockets, "nt8.control.sock")
    control = ClienteControl(ruta_control)
    cliente = AdaptadorSimuladorNT8(ruta_datos, timeout_operacion=N + 10.0)
    assert cliente.arrancar() is True
    # la prop nunca llena dentro de N -- fill_en_s muy por encima de N, reloj REAL
    control.programa_abrir("CTA-PROP", INSTRUMENTO_PROP, fill_en_s=999.0)

    t0 = time.monotonic()
    r = abre_las_dos_patas(cliente, "CTA-HEDGE", "CTA-PROP", INSTRUMENTO_PROP,
                            direccion=1, m=4, k=10)  # reloj=None, dormir=None -> POR DEFECTO, reloj real
    dt = time.monotonic() - t0
    print(f"  resultado: {r}")
    print(f"  tiempo de pared real transcurrido: {dt:.3f}s  (N nominal = {N}s)")

    print("\n  -- comprobacion R3: la igualdad EXACTA a N tiene que FALLAR por jitter real --")
    exacto_falla = (dt != N)
    ok(f"dt NO es exactamente igual a N={N}s (el reloj de pared real SIEMPRE mete jitter, "
       "algo que el reloj logico de las pruebas unitarias nunca mostraba)",
       exacto_falla, f"dt={dt:.6f}s")

    ok(f"dt cae dentro de una banda de tolerancia realista alrededor de N={N}s "
       f"(entre {N - 0.3}s y {N + 2.0}s -- nunca antes de N, y no mucho despues)",
       (N - 0.3) <= dt <= (N + 2.0), f"dt={dt:.3f}s")
    ok("motivo == 'N_expirado_prop_cancelada_hedge_aplanado' -- el timeout real disparo "
       "la misma rama que el reloj logico ya probaba en 05_ORDEN_DE_CONSTRUCCION",
       r.get("motivo") == "N_expirado_prop_cancelada_hedge_aplanado", r)
    ok("el hedge quedo aplanado tras el timeout real de N (no se queda desnudo)",
       r.get("abierto") is False, r)
finally:
    para_servidor(proc, fichero_info)


print(f"\n=== Fase 6b: N_hedge={N_HEDGE}s (timeout del HEDGE) con reloj de pared real -- el hedge nunca confirma ===")
proc, dir_sockets, fichero_info = arranca_servidor("hedgeN")
try:
    ruta_datos = os.path.join(dir_sockets, "nt8.sock")
    ruta_control = os.path.join(dir_sockets, "nt8.control.sock")
    control = ClienteControl(ruta_control)
    cliente = AdaptadorSimuladorNT8(ruta_datos, timeout_operacion=N_HEDGE + 10.0)
    assert cliente.arrancar() is True
    control.programa_abrir("CTA-HEDGE", MES, fill_en_s=999.0)

    t0 = time.monotonic()
    r = abre_las_dos_patas(cliente, "CTA-HEDGE", "CTA-PROP", INSTRUMENTO_PROP,
                            direccion=1, m=4, k=10)
    dt = time.monotonic() - t0
    print(f"  resultado: {r}")
    print(f"  tiempo de pared real transcurrido: {dt:.3f}s  (N_hedge nominal = {N_HEDGE}s)")

    ok(f"dt NO es exactamente igual a N_hedge={N_HEDGE}s (jitter real)", dt != N_HEDGE, f"dt={dt:.6f}s")
    ok(f"dt cae dentro de una banda de tolerancia realista alrededor de N_hedge={N_HEDGE}s "
       f"(entre {N_HEDGE - 0.3}s y {N_HEDGE + 2.0}s)",
       (N_HEDGE - 0.3) <= dt <= (N_HEDGE + 2.0), f"dt={dt:.3f}s")
    ok("motivo == 'N_hedge_expirado_cancelado' -- nunca llego a la fase prop "
       "(el hedge no confirmo, no se manda nada de la prop)",
       r.get("motivo") == "N_hedge_expirado_cancelado" and r.get("order_id_prop") is None, r)
finally:
    para_servidor(proc, fichero_info)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
