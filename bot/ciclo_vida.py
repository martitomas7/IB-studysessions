# -*- coding: utf-8 -*-
"""ciclo_vida.py · D4/D5/D6 · 05_ORDEN_DE_CONSTRUCCION.md · norma R-4, R-5 (01_ESPECIFICACION_E2E.md §4-5)

Responsabilidad (02_ARQUITECTURA.md §2): R-4 y R-5 -- pool, empalme, reset, emergencia,
recámara, relevo, escalera. PROHIBIDO: aritmética de sizing (se la pide a `sizing.py`).

Este módulo reproduce, con `R=1` (un solo linaje, no vectorizado) y organizado en
funciones con nombre y responsabilidad propios, la misma lógica que `modelo/pipeline3.py`
implementa vectorizada para miles de réplicas a la vez. Cada función de aquí cita, en su
docstring, la línea o el bloque de `pipeline3.py` del que es la versión de-vectorizada --
así una discrepancia se puede rastrear directamente al origen.

R6 (04_GUARDARRAILES): las funciones de `sizing.py`/`sesion.py` que se llaman desde aquí
NO se tocan. Este módulo solo decide QUÉ cuenta opera y CUÁNDO, y traduce sus resultados
a cambios de estado (pool, recámara, funded) -- la aritmética de una sesión es ajena a él.

Cableado de `bot/comandos.py::valor_efectivo()` (recomendación 1 de RECOMENDACIONES.md,
aplicada 20-08-2026): `toma_sub` y `procesa_dia_eval` reciben `estado`/`dia_actual` y
consultan `valor_efectivo()` para `emergencia`/`empalme`/`pausa_eval` en vez de leer
`03_CONFIG.yaml` directo -- así apagar una de esas tres palancas sin pasar por
`estado.desviaciones_activas` deja de ser posible en el código, no solo prohibido por
la norma. Con `desviaciones_activas=[]` (todo el replay de 504 días), `valor_efectivo()`
devuelve siempre el valor certificado sin tocarlo -- el cableado no puede, por
construcción, mover el resultado del replay.
"""
from bot import config, sizing, sesion, calendario, comandos


# =============================================================================
# POOL DE SUSCRIPCIONES · R-4.1, R-4.4, R-4.5, R-4.6
# =============================================================================

def coste_diario_pool():
    """Coste fijo diario de mantener el pool (R-4.1: 'coste fijo N*cuota/mes').
    `dias_facturacion` no es un número aparte inventado: es la misma convención de
    30 días que ya usa `reset_prob_diaria` (03_CONFIG.yaml lo dice explícito: '1/30
    en vez de las fechas de facturación reales') -- se deriva de ahí, no se repite
    un 30 suelto. Pipeline3.py:217-218 usa el mismo 30.0 para las dos cosas."""
    cfg = config.obtener()
    pool_subs = cfg.orquestacion.pool_subs.valor()
    cuota = cfg.proveedor.cuota_sub_usd.valor()
    dias_facturacion = round(1.0 / cfg.proveedor.reset_prob_diaria.valor())
    return pool_subs * cuota / dias_facturacion


def toma_sub(pool_frescas, pool_rotas, estado, dia_actual):
    """R-4.1 (toma fresca) y R-4.5 (emergencia). Pipeline3.py:188-198 `toma()`.
    `estado`/`dia_actual`: para `valor_efectivo('emergencia', ...)` -- ver
    docstring del módulo. Devuelve (obtuvo, es_emergencia, coste, frescas_nueva,
    rotas_nueva)."""
    cfg = config.obtener()
    if pool_frescas > 0:
        return True, False, 0.0, pool_frescas - 1, pool_rotas
    emergencia_on = comandos.valor_efectivo('emergencia', cfg.orquestacion.emergencia.valor(),
                                             estado, dia_actual)
    if emergencia_on and pool_rotas > 0:
        cuota = cfg.proveedor.cuota_sub_usd.valor()
        return True, True, cuota, pool_frescas, pool_rotas - 1
    return False, False, 0.0, pool_frescas, pool_rotas


def aplica_resets(pool_frescas, pool_rotas, n_resets):
    """R-4.4. `n_resets` ya viene decidido por el llamador (forzado desde el
    replay pack en modo replay; en modo vivo, un sorteo Bernoulli(reset_prob_diaria)
    por sub rota -- eso NO vive aquí, esta función solo aplica el resultado).
    Pipeline3.py:219-222."""
    n = min(n_resets, pool_rotas)
    return pool_frescas + n, pool_rotas - n


def qcap_abierto(recamara_n):
    """R-4.6: no se abren intentos nuevos de eval si ya hay `qcap` dormidas --
    salvo que la tesorería viva alcance `qcap_tes_usd`. Pipeline3.py:307-309."""
    cfg = config.obtener()
    qcap = cfg.orquestacion.qcap.valor()
    return recamara_n < qcap


def qcap_abierto_por_tesoreria(caja, retirado):
    """El levantamiento del tope por tesorería viva (R-4.6, segunda mitad)."""
    cfg = config.obtener()
    qcap_tes = cfg.orquestacion.qcap_tes_usd.valor()
    return (caja - retirado) >= qcap_tes


# =============================================================================
# EVAL · R-4.2, R-4.3 (empalme), R-4.7 (aprobación provisional/confirmada)
# =============================================================================

def arma_intento_eval(eval_estado, pool_estado, caja_delta, eventos, qok,
                       intentos_nuevos_ok, estado, dia_actual):
    """PRE-mercado del intento 0 de eval -- extraído SIN CAMBIOS de lo que
    era el arranque de `procesa_dia_eval` (pipeline3.py:319-330 + el
    `sizing.plan` de la línea ~336), para D8.4 reestructurado
    (RESPUESTA_D8_CONCURRENCIA.md §3: "abre_dia" arma el plan de cada slot
    ANTES de que el bucle de tiempo compartido empiece a mirar barras --
    eval y funded dejan de competir por un único cursor de
    `fuente_barras`).

    `caja_delta`/`eventos`: acumuladores YA EXISTENTES del día (para el
    intento 0 el llamador pasa `0.0`/eventos vacíos) -- se HILAN, nunca se
    sustituyen ni se sustituyen por otro, exactamente como hacía la
    variable local única de la función monolítica; ver `arma_empalme_eval`
    más abajo, que retoma estos MISMOS acumuladores en vez de empezar de
    cero, para que todo el día siga siendo una única cuenta corriente.

    R-4.1: si el slot ya viene activo (una 'pausa' de ayer que sigue el
    mismo linaje), NO se toma ninguna sub nueva -- se arma el plan
    directamente sobre el balance ya acumulado. Si está vacío, solo
    arranca si `qok` Y el operador no ha pausado los intentos nuevos
    (`comandos.pausa_eval`) Y el pool cede una sub (`toma_sub`, R-4.5
    emergencia incluida).

    Devuelve dict(arranca: bool, eval_estado, pool_estado, caja_delta,
    eventos, [plan, m, friccion, deslizamiento] si arranca=True) -- si
    `arranca=False`, el llamador debe devolver el dict de "slot vacío"
    exactamente como hacía la función monolítica."""
    cfg = config.obtener()
    m_eval = cfg.sizing.m_eval.valor()
    exp_eval = cfg.sizing.exp_eval_usd.valor()
    kcap = cfg.sizing.kcap.valor()
    T_eval = cfg.proveedor.objetivo_eval_usd.valor()
    spr = cfg.hedge_broker.spr_usd.valor()
    slip_micro = cfg.hedge_broker.slip_usd_micro.valor()
    cuota = cfg.proveedor.cuota_sub_usd.valor()
    b_eval = cfg.sizing.b_eval_usd.valor()          # R-2.2: G = max(s0,0) + B

    ev = dict(eval_estado)
    pool = dict(pool_estado)
    caja_delta = caja_delta
    eventos = dict(eventos)

    # --- ¿el slot está vacío? intentar arrancar un intento nuevo (R-4.1) -------
    if not ev["activa"]:
        if qok and intentos_nuevos_ok:
            obtuvo, es_emerg, coste, pool["frescas"], pool["rotas"] = toma_sub(
                pool["frescas"], pool["rotas"], estado, dia_actual)
            if obtuvo:
                caja_delta -= coste
                if es_emerg:
                    eventos["emergencias"] += 1
                eventos["intentos"] += 1
                ev = dict(activa=True, bal=0.0, pico=0.0, H=0.0, s0=cuota, k=0.0, m=0.0,
                          aprobada_provisional=False, aprobada_confirmada=False)
    if not ev["activa"]:
        return dict(arranca=False, eval_estado=ev, pool_estado=pool,
                     caja_delta=caja_delta, eventos=eventos)

    friccion = spr * m_eval
    plan = sizing.plan(bal=ev["bal"], pico=ev["pico"], G=max(ev["s0"], 0.0) + b_eval, H=ev["H"],
                        fric=friccion, m=m_eval, EXP=exp_eval, T=T_eval, dcap=1e18, kcap=kcap)
    return dict(arranca=True, eval_estado=ev, pool_estado=pool, caja_delta=caja_delta,
                eventos=eventos, plan=plan, m=m_eval, friccion=friccion,
                deslizamiento=slip_micro * m_eval)


def arma_empalme_eval(eval_estado, pool_estado, caja_delta, eventos, dia_previo,
                       empalme_on, qok, estado, dia_actual):
    """R-4.3: decide si HOY toca el ÚNICO empalme posible tras la muerte de
    un intento -- y si toca, arranca la sub nueva + arma su plan (fricción
    con el factor de empalme). Extraído SIN CAMBIOS de pipeline3.py:369-374
    -- misma forma de salida que `arma_intento_eval` (mismas claves) para
    que el llamador trate los dos intentos igual.

    `dia_previo`: el dict YA RESUELTO del intento que acaba de morir (para
    leer `barra_evento`, R-4.3: "si la muerte ocurre antes de las últimas
    `empalme_barra_limite` barras"). `caja_delta`/`eventos`: los MISMOS
    acumuladores que trae el intento que acaba de morir -- se continúan,
    no se reinician (ver docstring de `arma_intento_eval`)."""
    cfg = config.obtener()
    m_eval = cfg.sizing.m_eval.valor()
    exp_eval = cfg.sizing.exp_eval_usd.valor()
    kcap = cfg.sizing.kcap.valor()
    T_eval = cfg.proveedor.objetivo_eval_usd.valor()
    spr = cfg.hedge_broker.spr_usd.valor()
    slip_micro = cfg.hedge_broker.slip_usd_micro.valor()
    cuota = cfg.proveedor.cuota_sub_usd.valor()
    b_eval = cfg.sizing.b_eval_usd.valor()
    empalme_factor = cfg.orquestacion.empalme_friccion_factor.valor()
    empalme_limite = cfg.orquestacion.empalme_barra_limite.valor()
    nb_use = cfg.sesion.barras_por_dia.valor()

    ev = dict(eval_estado)
    pool = dict(pool_estado)
    caja_delta = caja_delta
    eventos = dict(eventos)

    quiere = empalme_on and (dia_previo["barra_evento"] < nb_use - empalme_limite) and qok
    if not quiere:
        return dict(arranca=False, eval_estado=ev, pool_estado=pool,
                     caja_delta=caja_delta, eventos=eventos)

    obtuvo, es_emerg, coste, pool["frescas"], pool["rotas"] = toma_sub(
        pool["frescas"], pool["rotas"], estado, dia_actual)
    if not obtuvo:
        return dict(arranca=False, eval_estado=ev, pool_estado=pool,
                     caja_delta=caja_delta, eventos=eventos)

    caja_delta -= coste
    if es_emerg:
        eventos["emergencias"] += 1
    eventos["intentos"] += 1
    ev = dict(activa=True, bal=0.0, pico=0.0, H=0.0, s0=cuota, k=0.0, m=0.0,
              aprobada_provisional=False, aprobada_confirmada=False)
    b0_empalme = dia_previo["barra_evento"]
    friccion_empalme = spr * m_eval * empalme_factor
    plan2 = sizing.plan(bal=0.0, pico=0.0, G=max(cuota, 0.0) + b_eval, H=0.0,
                         fric=friccion_empalme, m=m_eval, EXP=exp_eval, T=T_eval,
                         dcap=1e18, kcap=kcap)
    return dict(arranca=True, eval_estado=ev, pool_estado=pool, caja_delta=caja_delta,
                eventos=eventos, plan=plan2, m=m_eval, friccion=friccion_empalme,
                deslizamiento=slip_micro * m_eval, b0=b0_empalme)


def cierra_resolucion_eval(eval_estado, pool_estado, caja_delta, hubo_muerte, eventos,
                            dia, plan, cuota, rebuy_on, modo_auto_confirma, m_eval):
    """POST-mercado de UN intento ya resuelto (sirve tanto para el intento 0
    como para el empalme -- la propia función NO decide si intentar un
    empalme, solo señala `quiere_intentar_empalme`; decidir CUÁNDO
    intentarlo, y que el empalme del empalme no exista, "máximo 1 empalme
    por día", vive en el llamador, `procesa_dia_eval`/D8.4). Extraído SIN
    CAMBIOS de pipeline3.py:337-368 (intento 0) / 375-387 (empalme, mismo
    bloque).

    Devuelve dict(eval_estado, pool_estado, sunk_a_recamara, caja_delta,
    hubo_muerte, eventos, bloqueo, quiere_intentar_empalme)."""
    ev = dict(eval_estado)
    pool = dict(pool_estado)
    eventos = dict(eventos)

    caja_delta += dia["hedge_dolares"]
    ev["H"] += dia["hedge_dolares"]
    ev["bal"] += dia["dx_puntos"] * 5.0 * plan["k"] - dia["comision"]
    ev["pico"] = max(ev["pico"], ev["bal"])
    ev["k"] = plan["k"]           # recomendación 5: persistir k/m del día -- el
    ev["m"] = m_eval               # dashboard no debe RECALCULAR, solo mostrar lo usado
    hubo_muerte = hubo_muerte or dia["muere"]
    if dia["muere"]:
        eventos["muertes_eval"] += 1
        # pipeline3.py:356 "broken += mu.astype(int)" -- la SUB que muere se marca
        # rota, aparte y antes de cualquier toma() que pida una nueva para el
        # empalme. Sin esto el pool pierde la cuenta: una sub que murio no
        # desaparece, queda "rota" hasta que la toque un reset gratis (R-4.4).
        pool["rotas"] += 1

    sunk_a_recamara = None
    bloqueo_hoy = plan["bloqueo"]
    quiere_intentar_empalme = False
    T_eval = config.obtener().proveedor.objetivo_eval_usd.valor()
    if dia["objetivo"] and ev["bal"] >= T_eval - 1e-9:
        sunk_a_recamara, ev, pool, caja_delta, eventos = _aprueba_eval(
            ev, pool, caja_delta, eventos, cuota, rebuy_on, modo_auto_confirma)
    elif dia["muere"]:
        # R-4.3: "si la eval muere intradía y la muerte ocurre antes de las últimas
        # `empalme_barra_limite` barras, el bot empalma el MISMO día ... Máximo 1
        # empalme por día". La decisión de intentarlo de verdad (barra límite, qok,
        # toma_sub) vive en `arma_empalme_eval` -- aquí solo se señala.
        quiere_intentar_empalme = True
    elif bloqueo_hoy:
        # pipeline3.py: en el intento 0, cuando NO hay muerte (mu=False), el "else"
        # del bucle aplica `e_act &= ~mu & ~bq` -- con mu=False eso es `&= ~bq`:
        # un intento 0 bloqueado SI desactiva el slot (a diferencia de una fondeada
        # bloqueada, que sigue intentando manana con el MISMO linaje -- aqui, al
        # no haber linaje que conservar dentro del slot, el slot vuelve a quedar
        # vacio y manana se intenta con una sub nueva).
        ev["activa"] = False
    # si no hubo objetivo, ni muerte, ni bloqueo: sobrevivio/pauso, sigue activa
    # tal cual (bal/H/pico ya actualizados arriba).

    return dict(eval_estado=ev, pool_estado=pool, sunk_a_recamara=sunk_a_recamara,
                caja_delta=caja_delta, hubo_muerte=hubo_muerte, eventos=eventos,
                bloqueo=bloqueo_hoy, quiere_intentar_empalme=quiere_intentar_empalme)


def procesa_dia_eval(eval_estado, pool_estado, recamara_dormidas, direccion,
                      ph, pl, pc, b0v, qok, modo_auto_confirma, estado, dia_actual,
                      resuelve_dia=None):
    """Procesa el slot de evaluación (E=1) durante un día completo, incluido el
    posible empalme -- es la versión de-vectorizada de pipeline3.py:319-387, el
    bucle `for s in range(E): ... for intento in range(2):`.

    D8.4 reestructurado (RESPUESTA_D8_CONCURRENCIA.md §3, 20-08-2026): esta
    función ahora es un envoltorio DELGADO sobre `arma_intento_eval` ->
    `resuelve_dia` -> `cierra_resolucion_eval` (y, si toca empalme,
    `arma_empalme_eval` -> `resuelve_dia` -> `cierra_resolucion_eval` una
    segunda vez) -- exactamente la misma composición, en el mismo orden,
    que antes vivía inline en un solo cuerpo. El camino replay/blocking
    (este mismo, sin cambios de comportamiento) sigue siendo el que usa
    `orquestador.corre_replay()`; el camino EN VIVO concurrente
    (`bot/bucle_de_tiempo.py`, D8.4) llama a las cuatro piezas por
    separado, sustituyendo la llamada bloqueante a `resuelve_dia` por
    pasos no bloqueantes de `bot/resolucion_en_vivo.py::MaquinaEnVivo` --
    así eval y funded dejan de competir por un único cursor de barras
    (ver RESPUESTA_D8_CONCURRENCIA.md, la razón original de esta
    extracción).

    `resuelve_dia` (D8.4, ORDEN_DE_TRABAJO_D8.md §0, revisión 20-08-2026):
    inyección aditiva pura -- por defecto es `sesion.resolver_dia` (el
    oráculo congelado, R6), así que TODO llamador existente (empezando por
    `orquestador.py`) obtiene el comportamiento EXACTO de siempre sin
    cambiar una línea.

    `modo_auto_confirma`: en modo replay (validación contra el motor congelado, que
    aprueba y confirma al instante) esto es True. En el bot real (Arquitectura §8:
    "el bot NUNCA... activa... alerta y espera a que el humano confirme") es False,
    y una aprobación se queda en `aprobada_provisional` hasta que el humano la
    confirma en `estado.json` -- eso NO se implementa en este delta (D2-D7 son
    brókers simulados, Fase 1); se deja el gancho listo para D8/D9.

    `estado`/`dia_actual`: el estado.json completo y el día de negociación de HOY
    -- para `comandos.valor_efectivo()` (`empalme`, `pausa_eval`, y `emergencia`
    dentro de `toma_sub`). `pausa_eval` SOLO bloquea el intento NUEVO del día
    (el slot vacío que arrancaría desde cero) -- no el empalme, que es continuar
    "lo que ya está en marcha" (08_LABORATORIO.md §7.2: "dejando vivo lo que ya
    está en marcha"), no arrancar algo nuevo.

    Devuelve un dict con: eval_estado (nuevo), pool_estado (nuevo), sunk_a_recamara
    (float o None -- el coste hundido que pasa a una dormida nueva si hubo
    aprobación confirmada), caja_delta, hubo_muerte (bool), eventos (dict con
    intentos/aprobaciones/emergencias/recompras/muertes_eval de HOY, para
    contrastar con el replay pack), bloqueo (bool, si el intento único del día
    estuvo bloqueado).
    """
    # OJO (bug real cazado en R3 al re-verificar romper_mi_orquestador.py tras
    # D8.4 paso 1): `resuelve_dia=sesion.resolver_dia` como VALOR POR DEFECTO
    # del parámetro se evaluaría UNA SOLA VEZ, al importar el módulo -- ligado
    # pronto (early binding). `romper_mi_orquestador.py` monkeypatchea
    # `sesion_mod.resolver_dia` DESPUÉS de que `ciclo_vida.py` ya se importó;
    # con un default ligado pronto, ese monkeypatch queda ciego para toda
    # llamada que confíe en el default -- exactamente 2 de las 5 roturas de la
    # puerta (look-ahead R-3.2 y cuenta bloqueada R-2.4/4.3) dejaron de
    # detectarse. Corregido: default `None`, resuelto aquí dentro con ligado
    # tardío -- así SIEMPRE lee `sesion.resolver_dia` en el instante de la
    # llamada, monkeypatch incluido.
    resuelve_dia = resuelve_dia or sesion.resolver_dia
    cfg = config.obtener()
    empalme_on = comandos.valor_efectivo('empalme', cfg.orquestacion.empalme.valor(),
                                          estado, dia_actual)
    intentos_nuevos_ok = comandos.valor_efectivo('pausa_eval', True, estado, dia_actual)
    rebuy_on = cfg.orquestacion.rebuy.valor()
    cuota = cfg.proveedor.cuota_sub_usd.valor()
    m_eval = cfg.sizing.m_eval.valor()
    eventos_cero = dict(intentos=0, aprobaciones=0, emergencias=0, recompras=0, muertes_eval=0)

    arm = arma_intento_eval(eval_estado, pool_estado, 0.0, eventos_cero, qok,
                             intentos_nuevos_ok, estado, dia_actual)
    if not arm["arranca"]:
        return dict(eval_estado=arm["eval_estado"], pool_estado=arm["pool_estado"],
                     sunk_a_recamara=None, caja_delta=arm["caja_delta"], hubo_muerte=False,
                     eventos=arm["eventos"], bloqueo=False)

    dia = resuelve_dia(ph=ph, pl=pl, pc=pc, barra_inicio=b0v, plan_resultado=arm["plan"],
                        m=arm["m"], fric=arm["friccion"], deslizamiento=arm["deslizamiento"])
    r = cierra_resolucion_eval(arm["eval_estado"], arm["pool_estado"], arm["caja_delta"], False,
                                arm["eventos"], dia, arm["plan"], cuota, rebuy_on,
                                modo_auto_confirma, m_eval)

    if not r["quiere_intentar_empalme"]:
        return dict(eval_estado=r["eval_estado"], pool_estado=r["pool_estado"],
                     sunk_a_recamara=r["sunk_a_recamara"], caja_delta=r["caja_delta"],
                     hubo_muerte=r["hubo_muerte"], eventos=r["eventos"], bloqueo=r["bloqueo"])

    arm2 = arma_empalme_eval(r["eval_estado"], r["pool_estado"], r["caja_delta"], r["eventos"],
                              dia, empalme_on, qok, estado, dia_actual)
    if not arm2["arranca"]:
        # murio y no hubo empalme (deshabilitado, fuera del limite de barra,
        # qcap cerrado, o sin sub disponible): la cuenta queda vacia.
        ev = dict(arm2["eval_estado"])
        ev["activa"] = False
        return dict(eval_estado=ev, pool_estado=arm2["pool_estado"],
                     sunk_a_recamara=r["sunk_a_recamara"], caja_delta=arm2["caja_delta"],
                     hubo_muerte=r["hubo_muerte"], eventos=arm2["eventos"], bloqueo=r["bloqueo"])

    dia2 = resuelve_dia(ph=ph, pl=pl, pc=pc, barra_inicio=arm2["b0"], plan_resultado=arm2["plan"],
                         m=arm2["m"], fric=arm2["friccion"], deslizamiento=arm2["deslizamiento"])
    r2 = cierra_resolucion_eval(arm2["eval_estado"], arm2["pool_estado"], arm2["caja_delta"],
                                 r["hubo_muerte"], arm2["eventos"], dia2, arm2["plan"], cuota,
                                 rebuy_on, modo_auto_confirma, m_eval)
    ev2 = dict(r2["eval_estado"])
    if r2["quiere_intentar_empalme"]:   # maximo 1 empalme/dia -- no se reintenta
        ev2["activa"] = False
    return dict(eval_estado=ev2, pool_estado=r2["pool_estado"], sunk_a_recamara=r2["sunk_a_recamara"],
                caja_delta=r2["caja_delta"], hubo_muerte=r2["hubo_muerte"], eventos=r2["eventos"],
                bloqueo=r["bloqueo"])


def _aprueba_eval(ev, pool, caja_delta, eventos, cuota, rebuy_on, modo_auto_confirma):
    """R-4.2 y R-4.7: al tocar objetivo, `sunk = s0 - H` pasa a la recámara, la sub
    se cancela (gratis) y se recompra. En modo replay (auto-confirma) esto ocurre
    al instante, igual que pipeline3.py:357-368. En el bot real la aprobación queda
    `provisional` hasta que el humano la confirma (Arquitectura §8) -- no se activa
    ninguna fondeada sin confirmar (invariante 8 de estado.py)."""
    ev = dict(ev)
    pool = dict(pool)
    sunk = ev["s0"] - ev["H"]
    ev["aprobada_provisional"] = True
    if modo_auto_confirma:
        ev["aprobada_confirmada"] = True
        eventos = dict(eventos)
        eventos["aprobaciones"] += 1
        ev["activa"] = False
        if rebuy_on:
            caja_delta -= cuota
            eventos["recompras"] += 1
            pool["frescas"] += 1
        return sunk, ev, pool, caja_delta, eventos
    # sin confirmar: la cuenta se queda "activa" pero ya no opera (aprobada
    # pendiente) -- el bucle que llama a esto en modo no-replay debe respetar
    # `aprobada_provisional` y no volver a sesionar esa cuenta. No implementado
    # más allá del gancho en este delta (Fase 1, brókers simulados).
    return None, ev, pool, caja_delta, eventos


# =============================================================================
# FUNDED · R-5.1 a R-5.5
# =============================================================================

def activa_funded_si_toca(funded_estado, recamara_dormidas):
    """R-5.1: relevo. Una dormida se activa cuando no hay activa, la espera ya
    venció, y hay dormidas en recámara. Hereda `s0 = sunk_total / n_dormidas`
    -- la MEDIA agregada de TODAS las dormidas vivas en este instante, NO el
    valor propio de ninguna dormida individual (pipeline3.py:251:
    `s0m = d_sunk / max(d_n,1)`; línea 252: `f_s0 = s0m`). El modelo de
    referencia solo agrega (`d_sunk`, `d_n`); nunca trackea el coste hundido
    de cada dormida por separado -- lo dice la propia norma (R-7.4: "el
    simulador de v10 agrega la recámara, así que la política [de selección]
    no se puede medir hoy"). `02_ARQUITECTURA.md` §4 quiere, aun así, que el
    BOT lleve `recamara.dormidas` DESAGREGADA. Para que esa lista sea
    consistente con `recamara.sunk_total` (invariante #1 de estado.py) Y
    reproduzca la aritmética del modelo bit a bit, cada dormida de la lista
    se mantiene siempre a REPARTO IGUAL del agregado (`s0 = sunk_total/n`,
    recalculado en cada alta -- ver el `append` en orquestador.py -- y en
    cada baja, aquí mismo): con este modelo no existe, ni puede
    reconstruirse, un valor individual real que discriminar entre dormidas.
    Con reparto igual la política de qué dormida "sale" es irrelevante en
    valor -- retirar exactamente la media, dividiendo entre una menos, deja
    la media de las que quedan intacta (Sₙ/n − Sₙ/n dividido entre n−1 =
    Sₙ/n otra vez). Se retira la primera (FIFO) por ser la convención por
    defecto de R-7.4 hasta que el operador decida otra.
    Pipeline3.py:244-257.

    Devuelve (funded_estado_nuevo, recamara_dormidas_nueva, activada: bool)."""
    if funded_estado["activa"] or funded_estado["espera"] > 0 or not recamara_dormidas:
        return dict(funded_estado), list(recamara_dormidas), False
    dormidas = list(recamara_dormidas)
    n_antes = len(dormidas)
    sunk_total_antes = sum(d["s0"] for d in dormidas)
    s0m = sunk_total_antes / max(n_antes, 1)
    dormidas.pop(0)                                 # FIFO -- ver docstring
    n_despues = n_antes - 1
    sunk_total_despues = sunk_total_antes - s0m
    reparto = sunk_total_despues / n_despues if n_despues > 0 else 0.0
    dormidas = [dict(d, s0=reparto) for d in dormidas]
    nuevo = dict(funded_estado)
    nuevo.update(activa=True, fase=1, bal=0.0, pico=0.0, H=0.0, s0=s0m, dias=0)
    return nuevo, dormidas, True


def procesa_dia_funded(funded_estado, direccion, ph, pl, pc, b0v, es_dia_nuevo,
                        resuelve_dia=None):
    """R-5.2 a R-5.5: una sesión de la fondeada, y la escalera de cobros si toca
    objetivo. Pipeline3.py:260-296.

    `resuelve_dia`: ver el docstring de `procesa_dia_eval` -- misma inyección
    aditiva pura (D8.4), y el mismo ligado tardío (default `None`, resuelto
    aquí dentro) por el mismo motivo: un default `=sesion.resolver_dia` se
    ligaría pronto (al importar el módulo) y quedaría ciego a cualquier
    monkeypatch de `sesion.resolver_dia` hecho después -- bug real, cazado en
    R3 (`romper_mi_orquestador.py`).
    """
    resuelve_dia = resuelve_dia or sesion.resolver_dia
    cfg = config.obtener()
    m_fun = cfg.sizing.m_fun.valor()
    exp_fun = cfg.sizing.exp_fun_usd.valor()
    kcap = cfg.sizing.kcap.valor()
    spr = cfg.hedge_broker.spr_usd.valor()
    slip_micro = cfg.hedge_broker.slip_usd_micro.valor()
    b_fun = cfg.sizing.b_fun_usd.valor()
    n_ciclos = cfg.proveedor.escalera_retiro.n_ciclos.valor()
    dias_min_eval = cfg.proveedor.dias_min_eval.valor()
    relevo_dias = cfg.proveedor.relevo_dias.valor()
    # escalera_retiro.ciclo_1 / ciclos_2_a_5: a diferencia de la mayoria de entradas
    # de 03_CONFIG.yaml, umbral_bruto_usd/retira_usd/tope_dia_usd NO llevan cada uno
    # su propio {valor:...}: son floats sueltos directamente bajo ciclo_1 (el nodo
    # 'ciclo_1' en si es el que lleva tipo:DERIVADO). Por eso aqui NO se llama
    # .valor() sobre ellos -- ya son el numero.
    esc = cfg['proveedor']['escalera_retiro']

    fu = dict(funded_estado)
    caja_delta = 0.0
    eventos = dict(muertes_funded=0)

    fase = fu["fase"]
    rama = esc['ciclo_1'] if fase == 1 else esc['ciclos_2_a_5']
    T_c = rama['umbral_bruto_usd']
    W_c = rama['retira_usd']
    D_c = rama['tope_dia_usd']

    G = max(fu["s0"], 0.0) + b_fun
    friccion = spr * m_fun
    b0 = b0v
    plan = sizing.plan(bal=fu["bal"], pico=fu["pico"], G=G, H=fu["H"], fric=friccion,
                        m=m_fun, EXP=exp_fun, T=T_c, dcap=D_c, kcap=kcap)
    dia = resuelve_dia(ph=ph, pl=pl, pc=pc, barra_inicio=b0, plan_resultado=plan,
                        m=m_fun, fric=friccion, deslizamiento=slip_micro * m_fun)

    caja_delta += dia["hedge_dolares"]
    fu["H"] += dia["hedge_dolares"]
    fu["bal"] += dia["dx_puntos"] * 5.0 * plan["k"] - dia["comision"]
    fu["pico"] = max(fu["pico"], fu["bal"])
    fu["dias"] += 1
    fu["k"] = plan["k"]    # recomendación 5: persistir k/m del día, no recalcular en el dashboard
    fu["m"] = m_fun

    cerro_linaje = False
    toco_ciclo = False
    if dia["muere"]:
        eventos["muertes_funded"] += 1
        fu["activa"] = False
        fu["espera"] = relevo_dias
    elif dia["objetivo"] and fu["bal"] >= T_c - 1e-9 and fu["dias"] >= dias_min_eval:
        toco_ciclo = True
        caja_delta += W_c
        fu["s0"] = fu["s0"] - fu["H"] - W_c
        fu["H"] = 0.0
        fu["bal"] = 0.0
        fu["pico"] = 0.0
        fu["dias"] = 0
        fu["fase"] = fase + 1
        if fu["fase"] > n_ciclos:
            cerro_linaje = True
            fu["activa"] = False
            fu["espera"] = relevo_dias
    elif plan["bloqueo"]:
        # R-2.4 aplicado a funded, igual que a eval (bug encontrado en el
        # replay, dia 210: pipeline3.py:284 `f_act = f_act & ~mu & ~bq` --
        # el bloqueo (k<1) desactiva TAMBIEN a funded, no solo la deja
        # "congelada". A diferencia de la muerte (`mu`), el bloqueo NO
        # pone `espera` (linea 283 de pipeline3.py solo lo hace para `mu`):
        # el relevo puede volver a intentarlo el dia siguiente sin esperar.
        fu["activa"] = False

    return dict(funded_estado=fu, caja_delta=caja_delta, hubo_muerte=dia["muere"],
                toco_ciclo=toco_ciclo, cerro_linaje=cerro_linaje, eventos=eventos,
                bloqueo=plan["bloqueo"])
