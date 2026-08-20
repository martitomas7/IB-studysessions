# -*- coding: utf-8 -*-
"""arnes_bot_minimo.py · verificacion_R3/integracion_proceso_real

**ESTO NO ES D8.** D8 ("Ejecutores y detección de eventos",
`05_ORDEN_DE_CONSTRUCCION.md`, Fase 2) todavía no existe -- este fichero es
un DOBLE MÍNIMO de prueba, construido únicamente para que las Fases 5 y 7d2
de este mismo directorio tengan un PROCESO REAL que abrir posición, matar
con `kill -9`, y reiniciar -- sin ese proceso, el escenario (b) del plan de
pruebas ("matar el bot con una posición abierta y reconciliar al reiniciar,
07_ADAPTADOR_NT8.md §6") no se puede demostrar de verdad, solo narrar.

Lo que SÍ hace, y nada más:
  1. Se conecta a `simulador_nt8.servidor` vía `AdaptadorSimuladorNT8`
     (nunca a NT8 real -- esto es exclusivamente para hablar con el
     simulador de pruebas).
  2. Si no hay estado persistido: abre las dos patas llamando a la función
     de PRODUCCIÓN real `bot.protocolo_dos_patas.abre_las_dos_patas` (no
     reimplementa nada del protocolo) y persiste el resultado a
     `--fichero-estado` con el mismo patrón atómico que
     `bot/estado.py::guardar()` (fichero temporal + fsync + os.replace).
  3. Si HAY estado persistido (reinicio): reconcilia contra
     `leer_posicion()` de las dos cuentas, siguiendo la tabla de
     `07_ADAPTADOR_NT8.md` §6 -- fila por fila, sin inventar ningún caso
     nuevo que esa tabla no traiga.
  4. Escribe `--fichero-latido` cada `--intervalo-latido` segundos
     (mismo formato que `09_DESPLIEGUE.md` §1.1: `{"ts_iso":...,
     "pid":..., "fase":...}`) mientras el proceso sigue vivo -- la señal
     que el watchdog de verdad (o, aquí, la Fase 7d2) consulta.
  5. Corre hasta recibir SIGTERM, o hasta que lo maten con SIGKILL/SIGSTOP
     desde fuera (que es justo lo que las pruebas necesitan poder hacerle).

NO decide sizing, ni k/m reales de negocio -- esos se pasan por línea de
comandos, igual que cualquier otro arnés de esta carpeta con `AdaptadorFalso`."""
import argparse
import datetime
import json
import os
import signal
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, ING)

from bot import config
from bot.protocolo_dos_patas import abre_las_dos_patas
from simulador_nt8.cliente import AdaptadorSimuladorNT8


def _guarda_atomico(ruta, obj):
    """Mismo patrón que bot/estado.py::guardar() -- fichero temporal en el
    mismo directorio + fsync + os.replace, para que un kill -9 a mitad de
    la escritura nunca deje el fichero de estado a medias."""
    directorio = os.path.dirname(os.path.abspath(ruta)) or "."
    tmp = os.path.join(directorio, f".{os.path.basename(ruta)}.tmp")
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)


def _carga_si_existe(ruta):
    if not os.path.exists(ruta):
        return None
    with open(ruta) as fh:
        return json.load(fh)


def _escribe_latido(ruta, fase):
    obj = {"ts_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "pid": os.getpid(), "fase": fase}
    _guarda_atomico(ruta, obj)


def _log(msg):
    print(f"[arnes_bot_minimo pid={os.getpid()}] {msg}", flush=True)


def reconcilia(adaptador, estado_previo, cuenta_hedge, cuenta_prop, instrumento_prop):
    """07_ADAPTADOR_NT8.md §6, aplicado literal -- ninguna fila nueva que
    la tabla del documento no traiga ya. Devuelve (debe_operar: bool,
    motivo: str).

    R3 cazó aquí un bug real (verificacion_R3/integracion_proceso_real/
    prueba_bot_muere_y_reconcilia.py, primera corrida): esta función
    consultaba la posición del hedge bajo el literal "MES", pero
    `bot/protocolo_dos_patas.py::abre_las_dos_patas` -- la función de
    PRODUCCIÓN real que este mismo arnés llama para abrir -- usa
    `cfg.hedge_broker.instrumento`, que en 03_CONFIG.yaml NO es el string
    "MES" sino 'MES (Micro E-mini S&P 500)' -- así que la reconciliación
    siempre miraba una posición inexistente (0) y declaraba "descuadre
    fatal" incluso cuando todo estaba perfectamente cuadrado. Corregido:
    leer el mismo instrumento de la misma fuente de configuración que usa
    la propia función que abrió la posición -- nunca un literal propio."""
    instrumento_hedge = config.obtener().hedge_broker.instrumento
    pos_hedge, _ = adaptador.leer_posicion(cuenta_hedge, instrumento_hedge)
    pos_prop, _ = adaptador.leer_posicion(cuenta_prop, instrumento_prop)
    m_esperado = estado_previo["m"]
    k_esperado = estado_previo["k"]
    direccion = estado_previo["direccion"]
    # Revisión adversarial 20-08-2026 (lente calidad_pruebas_r3): esta función
    # ignoraba estado_previo["abierto"] por completo -- calculaba
    # hedge_esperado/prop_esperado a partir de m/k SIEMPRE, sin importar si
    # el intento anterior había abierto de verdad. Con abierto=False (p.ej.
    # tras un hedge_rechazado_limpio o una conexion_caida que SI dejo algun
    # resto), una posicion residual real coincidente con m/k se declaraba
    # "RECONCILIADO, todo cuadra" (fila 5) en vez de "POSICION RESIDUAL"
    # (fila 2) -- reproducido en vivo llamando a esta funcion directamente.
    # Corregido: sin abierto=True, NO se espera ninguna posicion.
    abierto_previo = estado_previo.get("abierto", False)
    hedge_esperado = -direccion * m_esperado if abierto_previo else 0
    prop_esperado = direccion * k_esperado if abierto_previo else 0

    hedge_viva = pos_hedge != 0
    prop_viva = pos_prop != 0

    if hedge_viva != prop_viva:
        return False, (f"DESCUADRE FATAL (una sola pata): hedge={pos_hedge} prop={pos_prop} "
                        "-- 07_ADAPTADOR_NT8.md §6, fila 1. NO se opera, alerta MAXIMA.")
    if not abierto_previo and (hedge_viva or prop_viva):
        return False, (f"POSICION RESIDUAL: estado.json dice abierto=False pero hay posicion viva "
                        f"(hedge={pos_hedge}, prop={pos_prop}) -- 07_ADAPTADOR_NT8.md §6, fila 2. "
                        "NO se opera esa cuenta, alerta, exige reconciliacion manual.")
    if not hedge_viva and not prop_viva:
        return False, ("todo cuadra, sin posicion viva -- dia nuevo, no hay nada que reconciliar "
                        "en este arnes minimo (no abre por si solo tras un reinicio; ver §6 fila 4)")
    if pos_hedge != hedge_esperado or pos_prop != prop_esperado:
        return False, (f"tamano de posicion no coincide con m/k esperados: "
                        f"hedge={pos_hedge} (esperado {hedge_esperado}), "
                        f"prop={pos_prop} (esperado {prop_esperado}) -- §6, fila 3. "
                        "NO se opera, alerta con el detalle del desajuste.")
    return True, (f"RECONCILIADO: reinicio a media sesion, todo cuadra "
                   f"(hedge={pos_hedge}, prop={pos_prop}) -- §6, fila 5. "
                   "NO se re-ejecuta la entrada de b0 (R-3.7).")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--socket-datos", required=True)
    ap.add_argument("--fichero-estado", required=True)
    ap.add_argument("--fichero-latido", required=True)
    ap.add_argument("--cuenta-hedge", default="CTA-HEDGE")
    ap.add_argument("--cuenta-prop", default="CTA-PROP")
    ap.add_argument("--instrumento-prop", default="instrumento-prop-demo")
    ap.add_argument("--direccion", type=int, default=1, choices=(1, -1))
    ap.add_argument("--m", type=float, default=4)
    ap.add_argument("--k", type=float, default=10)
    ap.add_argument("--intervalo-latido", type=float, default=0.2)
    args = ap.parse_args(argv)

    config.obtener()  # valida 03_CONFIG.yaml antes de nada (mismo orden que D0)

    adaptador = AdaptadorSimuladorNT8(args.socket_datos)
    if not adaptador.arrancar():
        _log("no se pudo conectar al simulador -- saliendo (returncode 2)")
        return 2

    estado_previo = _carga_si_existe(args.fichero_estado)
    if estado_previo is None:
        _log(f"sin estado previo -- abriendo las dos patas (direccion={args.direccion}, "
             f"m={args.m}, k={args.k})")
        eventos = []
        r = abre_las_dos_patas(adaptador, args.cuenta_hedge, args.cuenta_prop,
                                args.instrumento_prop, args.direccion, args.m, args.k,
                                eventos=eventos)
        _log(f"resultado de abre_las_dos_patas: {r}")
        estado_previo = dict(direccion=args.direccion, m=args.m, k=args.k,
                              abierto=r["abierto"], order_id_hedge=r.get("order_id_hedge"),
                              order_id_prop=r.get("order_id_prop"))
        _guarda_atomico(args.fichero_estado, estado_previo)
        fase = "abierto" if r["abierto"] else "no_operado_hoy"
    else:
        _log(f"estado previo encontrado -- reconciliando: {estado_previo}")
        debe_operar, motivo = reconcilia(adaptador, estado_previo, args.cuenta_hedge,
                                          args.cuenta_prop, args.instrumento_prop)
        _log(motivo)
        fase = "reconciliado" if debe_operar else "bloqueado_por_descuadre"

    _escribe_latido(args.fichero_latido, fase)

    parar = {"flag": False}
    def _maneja_sigterm(signum, frame):
        parar["flag"] = True
    signal.signal(signal.SIGTERM, _maneja_sigterm)

    _log(f"en marcha, fase={fase} -- escribiendo latido cada {args.intervalo_latido}s hasta SIGTERM")
    while not parar["flag"]:
        _escribe_latido(args.fichero_latido, fase)
        time.sleep(args.intervalo_latido)

    _log("SIGTERM recibido -- parando limpio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
