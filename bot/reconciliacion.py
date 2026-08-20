# -*- coding: utf-8 -*-
"""reconciliacion.py · D8.4 · 07_ADAPTADOR_NT8.md §6 · diseño grounded de
D8.4 §2.6

Reconciliación de arranque, EN PRODUCCIÓN: se llama UNA VEZ al arrancar
`bot/bucle_del_dia.py` (frío o tras cualquier reinicio, D8.5), antes de
operar nada. Promueve la lógica de
`verificacion_R3/integracion_proceso_real/arnes_bot_minimo.py::reconcilia`
(que es SOLO un arnés de prueba, "NO es D8") a código real -- pero, a
diferencia de ese arnés, delega la clasificación en `bot/seguridad.py`
(`clasifica_posicion`/`clasifica_conocimiento`), que existe exactamente
para esto, en vez de reimplementar el criterio a mano.

PROHIBIDO (mismo principio que el resto de `bot/`): esto no decide
sizing ni sesión -- lee lo que YA se sabe (posiciones reales,
legibilidad) y aplica la tabla de `10_SEGURIDAD.md` §1-§3. `bot/bucle_del_dia.py`
es quien de verdad ejecuta el bucle una vez `debe_operar` es `True`."""
from bot import config, idempotencia_ordenes as IO, protocolo_dos_patas as DP
from bot import seguridad as SEG


def reconcilia_arranque(adaptador, st, cuenta_hedge_eval, cuenta_prop_eval,
                         cuenta_hedge_funded, cuenta_prop_funded, instrumento_prop,
                         ruta_nivel, ruta_ordenes, eventos=None, reloj=None, dormir=None):
    """Compara, por slot (`eval`/`funded`), lo que `estado.json` CREE que
    tiene abierto contra lo que el bróker REALMENTE reporta -- "la
    posición abierta: fuente de verdad SIEMPRE el bróker, nunca
    estado.json" (10_SEGURIDAD.md §4.D).

    Devuelve `{debe_operar: bool, eval: {...}, funded: {...}}` -- `debe_operar`
    es `True` solo si LOS DOS slots quedan en condición de operar (PLANO,
    o CUBIERTO con tamaños que corresponden -- reinicio a media sesión)."""
    cfg = config.obtener()
    MES = cfg.hedge_broker.instrumento
    eventos = eventos if eventos is not None else []
    resultado = {}

    for slot, cuenta_hedge, cuenta_prop, activa, m_esp, k_esp in (
            ("eval", cuenta_hedge_eval, cuenta_prop_eval,
             st["eval"]["activa"], st["eval"].get("m", 0), st["eval"].get("k", 0)),
            ("funded", cuenta_hedge_funded, cuenta_prop_funded,
             st["funded"]["activa"], st["funded"].get("m", 0), st["funded"].get("k", 0))):
        try:
            cant_hedge, _ = adaptador.leer_posicion(cuenta_hedge, MES)
            hedge_legible = adaptador.hay_conexion(cuenta_hedge)
        except Exception:
            cant_hedge, hedge_legible = 0, False
        try:
            cant_prop, _ = adaptador.leer_posicion(cuenta_prop, instrumento_prop)
            prop_legible = adaptador.hay_conexion(cuenta_prop)
        except Exception:
            cant_prop, prop_legible = 0, False

        cp = SEG.clasifica_posicion(cant_hedge, cant_prop, m_esp if activa else 0,
                                     k_esp if activa else 0, en_ventana_transicion=False)
        ck = SEG.clasifica_conocimiento(hedge_legible, prop_legible, cp)

        if ck == 'DESCONOCIDO':
            DP.cierra_las_dos_patas(adaptador, cuenta_prop, instrumento_prop, cuenta_hedge,
                                     eventos=eventos, reloj=reloj, dormir=dormir)
            SEG.reacciona_a_desconocido(
                ruta_nivel, detalle=f"{slot}: hedge_legible={hedge_legible} "
                                    f"prop_legible={prop_legible} cant_hedge={cant_hedge} "
                                    f"cant_prop={cant_prop}")
            resultado[slot] = dict(debe_operar=False, motivo='DESCONOCIDO')
        elif cp == 'VIOLACION':
            DP.cierra_las_dos_patas(adaptador, cuenta_prop, instrumento_prop, cuenta_hedge,
                                     eventos=eventos, reloj=reloj, dormir=dormir)
            SEG.reacciona_a_violacion_tamanos(
                ruta_nivel, detalle=f"{slot}: hedge={cant_hedge} (esperado {m_esp}) "
                                    f"prop={cant_prop} (esperado {k_esp})")
            resultado[slot] = dict(debe_operar=False, motivo='VIOLACION_TAMANOS')
        elif cp == 'CUBIERTO':
            # reinicio a media sesión (07_ADAPTADOR_NT8.md §6, última fila): NO
            # se re-ejecuta la entrada -- se retro-completa cualquier intención
            # de HOY que quedara sin resultado (D8.5) y se sigue sondeando el
            # bracket ya vivo (bot/bucle_del_dia.py, siguiente paso).
            for iid in IO.intenciones_sin_resultado(ruta_ordenes, st["dia_negociacion"] + 1):
                if iid.split(':')[1] == slot:
                    IO.marca_resultado(ruta_ordenes, iid,
                                        dict(reconciliado=True, cant_hedge=cant_hedge,
                                             cant_prop=cant_prop))
            resultado[slot] = dict(debe_operar=True, motivo='CUBIERTO_REANUDA')
        else:   # PLANO
            resultado[slot] = dict(debe_operar=True, motivo='PLANO_DIA_NUEVO')

    return dict(debe_operar=all(r['debe_operar'] for r in resultado.values()), **resultado)
