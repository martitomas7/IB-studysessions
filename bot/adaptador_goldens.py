# -*- coding: utf-8 -*-
"""adaptador_goldens.py · D1 · el "<tu_adaptador>" de tests/runner_goldens_v10.py

ESTO NO ES EL BOT. Es el pegamento de prueba que traduce entre el formato
compacto de tests/goldens_v10.json (un precio inicial + una lista de "tramos")
y la interfaz real y separada de sizing.py + sesion.py -- que es la que de
verdad usara el bot (D2 en adelante), alimentada con precios reales del
adaptador de mercado, no con "tramos" sinteticos.

Por eso `_barras_desde_tramos` -- con su literal 0.5 -- vive AQUI y no en
sesion.py: 0.5 no es un numero de negocio, es la mitad del "ancho" sintetico
que este conversor de formato de prueba le da a cada barra generada a partir
de un cierre (para que tenga un alto y un bajo con los que sesion.py pueda
barrer) -- es un detalle de como esta codificado el fixture de los goldens,
igual que en tests/nucleo_referencia_v10.py, al que replica exactamente para
poder compararse contra el.

Expone `resolver_sesion(entradas) -> salidas` con las claves exactas que
espera tests/runner_goldens_v10.py.
"""
from bot import config, sizing, sesion


def _barras_desde_tramos(p0, tramos, NB):
    """Replica exacta de la funcion homonima de tests/nucleo_referencia_v10.py
    -- mismo formato de fixture, mismo resultado. Construye ph/pl/pc a partir
    de una lista de (hasta, delta_por_barra)."""
    ph, pl, pc = [], [], []
    p, b = p0, 0
    for hasta, dp in tramos:
        while b < hasta and b < NB:
            n = p + dp
            ph.append(max(p, n) + 0.5)
            pl.append(min(p, n) - 0.5)
            pc.append(n)
            p = n
            b += 1
    while b < NB:
        ph.append(p + 0.5)
        pl.append(p - 0.5)
        pc.append(p)
        b += 1
    return ph, pl, pc


def resolver_sesion(entradas):
    """Entradas: dict del golden (ver tests/goldens_v10.json). Salidas: dict
    con las mismas nueve claves que tests/runner_goldens_v10.py compara."""
    e = entradas
    # 88 = sesion.barras_de_la_serie en 03_CONFIG.yaml, no un literal (R2): el
    # golden puede pisarlo con su propio 'NB' (algunos casos lo hacen), y si no
    # lo trae, el valor por defecto sale de la config, no de la cabeza.
    NB = e.get('NB', config.obtener().sesion.barras_de_la_serie.valor())
    ph, pl, pc = _barras_desde_tramos(e['camino']['p0'], e['camino']['tramos'], NB)

    resultado_plan = sizing.plan(
        bal=e['bal'], pico=e['pico'], G=e['G'], H=e['H_hedge_acum'],
        fric=e['friccion'], m=e['m'], EXP=e['EXP'], T=e['T'],
        dcap=e['dcap'], kcap=e['kcap'],
        CMS=e.get('CMS'), fsuelo=e.get('fsuelo'),
    )

    resultado_dia = sesion.resolver_dia(
        ph=ph, pl=pl, pc=pc, barra_inicio=e['barra_inicio'],
        plan_resultado=resultado_plan, m=e['m'], fric=e['friccion'],
        deslizamiento=e.get('deslizamiento', 0.0), redondea=True,
    )

    return dict(
        k=resultado_plan['k'],
        dx_puntos=resultado_dia['dx_puntos'],
        hedge_dolares=resultado_dia['hedge_dolares'],
        comision=resultado_dia['comision'],
        muere=resultado_dia['muere'],
        pausa=resultado_dia['pausa'],
        objetivo=resultado_dia['objetivo'],
        barra_evento=resultado_dia['barra_evento'],
        bloqueo_k_menor_1=resultado_plan['bloqueo'],
    )
