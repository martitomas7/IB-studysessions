# -*- coding: utf-8 -*-
"""bucle_del_dia.py · D8.4 · ORDEN_DE_TRABAJO_D8.md §0/§D8.4 · diseño
grounded (panel de ángulos + síntesis, 20-08-2026)

"D8.4 · El bucle del día. Ensambla lo que ya existe: cargar estado ->
calendario -> sizing por cuenta -> abre_las_dos_patas -> órdenes en
reposo -> vigilar -> cerrar -> ciclo_vida -> tesorería -> persistir ->
línea del diario. Ninguna pieza nueva salvo el pegamento."

Y de verdad lo es: la única pieza NUEVA en este fichero es el propio
bucle (reconciliar, decidir dirección/ventana/resets si está en vivo,
construir el `ResuelveDiaEnVivo` de cada slot, persistir) -- toda la
aritmética de negocio (pool/funded/eval/tesorería/retiro/contra_pendiente)
vive en `bot/orquestador.py::procesa_dia()`, la MISMA función que usa
`corre_replay()` para los 504 días offline. Esto es lo que hace cierto,
en sentido fuerte, "el bucle del día tiene que ser UNO SOLO" (§0): esta
función llama a `orquestador.procesa_dia()` para CADA día, tanto si la
fuente de barras es un pack de replay (Puerta Grande, §4) como si es un
feed en vivo -- nunca una aritmética "equivalente" reimplementada aparte.
"""
import json
import os
from functools import partial

from bot import bloqueo_proceso, bucle_de_tiempo, calendario, config, estado, orquestador
from bot import reconciliacion, resolucion_en_vivo, seguridad as SEG


def _escribe_linea_diario(ruta_diario, diario):
    """Append-only, mismo principio que el resto del proyecto -- el
    diario NUNCA se reescribe, solo crece. `orquestador.corre_replay()`
    escribe todo el fichero de una vez (`ruta_salida_diario`); aquí se
    añade una línea por día, según se procesa."""
    directorio = os.path.dirname(os.path.abspath(ruta_diario)) or '.'
    os.makedirs(directorio, exist_ok=True)
    with open(ruta_diario, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(diario) + "\n")


FASES_VALIDAS = frozenset({'f3.1', 'f3.2', 'f3.3', 'plena'})


def _topes_de_fase(fase):
    """D9 §3.2 (autorización R6, 22-08-2026): la tabla fase -> topes tal
    cual la fijó el operador. Vive AQUÍ, no en `orquestador.py`/
    `bucle_de_tiempo.py` -- esos dos módulos solo APLICAN números, nunca
    saben qué es 'f3.1' (docstring de `orquestador.py`: "prohibido que
    contenga reglas de negocio").

    | fase  | eval | funded | recamara | rebuy / emergencia |
    |-------|------|--------|----------|--------------------|
    | f3.1  | 1    | 0      | 0        | apagados           |
    | f3.2  | 1    | 1      | 1        | encendidos         |
    | f3.3  | -    | 1      | qcap     | según config       |
    | plena | -    | -      | -        | según config       |

    `None` en un campo = "sin tope EXTRA para esa cuenta, más allá de lo
    que ya hace config" (NUNCA "sin cuentas permitidas") -- 'f3.3.recamara'
    usa `None` porque eso es exactamente lo que ya hace `qcap_abierto()`
    sin tope de fase (capado a `orquestacion.qcap`, ni más ni menos). Para
    'plena' se devuelve `None` directamente (el dict entero, no un campo)
    -- la señal que `orquestador.procesa_dia()`/
    `bucle_de_tiempo.resuelve_dia_concurrente()` interpretan como "cero
    cambio de comportamiento", el requisito de que el replay de 504 días
    quede intacto bit a bit.

    `funded=1` en f3.3 es ESTRUCTURAL, no un tope nuevo que haga falta
    comprobar -- `st['funded']` es un único booleano en este modelo (nunca
    una lista), así que jamás puede haber más de una fondeada activa a la
    vez, con o sin esta tabla. Se deja explícito aquí, como pidió el
    operador, "para que nadie lo lea como 'en f3.3 se sueltan las
    fondeadas'" -- documentación, no una comprobación nueva."""
    if fase not in FASES_VALIDAS:
        raise ValueError(f"fase={fase!r} no reconocida -- debe ser una de {sorted(FASES_VALIDAS)}")
    if fase == 'f3.1':
        return dict(eval=1, funded=0, recamara=0, rebuy=False, emergencia=False)
    if fase == 'f3.2':
        return dict(eval=1, funded=1, recamara=1, rebuy=True, emergencia=True)
    if fase == 'f3.3':
        return dict(eval=None, funded=1, recamara=None, rebuy=None, emergencia=None)
    return None   # 'plena' -- sin tope de fase, comportamiento de siempre


ETIQUETAS_DESCRIPTOR_VALIDAS = frozenset({'demo', 'real'})


def _modo_nt8_esperado(fase):
    """D9 §3.5 reducida (`DECISION_CREDENCIALES_Y_FASE.md`, autorización R6,
    22-08-2026): qué `modo` (07_ADAPTADOR_NT8.md §1.2) debe reportar NT8
    para que la `fase` declarada tenga sentido. Hoy TODA fase de §3.2
    (`f3.1`/`f3.2`/`f3.3`/`plena`) es dinero real -- ninguna de las cuatro
    admite una cuenta `SIMULADA` por debajo.

    Cuando D9 §3.3 (`papel_feed_retrasado`) exista, esa rama exigirá
    `'SIMULADA'` -- pero ese modo todavía NO es un valor de `fase` ni un
    parámetro que `bucle_del_dia()` reciba hoy, así que esta función no
    tiene todavía nada que ramificar para él. Quien construya §3.3 debe
    extender ESTA función (no duplicar la tabla en otro sitio) el día que
    `papel_feed_retrasado` exista de verdad."""
    if fase not in FASES_VALIDAS:
        raise ValueError(f"fase={fase!r} no reconocida -- debe ser una de {sorted(FASES_VALIDAS)}")
    return 'REAL'


def _valida_descriptor_nt8(descriptor):
    """Comprobación de forma, no de realidad -- ver `_verifica_identidad_nt8()`
    para la parte que sí pregunta a NT8. `etiqueta` es puramente informativa
    (se pinta en el dashboard), pero un valor fuera de {'demo','real'} es un
    error de configuración y debe fallar igual de alto que cualquier otro."""
    f = []
    if 'cuenta_nt8' not in descriptor or not descriptor['cuenta_nt8']:
        f.append("descriptor_nt8: falta 'cuenta_nt8' (o está vacío)")
    if descriptor.get('etiqueta') not in ETIQUETAS_DESCRIPTOR_VALIDAS:
        f.append(f"descriptor_nt8: etiqueta={descriptor.get('etiqueta')!r} no reconocida -- "
                 f"debe ser una de {sorted(ETIQUETAS_DESCRIPTOR_VALIDAS)}")
    return f


def _verifica_identidad_nt8(fase, descriptor, adaptador):
    """D9 §3.5 reducida (`DECISION_CREDENCIALES_Y_FASE.md`, autorización R6,
    22-08-2026): "la guarda se verifica contra la realidad, no contra la
    etiqueta". Al arrancar, se le pregunta a NT8 (nunca al propio descriptor)
    qué cuenta es y si es SIMULADA o REAL, y se compara con lo que la `fase`
    declarada exige (`_modo_nt8_esperado()`). Devuelve la lista de fallos
    (vacía = arranca limpio) -- mismo contrato de retorno que
    `estado.py::valida_tope_fase()`, DELIBERADAMENTE separada de ella (no
    tiene nada que ver con `estado.json`, así que no tiene nada que hacer
    en `bot/estado.py`).

    `descriptor=None` -> nunca falla: opt-in, igual que `topes=None` en
    D9 §3.2 -- ni un solo punto de llamada existente (los 504 días de LA
    PUERTA GRANDE incluidos, que ni siquiera usan un `AdaptadorFalso`, sino
    `AdaptadorReplaySobrePack`) declara un descriptor, así que ninguno
    empieza a preguntarle nada a NT8 por este cambio. El día que exista un
    `--config` real (D9 §5.4, todavía sin construir) será quien decida CÓMO
    se lee `descriptor_nt8` de disco -- esta función solo exige la forma ya
    resuelta, un dict, el mismo principio que `orquestador.procesa_dia(...,
    topes=)` exige números ya resueltos, nunca una ruta ni una etiqueta de
    fase en crudo."""
    if descriptor is None:
        return []
    f = _valida_descriptor_nt8(descriptor)
    if f:
        return f
    cuenta = descriptor['cuenta_nt8']
    if not adaptador.hay_conexion(cuenta):
        return [f"NT8 no sabe contestar por la cuenta declarada ({cuenta!r}): "
                f"hay_conexion() dice que no hay conexión"]
    modo, motivo = adaptador.consulta_modo_cuenta(cuenta)
    if modo is None:
        return [f"NT8 no sabe contestar por la cuenta declarada ({cuenta!r})"
                + (f": {motivo}" if motivo else "")]
    esperado = _modo_nt8_esperado(fase)
    if modo != esperado:
        return [f"la fase declarada ({fase!r}) exige una cuenta {esperado}, pero NT8 dice que "
                f"la cuenta declarada ({cuenta!r}) es {modo}"]
    return []


def _escribe_eventos_residuo(dir_residuo, dia_negociacion, eventos):
    """D9 §3.6 (autorización R6, 22-08-2026, Capa B): un fichero JSONL por
    día, `residuo/eventos_<dia_negociacion>.jsonl` -- una línea por evento
    (`divergencia_fill`, `residuo_operacion`, `DIVERGENCIA_ORACULO`,
    `residuo_dia`/`residuo_dia_omitido`, ...). Deliberadamente un directorio
    NUEVO, `residuo/`, separado de `laboratorio/` (08_LABORATORIO.md §2):
    productor distinto -- `laboratorio/` lo escribe el indicador NT8 del
    lado del mercado; esto lo escribe el propio bot, del lado de su
    ejecución. Fusionar los dos en un futuro es una decisión del operador,
    no algo que este delta deba decidir por su cuenta.

    Solo se llama para un día que de verdad pasó por el bucle de tiempo
    concurrente (`resuelve_concurrente is not None`, ver el llamador) --
    un día puramente REPLAY nunca rellena `eventos_hoy`, así que no genera
    ningún fichero (nada que persistir, nada que fingir)."""
    os.makedirs(dir_residuo, exist_ok=True)
    ruta = os.path.join(dir_residuo, f"eventos_{dia_negociacion:04d}.jsonl")
    with open(ruta, 'w', encoding='utf-8') as fh:
        for ev in eventos:
            fh.write(json.dumps(ev) + "\n")


def bucle_del_dia(fuente_barras, adaptador,
                   cuenta_hedge_eval, cuenta_prop_eval, cuenta_hedge_funded, cuenta_prop_funded,
                   instrumento_prop, ruta_estado, ruta_nivel, ruta_ordenes, ruta_lock,
                   dir_instantaneas, dias_retenidos, ruta_diario, fase,
                   modo_auto_confirma=True, rng=None, reloj=None, dormir=None, dir_residuo=None,
                   descriptor_nt8=None):
    """El bucle único de D8.4. `fuente_barras` (`bot/fuente_barras.py`) y
    `adaptador` (puerto de `07_ADAPTADOR_NT8.md` §1) son los DOS puertos
    de §0 -- todo lo demás (nombres de cuenta, rutas de persistencia) es
    configuración de despliegue, no aritmética de negocio.

    Si `fuente_barras.abre_dia()` devuelve un `ContextoDia` con
    `direccion=None` (mismo contrato que `FuenteEnVivo`), este bucle
    sortea de verdad (dirección con la regla CONTRA, ventana, resets) y
    liga un `resuelve_concurrente` (`bot/bucle_de_tiempo.py`, D8.4
    reestructuración -- RESPUESTA_D8_CONCURRENCIA.md §3: funded y eval se
    resuelven JUNTAS, por un único bucle de barras compartido, nunca una
    esperando a que la otra acabe su día entero) -- si trae `direccion`
    ya forzada (mismo contrato que `FuenteDeReplay`), delega en
    `sesion.resolver_dia` sin construir nada nuevo (pasando
    `resuelve_dia_eval=None`/`resuelve_dia_funded=None` a `procesa_dia()`,
    que usa su propio default).

    `dir_residuo` (D9 §3.6, autorización R6, 22-08-2026, Capa B): opcional,
    `None` por defecto -- si se pasa, cada día que corre por el bucle de
    tiempo concurrente vuelca sus `eventos_hoy` (divergencia_fill,
    residuo_operacion, DIVERGENCIA_ORACULO, residuo_dia/residuo_dia_omitido)
    a `dir_residuo/eventos_<dia>.jsonl`. `None` preserva el comportamiento
    de siempre (no escribe nada) -- deliberado: los nueve arneses de R3 que
    ya llaman a esta función se escribieron antes de que esto existiera, y
    forzarles un directorio que no necesitan no aporta nada; solo el
    arnés dedicado de esta pieza (`verificacion_R3/prueba_residuo_operacion.py`)
    lo pasa de verdad.

    `fase` (D9 §3.2, autorización R6, 22-08-2026): OBLIGATORIO, sin valor
    por defecto -- una de `'f3.1'`/`'f3.2'`/`'f3.3'`/`'plena'` (ver
    `_topes_de_fase()` para la tabla exacta). El bot NUNCA escala su
    propia fase (Clase C: editar el arranque + reiniciar, nunca desde el
    dashboard -- no hay ningún comando que la cambie, ver
    `bot/comandos.py::CLASE_A`/`CLASE_B`, que no la nombran). Al arrancar,
    si `estado.json` ya excede el tope de la fase pedida, el bot NO
    arranca (falla explícito, nunca trunca en silencio). `fase='plena'`
    reproduce el comportamiento de siempre, bit a bit -- es la que usan
    los arneses de R3 que no necesitan tope alguno.

    `descriptor_nt8` (D9 §3.5 reducida, `DECISION_CREDENCIALES_Y_FASE.md`,
    autorización R6, 22-08-2026): opcional, `None` por defecto -- el bot no
    guarda ningún secreto (las credenciales viven en NT8, ver
    `09_DESPLIEGUE.md` §3), así que esto es solo un descriptor NO secreto,
    `{'cuenta_nt8': str, 'etiqueta': 'demo'|'real'}`. `None` preserva el
    comportamiento de siempre (no se le pregunta nada a NT8 sobre su modo)
    -- deliberado, mismo principio que `topes=None`: ningún punto de llamada
    existente declara un descriptor, así que ninguno cambia. Si se pasa uno,
    al arrancar se compara lo que NT8 responde de verdad (nunca la etiqueta
    autoasignada) contra lo que la `fase` exige -- ver
    `_verifica_identidad_nt8()`.

    Devuelve el `st` final, o `None` si `estado.json` está corrupto, si
    excede el tope de fase al arrancar, o si la identidad de NT8 no
    coincide con la fase declarada (los tres casos ya reaccionados a N4
    antes de devolver)."""
    import random as _random
    import time as _time
    reloj = reloj or _time.monotonic
    dormir = dormir or _time.sleep
    topes = _topes_de_fase(fase)

    with bloqueo_proceso.adquiere(ruta_lock):
        try:
            st = estado.cargar(ruta_estado)
        except estado.EstadoInvalidoError as ex:
            SEG.reacciona_a_estado_invalido(ruta_nivel, detalle=str(ex))
            return None

        fallos_fase = estado.valida_tope_fase(st, topes)
        if fallos_fase:
            # D9 §3.2: "si estado.json ya tiene más cuentas activas que las
            # que la fase pedida permite, el arranque debe FALLAR
            # explícitamente, nunca truncar en silencio" -- misma reacción
            # que un estado corrupto (N4 + detalle), nunca una excepción
            # cruda sin contexto.
            detalle = (f"estado.json en {ruta_estado} ya excede el tope de fase={fase!r} -- "
                       f"el bot NO arranca:\n" + "\n".join(f"  - {x}" for x in fallos_fase))
            SEG.reacciona_a_estado_invalido(ruta_nivel, detalle=detalle)
            return None

        fallos_identidad = _verifica_identidad_nt8(fase, descriptor_nt8, adaptador)
        if fallos_identidad:
            # D9 §3.5 reducida: "la guarda se verifica contra la realidad, no
            # contra la etiqueta" -- si NT8 no confirma la cuenta/modo que la
            # fase declarada exige, el bot NO arranca, misma reacción N4 que
            # un estado.json corrupto o un tope de fase excedido.
            detalle = ("identidad de NT8 no coincide con fase=" + repr(fase) + " -- "
                       "el bot NO arranca:\n" + "\n".join(f"  - {x}" for x in fallos_identidad))
            SEG.reacciona_a_estado_invalido(ruta_nivel, detalle=detalle)
            return None

        if SEG.nivel_actual(ruta_nivel) in ('N3', 'N4'):
            # KILL/CONGELADO: no opera, no llama al bróker para nada más que
            # ya se haya hecho -- espera intervención humana explícita
            # (bot/seguridad.py::baja_humana).
            return st

        rec = reconciliacion.reconcilia_arranque(
            adaptador, st, cuenta_hedge_eval, cuenta_prop_eval, cuenta_hedge_funded,
            cuenta_prop_funded, instrumento_prop, ruta_nivel, ruta_ordenes,
            reloj=reloj, dormir=dormir)
        if not rec['debe_operar']:
            return st

        rng = rng or _random.Random()
        cfg = config.obtener()

        while fuente_barras.dia_disponible():
            # ORDEN_DE_TRABAJO_D9.md §3.1 -- el hueco que el comentario de
            # abajo documentaba ("cuándo exactamente" no estaba grounded)
            # ya está cerrado: si el nivel es N1/N2, se intenta la bajada
            # automática ANTES de decidir si el bucle sigue, para que un
            # "sí, ya bajó" permita procesar el día de hoy en la MISMA
            # vuelta, en vez de esperar a la siguiente invocación del
            # proceso. `verifica_reconciliado()` es de solo lectura --
            # nunca cierra nada, nunca sube de nivel; el único causante
            # que hoy escala a N1/N2 es 'reconciliacion' (ver
            # bot/seguridad.py::CAUSAS/reacciona_a_desconocido/
            # reacciona_a_liquidacion_forzosa) -- cualquier otra causa que
            # algún día llegue aquí (hoy ninguna) se trata como "no se
            # puede verificar" y nunca baja sola, la misma cautela que
            # 10_SEGURIDAD.md exige ante la duda.
            if SEG.nivel_actual(ruta_nivel) in ('N1', 'N2'):
                historial_nivel = SEG.lee_nivel(ruta_nivel).get('historial', [])
                causa_activa = historial_nivel[-1].get('causa') if historial_nivel else None
                if causa_activa == 'reconciliacion':
                    causa_sigue_activa = not reconciliacion.verifica_reconciliado(
                        adaptador, st, cuenta_hedge_eval, cuenta_prop_eval,
                        cuenta_hedge_funded, cuenta_prop_funded, instrumento_prop)
                else:
                    causa_sigue_activa = None
                SEG.intenta_bajar_automatico(ruta_nivel, st['dia_negociacion'] + 1, causa_sigue_activa)

            if SEG.nivel_actual(ruta_nivel) != 'N0':
                # cualquier nivel que siga vigente tras el intento de arriba
                # detiene el bucle -- N3/N4 nunca llegan a intentarlo
                # (intenta_bajar_automatico es no-op fuera de N1/N2), solo
                # con un humano.
                break

            ctx = fuente_barras.abre_dia()
            resuelve_eval = resuelve_funded = None   # None -> procesa_dia() usa sesion.resolver_dia
            resuelve_concurrente = None               # solo se liga en el camino EN VIVO, ver abajo
            # D9 §3.6 (autorización R6, 22-08-2026, Capa B): la lista que
            # `bot/protocolo_dos_patas.py`/`bot/resolucion_en_vivo.py` ya
            # rellenan (divergencia_fill, DIVERGENCIA_ORACULO, residuo_dia,
            # ...) se creaba y se descartaba cada día -- nunca llegaba a
            # ningún sitio porque `resuelve_concurrente` no la recibía. Se
            # crea aquí y se liga como `eventos=` en las DOS construcciones
            # de abajo; al ser una lista MUTABLE, queda rellena cuando
            # `orquestador.procesa_dia()` la use más abajo -- sin que
            # `bucle_de_tiempo.resuelve_dia_concurrente()` tenga que
            # devolverla (ver su propio comentario: "sin cambiar la firma
            # de retorno").
            eventos_hoy = []

            if ctx.direccion is not None and not ctx.resolucion_en_vivo:
                # REPLAY: todo forzado desde el pack, exactamente como hacía
                # orquestador.py::procesa_dia_replay antes de esta extracción.
                direccion = ctx.direccion
                ventana_txt = ctx.ventana_txt
                b0v = cfg.sesion.cal_rth.b0_rth.valor() if ventana_txt == "RTH" else 0
                ph, pl, pc = calendario.refleja_camino(ctx.ph, ctx.pl, ctx.pc, direccion)
                n_resets_hoy = ctx.n_resets_hoy
            elif ctx.direccion is not None and ctx.resolucion_en_vivo:
                # LA PUERTA GRANDE (ORDEN_DE_TRABAJO_D8.md §4): dirección,
                # ventana y resets FORZADOS desde el pack -- "igual que hace
                # el contrato del replay" -- pero resueltos "por el bucle en
                # vivo" (D8.2/D8.3/D8.5 de verdad, bar a bar, vía el mismo
                # bucle de tiempo compartido que usa producción). Tercer
                # modo del contrato de `ContextoDia` -- ver su docstring.
                direccion = ctx.direccion
                ventana_txt = ctx.ventana_txt
                b0v = cfg.sesion.cal_rth.b0_rth.valor() if ventana_txt == "RTH" else 0
                n_resets_hoy = ctx.n_resets_hoy
                ph = pl = pc = resolucion_en_vivo.CAMINO_NO_USADO_EN_VIVO

                dia_de_hoy = st["dia_negociacion"] + 1
                resuelve_concurrente = partial(
                    bucle_de_tiempo.resuelve_dia_concurrente,
                    adaptador=adaptador, fuente_barras=fuente_barras,
                    cuenta_hedge_eval=cuenta_hedge_eval, cuenta_prop_eval=cuenta_prop_eval,
                    cuenta_hedge_funded=cuenta_hedge_funded, cuenta_prop_funded=cuenta_prop_funded,
                    instrumento_prop=instrumento_prop, ruta_ordenes=ruta_ordenes,
                    ruta_nivel=ruta_nivel, dia_negociacion=dia_de_hoy, eventos=eventos_hoy,
                    reloj=reloj, dormir=dormir)
            else:
                # EN VIVO: se sortea de verdad. La dirección de HOY sale de
                # contra_pendiente YA ACTUALIZADO por procesa_dia() de AYER
                # (rearmado si ayer murió alguna cuenta, decrementado si no)
                # -- NO se vuelve a llamar calendario.sortea_direccion() aquí
                # (eso RECALCULARÍA contra_pendiente una segunda vez sobre el
                # mismo tránsito de día, doble contabilidad). Con el contador
                # ya en cero, hoy es un sorteo fresco 50/50 (R-6.1); si no,
                # hoy repite la dirección de ayer (regla CONTRA).
                if st["contra_pendiente"] > 0:
                    direccion = st["direccion"]
                else:
                    direccion = 1 if rng.random() < 0.5 else -1
                es_dia_de_dato = rng.random() < cfg.sesion.cal_rth.frac_dias_dato.valor()
                ventana_txt, b0v = calendario.ventana_del_dia(es_dia_de_dato)
                p_reset = cfg.proveedor.reset_prob_diaria.valor()
                n_resets_hoy = sum(1 for _ in range(st["pool"]["rotas"]) if rng.random() < p_reset)
                ph = pl = pc = resolucion_en_vivo.CAMINO_NO_USADO_EN_VIVO

                # D8.4 reestructuración (RESPUESTA_D8_CONCURRENCIA.md §3):
                # funded y eval se resuelven JUNTAS, por el bucle de tiempo
                # compartido -- un ResuelveDiaEnVivo por slot (bloqueante,
                # cada uno dueño de su propio cursor de fuente_barras) haría
                # que la segunda en llamarse esperase a que la primera
                # acabase su día entero, si las dos están activas el mismo
                # día (medido: 222/504 días del pack, 44 %).
                dia_de_hoy = st["dia_negociacion"] + 1
                resuelve_concurrente = partial(
                    bucle_de_tiempo.resuelve_dia_concurrente,
                    adaptador=adaptador, fuente_barras=fuente_barras,
                    cuenta_hedge_eval=cuenta_hedge_eval, cuenta_prop_eval=cuenta_prop_eval,
                    cuenta_hedge_funded=cuenta_hedge_funded, cuenta_prop_funded=cuenta_prop_funded,
                    instrumento_prop=instrumento_prop, ruta_ordenes=ruta_ordenes,
                    ruta_nivel=ruta_nivel, dia_negociacion=dia_de_hoy, eventos=eventos_hoy,
                    reloj=reloj, dormir=dormir)

            st, fin_de_dia, diario = orquestador.procesa_dia(
                st, direccion, ventana_txt, ph, pl, pc, b0v, n_resets_hoy,
                resuelve_dia_eval=resuelve_eval, resuelve_dia_funded=resuelve_funded,
                modo_auto_confirma=modo_auto_confirma, resuelve_concurrente=resuelve_concurrente,
                topes=topes)

            if dir_residuo is not None and resuelve_concurrente is not None:
                _escribe_eventos_residuo(dir_residuo, st["dia_negociacion"], eventos_hoy)

            # DECISION_DEGRADACION_N3.md (revisión operador 21-08-2026): la
            # degradación (R-7.2) es pegajosa -- nunca se revierte sola -- así
            # que la única salida real es PARAR (N3, "humano, explícito").
            # Evaluada CADA día (no solo el día del cruce): `sube_a()` es
            # monótono/idempotente, así que si un humano bajase el nivel a
            # mano con `degradado` todavía `True`, el bucle vuelve a subirlo
            # a N3 solo, al día siguiente -- sin esto la barrera sería
            # decorativa. Va DESPUÉS del bloque de tesorería (que ya corrió,
            # dentro de `procesa_dia()`) -- el día de hoy ya está cerrado y
            # el bot ya está PLANO; la única decisión real es si abre mañana
            # (la comprueba el `while` de arriba, en la vuelta siguiente).
            if st['degradado']:
                SEG.reacciona_a_degradacion_tesoreria(ruta_nivel, st['dia_negociacion'],
                                                       st['dia_degradacion'])

            _, checksum_actual = config.cargar()
            fallos = estado.validar(st, checksum_actual)
            if fallos:
                raise estado.EstadoInvalidoError(
                    "dia " + str(st['dia_negociacion']) + ": invariante roto tras procesar el dia:\n"
                    + "\n".join(f"  - {x}" for x in fallos))

            estado.guardar(st, ruta_estado)
            estado.guarda_instantanea(st, dir_instantaneas, st["dia_negociacion"], dias_retenidos)
            _escribe_linea_diario(ruta_diario, diario)
            fuente_barras.cierra_dia()

        return st
