# -*- coding: utf-8 -*-
"""sesion.py · D1 · 05_ORDEN_DE_CONSTRUCCION.md · norma R-3 (01_ESPECIFICACION_E2E.md §3)

NUCLEO PURO (02_ARQUITECTURA.md §1): sin red, sin reloj, sin ficheros, sin
aleatoriedad, sin logging. PROHIBIDO (Arquitectura §2): conocer cuentas, pool,
tesoreria -- este modulo resuelve UN dia de UNA sesion ya abierta, nada mas.

Entrada de mercado: `ph`, `pl`, `pc` son los arrays de precio alto/bajo/cierre
POR BARRA que el adaptador de mercado ya observo -- este modulo NO construye
barras a partir de un precio inicial y una lista de tramos ("camino.tramos" es
un formato compacto de los goldens de prueba, no algo que exista en producción;
ese conversor vive en `bot/adaptador_goldens.py`, fuera del nucleo).

Regla de dependencias (Arquitectura §2): "sizing y sesion no importan nada del
proyecto salvo config". Este modulo importa `bot.config` por el mismo motivo
que `sizing.py`: `valor_punto_usd` (la "5" de "h = -5*m*dx - fric", R-3.5) es
una constante del contrato del hedge, no un dato de la sesion -- nunca llega
como argumento de una llamada.

REGLA R6 (04_GUARDARRAILES): este es el nucleo de sesion. Pasa los 14 goldens
y NINGUN delta posterior lo toca.
"""
from bot import config


def resolver_dia(ph, pl, pc, barra_inicio, plan_resultado, m, fric, deslizamiento=0.0,
                  redondea=False):
    """R-3.1 a R-3.7. `plan_resultado` es exactamente el dict que devuelve
    `sizing.plan(...)`: {k, nu, ndn, bloqueo, comision, Mm}. Devuelve
    {dx_puntos, hedge_dolares, comision, muere, pausa, objetivo, barra_evento}.

    `redondea`: ver el comentario junto al `return` de abajo -- por defecto False
    (precision completa, para la orquestacion multidia); `adaptador_goldens.py`
    lo pone a True para reproducir exactamente `tests/goldens_v10.json`.
    """
    cfg = config.obtener()
    valor_punto = cfg.hedge_broker.valor_punto_usd.valor()

    NB = len(pc)
    b0 = barra_inicio
    k = plan_resultado['k']
    nu = plan_resultado['nu']
    ndn = plan_resultado['ndn']
    cst = plan_resultado['comision']
    Mm = plan_resultado['Mm']
    bloq = plan_resultado['bloqueo']
    pv = valor_punto * k

    # R-3.1 · el precio de entrada es el CIERRE de b0, no un precio aparte que
    # llegue de fuera -- se entra al cierre de la barra b0 (norma R-3.1).
    p0 = pc[min(b0, NB - 1)]

    # R-3.2 · barrido DESDE b0+1 -- NUNCA se evalua la propia barra de entrada
    # (evita el look-ahead que costo el 13,6 % del titular en v8).
    iD = iU = NB + 1
    for b in range(b0 + 1, NB):
        if iD > NB and (pl[b] - p0) <= -ndn: iD = b
        if iU > NB and (ph[b] - p0) >= nu: iU = b
        if iD <= NB and iU <= NB: break

    # R-3.3 · resolucion y desempate -- EL SUELO GANA EL EMPATE
    low = iD <= NB and iD <= iU
    tgt = iU <= NB and iU < iD
    dx = -ndn if low else (nu if tgt else pc[NB - 1] - p0)

    # R-3.4 · muerte (regla EOD): la salida de suelo es siempre al DLL: la
    # cuenta solo muere si la perdida REALIZADA perfora el suelo vivo.
    muere = (dx * pv - cst <= -(Mm - 1e-9))
    pausa = low and not muere

    # R-3.5 · P&L del hedge. El deslizamiento SOLO se aplica en la salida de
    # muerte (es la que se ejecuta con prisa).
    h = -valor_punto * m * dx - fric
    if muere:
        h -= deslizamiento

    ib = min(iD if low else (iU if tgt else NB - 1), NB - 1)

    # R-2.4, aplicado aqui: la cuenta bloqueada NO OPERA -- dx=0, comision=0,
    # hedge=0, no muere, no pausa, no alcanza objetivo. Se aplica AL FINAL,
    # despues de resolver el dia entero, igual que la especificacion ejecutable.
    if bloq:
        dx = 0.0
        cst = 0.0
        h = 0.0
        muere = False
        pausa = False
        tgt = False

    if redondea:
        # SOLO para comparar contra tests/goldens_v10.json, que trae los valores
        # ya redondeados a la misma precision que nucleo_referencia_v10.py. NO se
        # usa en la orquestacion multidia (ciclo_vida.py llama con redondea=False):
        # bal se acumula dia tras dia durante 504 dias, y redondear aqui e
        # multiplicar despues por 5*k (hasta 200) amplifica el error de
        # redondeo y lo acumula -- eso fue un divergencia real medida contra
        # tests/replay_v10.json (ver 05_ORDEN_DE_CONSTRUCCION D2-D7), no una
        # hipotesis. pipeline3.py, el motor de referencia multidia, NUNCA
        # redondea sus valores intermedios.
        dx, h, cst = round(dx, 6), round(h, 4), round(cst, 4)
    return dict(dx_puntos=dx, hedge_dolares=h,
                comision=cst, muere=muere, pausa=pausa,
                objetivo=tgt, barra_evento=ib)
