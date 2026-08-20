# -*- coding: utf-8 -*-
"""tesoreria.py · D7 · 05_ORDEN_DE_CONSTRUCCION.md · norma R-7 (01_ESPECIFICACION_E2E.md §7)

Responsabilidad (02_ARQUITECTURA.md §2): R-7 -- muro dinámico, degradación, retiro
mensual, `qcap`/`qcap_tes` (esos dos viven en ciclo_vida.py, que es quien los consulta
en el momento de abrir un intento). PROHIBIDO: decidir operaciones -- esto mide y avisa,
no abre ni cierra cuentas. Pipeline3.py:392-408.
"""
from bot import config


def muro_dinamico(micros_eval_comprometidos_hoy, exp_eval_comprometido_hoy):
    """R-7.1: 'muro = capital_usd - (m_fun*margen + exp_fun) - (micros_eval_hoy*margen
    + exp_eval_hoy)'. Solo cuenta el capital REALMENTE comprometido hoy -- si el slot
    de eval está vacío hoy, sus dos términos son 0.

    Lee `circuito.capital_usd`, NO `capital.capital_usd` directo (REVISION_REV5.md
    §3, 20-08-2026): son el mismo número mientras solo haya un circuito, pero
    `circuito.capital_usd` es el que existe para que un segundo circuito -- con su
    propio 03_CONFIG.yaml -- nunca pueda leer por descuido el capital de otro."""
    cfg = config.obtener()
    capital = cfg.circuito.capital_usd.valor()
    m_fun = cfg.sizing.m_fun.valor()
    exp_fun = cfg.sizing.exp_fun_usd.valor()
    margen = cfg.sesion.cal_rth.margen_usd.valor()
    return (capital - (m_fun * margen + exp_fun)
            - (micros_eval_comprometidos_hoy * margen + exp_eval_comprometido_hoy))


def comprueba_degradacion(caja, retirado, muro, ya_degradado):
    """R-7.2: se declara degradación el PRIMER día en que caja-retirado < -muro.
    Una vez True, no se revierte solo (mismo principio que `estado.json.degradado`,
    Arquitectura §4)."""
    if ya_degradado:
        return True
    return (caja - retirado) < -muro


def retiro_de_fin_de_mes(caja, retirado, es_dia_de_retiro):
    """R-7.3: cada `dias_por_mes` días de negociación se retira
    `max(0, caja - retencion_c_usd - retirado)`. Devuelve el importe retirado hoy
    (0.0 si no toca retiro)."""
    if not es_dia_de_retiro:
        return 0.0
    cfg = config.obtener()
    retencion = cfg.orquestacion.retencion_c_usd.valor()
    return max(0.0, caja - retencion - retirado)


def es_dia_de_retiro(dia_negociacion):
    """Cada `tesoreria.dias_por_mes` días de negociación (Arquitectura §5: 'si toca
    fin de mes'). `dia_negociacion` es el contador 1-indexado del día que se acaba
    de cerrar."""
    dias_por_mes = config.obtener().tesoreria.dias_por_mes.valor()
    return dia_negociacion % dias_por_mes == 0
