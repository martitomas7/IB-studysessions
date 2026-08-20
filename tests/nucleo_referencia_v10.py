# -*- coding: utf-8 -*-
"""NUCLEO DE REFERENCIA v10 · implementacion pura (sin numpy) de la aritmetica de sesion.
Es la especificacion EJECUTABLE del nucleo. El bot reimplementa esto; el runner compara.

Cambios frente a v8: (1) NO se evalua la barra de entrada b0 -- se entra a su cierre y se
vigila DESDE b0+1 (el look-ahead de v8 costaba el 13,6 % del titular); (2) si k<1 la cuenta
NO OPERA (dx=cst=h=0), Regla 4.3; (3) el deslizamiento de la salida de muerte resta a h.
"""
import math
MLL, DLL, LOCK = 2000.0, 1000.0, 100.0


def barras_desde_tramos(p0, tramos, NB=88):
    ph, pl, pc, p, b = [], [], [], p0, 0
    for hasta, dp in tramos:
        while b < hasta and b < NB:
            n = p + dp
            ph.append(max(p, n) + 0.5); pl.append(min(p, n) - 0.5); pc.append(n)
            p = n; b += 1
    while b < NB:
        ph.append(p + 0.5); pl.append(p - 0.5); pc.append(p); b += 1
    return ph, pl, pc


def resolver_sesion(e):
    """Entradas: dict `entradas` del golden. Salidas: dict `salidas`."""
    NB = e.get('NB', 88)
    ph, pl, pc = barras_desde_tramos(e['camino']['p0'], e['camino']['tramos'], NB)
    bal, pk, G, H = e['bal'], e['pico'], e['G'], e['H_hedge_acum']
    fric, m, exp = e['friccion'], e['m'], e['EXP']
    T, dcap, kcap, b0 = e['T'], e['dcap'], e['kcap'], e['barra_inicio']
    CMS = e.get('CMS', 1.90)
    slip = e.get('deslizamiento', 0.0)
    fsuelo = e.get('fsuelo', 1.0)

    fl = min(pk - MLL, LOCK)
    Mm = bal - fl
    den = G - H + fric
    k = float(kcap) if den <= 0 else math.floor(min(m * Mm / max(den, 1e-9), kcap))
    k1 = max(k, 1.0)                                   # cuna de comision (regla EOD)
    k = float(kcap) if den <= 0 else math.floor(min(m * max(Mm - CMS * k1, 1e-9)
                                                    / max(den, 1e-9), kcap))
    bloq = k < 1
    k = max(k, 1.0)
    pv = 5.0 * k
    cst = CMS * k
    top = min(T - bal + cst, dcap + cst)
    nu = min(max(top, 1e-9) / pv, exp / (5.0 * m))
    ndn = DLL * fsuelo / pv

    p0 = pc[min(b0, NB - 1)]
    iD = iU = NB + 1
    for b in range(b0 + 1, NB):                        # DESDE b0+1: sin mirada atras
        if iD > NB and (pl[b] - p0) <= -ndn: iD = b
        if iU > NB and (ph[b] - p0) >= nu: iU = b
        if iD <= NB and iU <= NB: break
    low = iD <= NB and iD <= iU                        # el suelo gana el empate
    tgt = iU <= NB and iU < iD
    dx = -ndn if low else (nu if tgt else pc[NB - 1] - p0)
    muere = (dx * pv - cst <= -(Mm - 1e-9))
    pausa = low and not muere
    h = -5.0 * m * dx - fric
    if muere: h -= slip
    ib = min(iD if low else (iU if tgt else NB - 1), NB - 1)
    if bloq:                                           # REGLA 4.3: no opera
        dx = 0.0; cst = 0.0; h = 0.0
        muere = False; pausa = False; tgt = False
    return dict(k=k, dx_puntos=round(dx, 6), hedge_dolares=round(h, 4),
                comision=round(cst, 4), muere=muere, pausa=pausa, objetivo=tgt,
                barra_evento=ib, bloqueo_k_menor_1=bloq)
