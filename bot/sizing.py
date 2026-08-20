# -*- coding: utf-8 -*-
"""sizing.py · D1 · 05_ORDEN_DE_CONSTRUCCION.md · norma R-2 (01_ESPECIFICACION_E2E.md §2)

NUCLEO PURO (02_ARQUITECTURA.md §1): sin red, sin reloj, sin ficheros, sin
aleatoriedad, sin logging. Entra un dict de una cuenta/sesion, sale
{k, nu, ndn, bloqueo, comision}. PROHIBIDO (Arquitectura §2): tocar estado,
loguear, llamar a brokers.

Regla de dependencias (Arquitectura §2): "sizing y sesion no importan nada del
proyecto salvo config". Por eso este modulo SI importa `bot.config` -- son las
unicas constantes que no varian por llamada (MLL/DLL/LOCK del proveedor, y los
valores por defecto de CMS/fsuelo cuando el llamador no los especifica), a
diferencia de bal/pico/G/H/fric/m/EXP/T/dcap/kcap, que son datos de ESTA sesion
y llegan como argumentos -- nunca se leen de config dentro de este modulo.

REGLA R6 (04_GUARDARRAILES): este es el nucleo de sesion. Pasa los 14 goldens
y NINGUN delta posterior lo toca. Si un delta futuro necesita cambiar esta
aritmetica, es que ese delta esta mal planteado: para y pregunta.
"""
import math

from bot import config


def plan(bal, pico, G, H, fric, m, EXP, T, dcap, kcap, CMS=None, fsuelo=None):
    """R-2.1 a R-2.5. Devuelve {k, nu, ndn, bloqueo, comision, Mm}.

    `Mm` se incluye ademas de los cuatro que nombra 02_ARQUITECTURA.md §2
    (k, nu, ndn, bloqueo) porque `sesion.py` lo necesita para R-3.4 (la regla
    de muerte EOD) y es un resultado DIRECTO de R-2.1 -- recalcularlo dentro
    de sesion.py exigiria repetir la formula de `fl`/`Mm` en dos sitios, y eso
    es justo lo que R6 prohibe (el nucleo de sesion se implementa una vez).

    CMS y fsuelo son opcionales: si el llamador no los da (como en los goldens,
    que no traen esas claves -- ver tests/goldens_v10.json), se toman de
    03_CONFIG.yaml (proveedor.comision_rt_usd, sizing.fsuelo) en vez de un
    literal en este fichero (R2). MLL/DLL/LOCK del proveedor y valor_punto_usd
    del hedge_broker (la "pv = 5*k" de la norma) SIEMPRE salen de config: no
    forman parte de las entradas de una sesion, son constantes del contrato.
    """
    cfg = config.obtener()
    MLL = cfg.proveedor.mll_usd.valor()
    DLL = cfg.proveedor.dll_usd.valor()
    LOCK = cfg.proveedor.lock_usd.valor()
    valor_punto = cfg.hedge_broker.valor_punto_usd.valor()   # "5" de "pv = 5*k" (R-2.5)
    if CMS is None:
        CMS = cfg.proveedor.comision_rt_usd.valor()
    if fsuelo is None:
        fsuelo = cfg.sizing.fsuelo.valor()

    # R-2.1 · suelo vivo y margen del dia
    fl = min(pico - MLL, LOCK)
    Mm = bal - fl

    # R-2.2 · objetivo de recuperacion
    den = G - H + fric

    # R-2.3 · dos pasadas (la cuna de comision). max(den, 1e-9) es la misma
    # guarda de estabilidad numerica que usa nucleo_referencia_v10.py -- evita
    # una division por un den positivo pero minusculo, no cambia ningun caso
    # de negocio (den<=0 ya se atajo aparte, dos veces, igual que la referencia).
    k0 = float(kcap) if den <= 0 else math.floor(min(m * Mm / max(den, 1e-9), kcap))
    k1 = max(k0, 1.0)
    k = float(kcap) if den <= 0 else math.floor(
        min(m * max(Mm - CMS * k1, 1e-9) / max(den, 1e-9), kcap))

    # R-2.4 · regla del bloqueo -- se decide ANTES de forzar k a 1
    bloqueo = k < 1
    k = max(k, 1.0)

    # R-2.5 · distancias
    pv = valor_punto * k
    cst = CMS * k
    top = min(T - bal + cst, dcap + cst)
    nu = min(max(top, 1e-9) / pv, EXP / (valor_punto * m))
    ndn = DLL * fsuelo / pv

    return dict(k=k, nu=nu, ndn=ndn, bloqueo=bloqueo, comision=cst, Mm=Mm)
