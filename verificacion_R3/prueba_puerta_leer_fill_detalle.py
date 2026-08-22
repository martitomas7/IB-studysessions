# -*- coding: utf-8 -*-
"""D9 §3.4/§3.6 fusionadas (AUTORIZACION_3_6_CERRADA.md, autorización R6) --
la PUERTA que el propio texto exige: "el contrato tiene que verificarse
solo, con el adaptador falso y el simulador NT8 cumpliéndolo los dos,
antes de enriquecer nada. Si esa puerta no pasa, para." Este fichero es
esa puerta. Nada de `protocolo_dos_patas.py`/`resolucion_en_vivo.py`
(el esquema enriquecido de los puntos de emisión) se toca todavía --
eso es el siguiente paso, y solo si esto sale 100 % verde.

Tres partes:
  1. `AdaptadorFalso` en proceso, con un reloj FALSO controlable -- valores
     exactos, deterministas.
  2. `AdaptadorSimuladorNT8` a través de un `simulador_nt8.servidor` real --
     no se puede comparar timestamp a timestamp contra la Parte 1 (dos
     procesos, dos relojes de pared reales independientes), así que aquí
     se verifica ESTRUCTURA y SEMÁNTICA (las mismas claves, `None`+motivo
     donde toca, orden temporal coherente) -- pero de punta a punta por el
     socket real, que es lo que de verdad prueba que el método nuevo está
     bien cableado en `servidor.py`/`cliente.py`, no solo en `AdaptadorFalso`.
  3. R3 -- "no se da nada por bueno sin demostrar que falla primero": una
     versión deliberadamente rota que fabrica `ts_feed` en vez de devolver
     `None`+motivo, para confirmar que la comprobación de "sin timestamps
     inventados" SÍ lo cazaría."""
import os
import signal
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot.adaptador_falso import AdaptadorFalso
from simulador_nt8.cliente import AdaptadorSimuladorNT8

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


CLAVES_ESPERADAS = {
    'feed_origen', 'ts_feed', 'ts_feed_motivo', 'ts_orden',
    'ts_fill_broker', 'ts_fill_broker_motivo',
    'ts_fill_recibido', 'ts_fill_recibido_motivo',
}


class _RelojFalso:
    """Reloj lógico controlable -- cada llamada avanza un paso fijo, para
    poder afirmar valores EXACTOS (no solo 'es un número')."""
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 1.0
        return self.t


print("=== 1. AdaptadorFalso en proceso, reloj falso controlable ===")
reloj = _RelojFalso()
a = AdaptadorFalso(reloj=reloj)
a.programa_abrir("CTA-PROP", "MES", fill_en_s=999)   # a proposito: NO llena todavia
oid = a.abrir("CTA-PROP", "MES", 1, 10)               # t=1: ts_creacion
d0 = a.leer_fill_detalle(oid)                          # t=2: avanza() lee, no llena

ok("claves exactas, ni de más ni de menos", set(d0) == CLAVES_ESPERADAS, sorted(d0))
ok("feed_origen es la cuenta de la orden", d0['feed_origen'] == "CTA-PROP", d0['feed_origen'])
ok("ts_orden == ts_creacion (t=1, el instante de abrir())", d0['ts_orden'] == 1.0, d0['ts_orden'])
ok("ts_feed es SIEMPRE None en este simulador (no modela un feed independiente)",
   d0['ts_feed'] is None)
ok("ts_feed_motivo explica por qué, en texto", isinstance(d0['ts_feed_motivo'], str)
   and len(d0['ts_feed_motivo']) > 0, d0['ts_feed_motivo'])
ok("orden todavia NO llena -> ts_fill_broker es None", d0['ts_fill_broker'] is None)
ok("... con motivo explícito, no un None mudo", d0['ts_fill_broker_motivo'] == 'orden_todavia_no_llena')
ok("orden todavia NO llena -> ts_fill_recibido es None", d0['ts_fill_recibido'] is None)
ok("... con motivo explícito", d0['ts_fill_recibido_motivo'] == 'orden_todavia_no_llena')

a.fuerza_fill(oid, precio=5000.0)                      # llena AHORA (dentro de fuerza_fill, no avanza reloj)
d1 = a.leer_fill_detalle(oid)                          # t=3: avanza() ya no hace nada (ya LLENA)

ok("tras llenar: feed_origen no cambia", d1['feed_origen'] == "CTA-PROP")
ok("tras llenar: ts_orden no cambia (sigue siendo el instante de abrir())", d1['ts_orden'] == 1.0)
ok("tras llenar: ts_feed sigue None (nunca deja de serlo en este simulador)", d1['ts_feed'] is None)
ok("tras llenar: ts_fill_broker YA es un número real (el instante de _llena())",
   isinstance(d1['ts_fill_broker'], float), d1['ts_fill_broker'])
ok("... y su motivo desaparece (ya no aplica 'todavia no llena')",
   d1['ts_fill_broker_motivo'] is None)
ok("tras llenar: ts_fill_recibido es el instante de ESTA llamada a leer_fill_detalle() (t=4 -- "
   "el reloj ya avanzó a t=3 dentro de fuerza_fill()/_llena() para fijar ts_fill_broker)",
   d1['ts_fill_recibido'] == 4.0, d1['ts_fill_recibido'])
ok("orden temporal coherente: ts_orden <= ts_fill_broker <= ts_fill_recibido",
   d1['ts_orden'] <= d1['ts_fill_broker'] <= d1['ts_fill_recibido'],
   (d1['ts_orden'], d1['ts_fill_broker'], d1['ts_fill_recibido']))

print("\n=== 2. AdaptadorSimuladorNT8, servidor real por socket (estructura + semántica) ===")


def arranca_servidor():
    dir_sockets = f"/tmp/nt8sim_puerta_lfd_{os.getpid()}"
    fichero_info = f"/tmp/nt8sim_puerta_lfd_info_{os.getpid()}.json"
    proc = subprocess.Popen(
        [sys.executable, "-m", "simulador_nt8", "--entorno=pruebas",
         "--dir-sockets", dir_sockets, "--fichero-info", fichero_info],
        cwd=ING, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    import time
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5.0 and not os.path.exists(fichero_info):
        time.sleep(0.02)
    if not os.path.exists(fichero_info):
        raise RuntimeError("el servidor no arrancó dentro de 5s")
    return proc, os.path.join(dir_sockets, "nt8.sock"), fichero_info


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


proc, ruta_datos, fichero_info = arranca_servidor()
try:
    remoto = AdaptadorSimuladorNT8(ruta_datos)
    remoto.arrancar()
    oid_r = remoto.abrir("CTA-HEDGE", "MES", -1, 4)   # comportamiento por defecto: llena al primer sondeo
    remoto.leer_estado_orden(oid_r)                    # dispara el avance/fill (mismo patrón que la Fase 2 existente)
    dr = remoto.leer_fill_detalle(oid_r)

    ok("el método nuevo SE PUEDE LLAMAR a través del socket (METODOS_CONTRATO lo admite)",
       isinstance(dr, dict), dr)
    ok("mismas claves exactas que en proceso directo", set(dr) == CLAVES_ESPERADAS, sorted(dr))
    ok("feed_origen remoto == la cuenta real", dr['feed_origen'] == "CTA-HEDGE", dr['feed_origen'])
    ok("ts_feed remoto también es None (mismo AdaptadorFalso por dentro, vía MotorSimulado)",
       dr['ts_feed'] is None)
    ok("ts_feed_motivo remoto no está vacío", isinstance(dr['ts_feed_motivo'], str) and dr['ts_feed_motivo'])
    ok("orden ya llena (comportamiento por defecto) -> ts_fill_broker remoto es un número real",
       isinstance(dr['ts_fill_broker'], (int, float)), dr['ts_fill_broker'])
    ok("... con motivo ausente (None), no 'todavia no llena'", dr['ts_fill_broker_motivo'] is None)
    ok("ts_fill_recibido remoto es un número real", isinstance(dr['ts_fill_recibido'], (int, float)),
       dr['ts_fill_recibido'])
    ok("orden temporal remota coherente: ts_orden <= ts_fill_broker <= ts_fill_recibido",
       dr['ts_orden'] <= dr['ts_fill_broker'] <= dr['ts_fill_recibido'],
       (dr['ts_orden'], dr['ts_fill_broker'], dr['ts_fill_recibido']))
finally:
    para_servidor(proc, fichero_info)

print("\n=== 3. R3: 'sin timestamps inventados' SÍ cazaría una implementación rota ===")
print("  (fabricar ts_feed en vez de devolver None+motivo es exactamente lo que R2 prohíbe)")


def _leer_fill_detalle_ROTO(adaptador, order_id):
    """Copia deliberadamente rota: en vez de `ts_feed=None` con motivo,
    hace pasar el reloj LOCAL por el reloj del feed -- justo lo que la
    regla de 07_ADAPTADOR_NT8.md §1.1 prohíbe explícitamente."""
    bueno = adaptador.leer_fill_detalle(order_id)
    roto = dict(bueno)
    roto['ts_feed'] = adaptador.reloj()   # BUG: valor inventado en vez de None+motivo
    roto['ts_feed_motivo'] = None
    return roto


def _sin_timestamps_inventados(d):
    """La comprobación que un agregador de residuo real tendría que aplicar:
    si un campo de timestamp NO es None, su '..._motivo' hermano debe SER
    None (motivo y valor son mutuamente excluyentes) -- y ts_feed, en
    AdaptadorFalso, debe ser SIEMPRE None (nunca placeholder)."""
    return d['ts_feed'] is None and d['ts_feed_motivo'] is not None


d_bueno = a.leer_fill_detalle(oid)
d_roto = _leer_fill_detalle_ROTO(a, oid)
ok("la implementación REAL pasa la comprobación 'sin timestamps inventados'",
   _sin_timestamps_inventados(d_bueno), d_bueno)
ok("la implementación ROTA (ts_feed fabricado) NO la pasa -- la comprobación discrimina de verdad",
   not _sin_timestamps_inventados(d_roto), d_roto)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
