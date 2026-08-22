# -*- coding: utf-8 -*-
"""bucle_de_tiempo.py · D8.4 reestructuración (RESPUESTA_D8_CONCURRENCIA.md
§3, 20-08-2026), paso 4/5

`orquestador.procesa_dia()` procesa funded ANTES que eval, secuencialmente
-- inocuo en replay (resolución instantánea, un array), pero con
`ResuelveDiaEnVivo` (dueño de su propio `while True` esperando barras) eso
significa que, si las dos están activas el mismo día (medido contra el
pack real: 222/504 días, 44 %), eval no empezaría su propia sesión hasta
que funded resolviera la SUYA entera -- en producción real, con un feed
que bloquea horas por barra, eso es un bug real, no un artefacto de
prueba.

Este módulo es el "bucle de tiempo compartido": UNA sola pasada de barras
alimenta a TODAS las máquinas vivas del día por igual (`MaquinaEnVivo`,
D8.4 paso 3) -- ninguna posee su propio cursor. Ninguna pieza de negocio
nueva: reutiliza intactas `ciclo_vida.arma_intento_funded`/
`cierra_resolucion_funded`, `arma_intento_eval`/`arma_empalme_eval`/
`cierra_resolucion_eval` (D8.4 pasos 1-2) -- el único código nuevo aquí es
el propio bucle que las hace avanzar juntas y encadena el empalme de eval
sin salir de la pasada de barras.

`qok` se calcula CAUSALMENTE (caja de INICIO de día, antes de que corra
ninguna sesión de hoy) -- nunca con el P&L de funded de HOY ya sumado,
que es lo que hace el motor congelado/replay (mirar al futuro de la
propia sesión de hoy es imposible en vivo). Esto es un defecto conocido y
medido, no un bug: afecta a 1/504 días del pack, -49,74 $ acumulados
(-0,17 %) -- ver `RESPUESTA_D8_CONCURRENCIA.md` §2 y §5, y el registro en
`03_CONFIG.yaml` (pendientes) / `modelo/DEFECTOS_CONOCIDOS.md`."""
from bot import config, comandos, residuo_diario
from bot import ciclo_vida as CV
from bot.resolucion_en_vivo import MaquinaEnVivo


def resuelve_dia_concurrente(st, direccion, b0v, qok, modo_auto_confirma,
                              adaptador, fuente_barras, cuenta_hedge_eval, cuenta_prop_eval,
                              cuenta_hedge_funded, cuenta_prop_funded, instrumento_prop,
                              ruta_ordenes, ruta_nivel, dia_negociacion,
                              eventos=None, reloj=None, dormir=None):
    """Un día completo de funded+eval, EN VIVO, por el bucle de tiempo
    compartido. `st["funded"]`/`st["eval"]`/`st["pool"]` se leen tal como
    están (el llamador, `orquestador.procesa_dia()`, ya habrá corrido
    `activa_funded_si_toca` antes de llegar aquí, igual que en el camino
    de siempre).

    Devuelve `(r_funded, r_eval)` -- MISMAS formas que
    `ciclo_vida.procesa_dia_funded()`/`procesa_dia_eval()` (`r_funded` es
    `None` si funded no estaba activa hoy, igual que el camino de
    siempre no la llama en ese caso) -- así `orquestador.procesa_dia()`
    los aplica a `st` exactamente igual, sin que le importe si vinieron
    de aquí o del camino bloqueante de un solo slot (D8.4 pasos 1-3)."""
    eventos = eventos if eventos is not None else []
    cfg = config.obtener()
    empalme_on = comandos.valor_efectivo('empalme', cfg.orquestacion.empalme.valor(),
                                          st, dia_negociacion)
    intentos_nuevos_ok = comandos.valor_efectivo('pausa_eval', True, st, dia_negociacion)
    cuota = cfg.proveedor.cuota_sub_usd.valor()
    rebuy_on = cfg.orquestacion.rebuy.valor()

    def _maquina(slot, cuenta_hedge, cuenta_prop, intento):
        return MaquinaEnVivo(adaptador, cuenta_hedge, cuenta_prop, instrumento_prop, direccion,
                              ruta_ordenes, ruta_nivel, slot, dia_negociacion, intento,
                              eventos=eventos, reloj=reloj, dormir=dormir)

    maquinas = {}   # 'funded' | 'eval' -> MaquinaEnVivo VIGENTE ahora mismo
    contexto = {}   # 'funded' | 'eval' -> el dict de arma_intento_*/arma_empalme_eval en curso
    barra_inicio_de = {}   # 'funded' | 'eval' -> barra_inicio DEL INTENTO VIGENTE (D9 §3.6)
    # D9 §3.6 (autorización R6, 22-08-2026): la secuencia CRUDA (sin
    # reflejar) de barras que este día sirvió `fuente_barras` de verdad --
    # capturada UNA sola vez aquí, en el bucle de tiempo compartido, que es
    # el único sitio con acceso a la barra cruda antes de que cada máquina
    # la refleje por su cuenta (`_refleja_bar`, anclado en su propio
    # `p0_real` de slot). `fuente_barras.abre_dia()` ya dejó el cursor en
    # -1 antes de llegar aquí (bot/fuente_barras.py), así que la barra
    # b=0 es la PRIMERA que se ve en este bucle -- append() en orden basta
    # para que el índice de la lista coincida con `barra.b`, exactamente lo
    # que `sesion.resolver_dia()` espera indexar.
    barras_reales_ph, barras_reales_pl, barras_reales_pc = [], [], []

    if st["funded"]["activa"]:
        arm_f = CV.arma_intento_funded(st["funded"])
        m = _maquina('funded', cuenta_hedge_funded, cuenta_prop_funded, 0)
        m.abre(b0v, arm_f['plan'], arm_f['m'], arm_f['friccion'], arm_f['deslizamiento'])
        maquinas['funded'] = m
        contexto['funded'] = arm_f
        barra_inicio_de['funded'] = b0v

    eventos_cero = dict(intentos=0, aprobaciones=0, emergencias=0, recompras=0, muertes_eval=0)
    arm_e = CV.arma_intento_eval(st["eval"], st["pool"], 0.0, eventos_cero, qok,
                                  intentos_nuevos_ok, st, dia_negociacion)
    st["pool"] = arm_e["pool_estado"]   # el pool es compartido -- se escribe YA, no al cerrar el día
    eval_intento_siguiente = 1
    r_eval_final = None
    eval_hubo_muerte_previa = False
    if arm_e["arranca"]:
        m = _maquina('eval', cuenta_hedge_eval, cuenta_prop_eval, 0)
        m.abre(b0v, arm_e['plan'], arm_e['m'], arm_e['friccion'], arm_e['deslizamiento'])
        maquinas['eval'] = m
        contexto['eval'] = arm_e
        barra_inicio_de['eval'] = b0v
    else:
        r_eval_final = dict(eval_estado=arm_e['eval_estado'], pool_estado=st['pool'],
                             sunk_a_recamara=None, caja_delta=arm_e['caja_delta'], hubo_muerte=False,
                             eventos=arm_e['eventos'], bloqueo=False)

    # --- el bucle de tiempo compartido: UNA barra por vuelta, para TODAS
    #     las máquinas vivas por igual -- esto es lo que resuelve la
    #     concurrencia (ninguna espera a que la otra acabe su día entero).
    while any(m.estado == 'VIGILANDO' for m in maquinas.values()):
        barra = fuente_barras.siguiente_barra()
        if barra is not None:
            barras_reales_ph.append(barra.ph)
            barras_reales_pl.append(barra.pl)
            barras_reales_pc.append(barra.pc)
        for m in list(maquinas.values()):
            if m.estado == 'VIGILANDO':
                m.avanza_barra(barra)

        m_eval = maquinas.get('eval')
        if r_eval_final is None and m_eval is not None and m_eval.estado == 'RESUELTO':
            arm_actual = contexto['eval']
            r = CV.cierra_resolucion_eval(arm_actual['eval_estado'], st['pool'],
                                           arm_actual['caja_delta'], eval_hubo_muerte_previa,
                                           arm_actual['eventos'], m_eval.resultado, arm_actual['plan'],
                                           cuota, rebuy_on, modo_auto_confirma, arm_actual['m'],
                                           arm_actual['G'], arm_actual['friccion'])
            st['pool'] = r['pool_estado']
            if not r['quiere_intentar_empalme']:
                r_eval_final = r
            else:
                arm_emp = CV.arma_empalme_eval(r['eval_estado'], r['pool_estado'], r['caja_delta'],
                                                r['eventos'], m_eval.resultado, empalme_on, qok,
                                                st, dia_negociacion)
                st['pool'] = arm_emp['pool_estado']
                if not arm_emp["arranca"]:
                    # murió y no hubo empalme (deshabilitado, fuera de la
                    # ventana, qcap cerrado, o sin sub disponible) -- vacía.
                    ev = dict(arm_emp['eval_estado'])
                    ev['activa'] = False
                    r_eval_final = dict(eval_estado=ev, pool_estado=arm_emp['pool_estado'],
                                         sunk_a_recamara=r['sunk_a_recamara'],
                                         caja_delta=arm_emp['caja_delta'], hubo_muerte=r['hubo_muerte'],
                                         eventos=arm_emp['eventos'], bloqueo=r['bloqueo'])
                else:
                    nueva = _maquina('eval', cuenta_hedge_eval, cuenta_prop_eval,
                                      eval_intento_siguiente)
                    nueva.abre(arm_emp['b0'], arm_emp['plan'], arm_emp['m'], arm_emp['friccion'],
                               arm_emp['deslizamiento'])
                    maquinas['eval'] = nueva
                    contexto['eval'] = arm_emp
                    barra_inicio_de['eval'] = arm_emp['b0']   # D9 §3.6: el intento vigente cambió de b0
                    contexto['eval_bloqueo_dia'] = r['bloqueo']   # el reportado es SIEMPRE el del intento 0
                    eval_intento_siguiente += 1
                    eval_hubo_muerte_previa = r['hubo_muerte']

        if barra is None:
            break   # red de seguridad -- toda máquina VIGILANDO debe haber
                     # resuelto ya al ver barra=None (MaquinaEnVivo.avanza_barra)

    if r_eval_final is None:
        # el empalme corrió y su propia máquina ya está RESUELTO -- cerrar
        # su resolución (única vez que sale de este 'if', porque el bucle
        # de arriba ya cerró el intento 0 en cuanto resolvió).
        m_eval = maquinas['eval']
        arm_actual = contexto['eval']
        r2 = CV.cierra_resolucion_eval(arm_actual['eval_estado'], st['pool'], arm_actual['caja_delta'],
                                        eval_hubo_muerte_previa, arm_actual['eventos'], m_eval.resultado,
                                        arm_actual['plan'], cuota, rebuy_on, modo_auto_confirma,
                                        arm_actual['m'], arm_actual['G'], arm_actual['friccion'])
        st['pool'] = r2['pool_estado']
        ev2 = dict(r2['eval_estado'])
        if r2['quiere_intentar_empalme']:   # máximo 1 empalme/día -- no se reintenta
            ev2['activa'] = False
        r_eval_final = dict(eval_estado=ev2, pool_estado=r2['pool_estado'],
                             sunk_a_recamara=r2['sunk_a_recamara'], caja_delta=r2['caja_delta'],
                             hubo_muerte=r2['hubo_muerte'], eventos=r2['eventos'],
                             bloqueo=contexto.get('eval_bloqueo_dia', r2['bloqueo']))

    r_funded = None
    if 'funded' in maquinas:
        arm_f = contexto['funded']
        # arma_intento_funded no devuelve caja_delta (a diferencia de eval,
        # funded no toma_sub ni paga coste en su fase PRE) -- arranca en 0.0,
        # igual que hacía procesa_dia_funded con su variable local.
        r_funded = CV.cierra_resolucion_funded(st['funded'], 0.0, maquinas['funded'].resultado,
                                                arm_f['plan'], arm_f['T_c'], arm_f['W_c'],
                                                arm_f['fase'], arm_f['m'], arm_f['G'], arm_f['friccion'])

    # D9 §3.6 (autorización R6, 22-08-2026): el residuo diario, por slot --
    # se añade a `eventos` (la MISMA lista que ya hila la Capa B de
    # bot/bucle_del_dia.py, sin cambiar la firma de retorno de esta
    # función). Solo si el bucle de barras llegó a correr de verdad: un día
    # con las DOS cuentas bloqueadas desde `abre()` (p.ej. el día 210 del
    # pack, ya conocido) nunca entra en el `while` de arriba, así que
    # `barras_reales_pc` queda vacía -- `sesion.resolver_dia()` indexaría
    # `pc[-1]` de una lista vacía. Se documenta el hueco en vez de fingir
    # un residuo (todo-ceros) que no se puede demostrar sin barras.
    if barras_reales_pc:
        for slot, maquina in maquinas.items():
            residuo = residuo_diario.residuo_dia_desde_barras_reales(
                barras_reales_ph, barras_reales_pl, barras_reales_pc, direccion,
                barra_inicio_de[slot], contexto[slot]['plan'], contexto[slot]['m'],
                contexto[slot]['friccion'], contexto[slot]['deslizamiento'], maquina.resultado)
            eventos.append(dict(tipo='residuo_dia', slot=slot, **residuo))
    elif maquinas:
        eventos.append(dict(tipo='residuo_dia_omitido', slots=sorted(maquinas),
                             motivo='sin_barras_capturadas_hoy_dia_bloqueado_desde_abre'))

    return r_funded, r_eval_final
