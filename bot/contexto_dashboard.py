# -*- coding: utf-8 -*-
"""contexto_dashboard.py · D-C · 08_LABORATORIO.md §6

Construye el `ctx` que `bot/dashboard.py::genera_html()` pinta, A PARTIR de
`estado.json`, el diario del orquestador y (si existen) los ficheros del
laboratorio -- "se genera desde los ficheros del laboratorio y el diario del
orquestador, sin inventar ninguna fuente nueva" (§6.1). Este módulo SÍ
decide cómo agregar/derivar (p. ej. la tasa mensual de E6), pero nunca
inventa un dato que no esté ya en alguna de esas fuentes o en
`03_CONFIG.yaml`.

CERRADO 20-08-2026 (RECOMENDACIÓN 2, revisión del operador sobre D-C): el
diario de `bot/orquestador.py` separaba "muertes de fondeada" pero no
"muertes de eval" -- el bloque 6 (MODELO vs REALIDAD) publicaba esa fila
como "no trackeado todavía". `ciclo_vida.py::procesa_dia_eval` ya emite
`eventos['muertes_eval']` (contador nuevo, incrementado en los dos puntos de
muerte de una eval -- intento inicial y empalme) y `orquestador.py` lo
acumula en el diario igual que los demás contadores -- re-verificado que el
replay de 504 días con `desviaciones_activas=[]` sigue dando exactamente
504 días · 0 fallos · caja final 29.134,87 $ tras el cableado (el contador
es una adición pura, nunca comparada por `tests/runner_replay_v10.py`).
"""
from bot import config, comandos, seguridad, tesoreria


def _agrega_eventos(historial_diario):
    # `muertes_eval` (RECOMENDACIÓN 2, revisión del operador 20-08-2026): el
    # diario de `bot/orquestador.py` ya trae este contador desde que
    # `ciclo_vida.py::procesa_dia_eval` lo emite -- se agrega igual que los
    # demás, con `.get(k, 0)` cubriendo diarios viejos (de antes de esta
    # revisión) que todavía no lo traían.
    total = dict(intentos=0, aprobaciones=0, muertes_funded=0, muertes_eval=0,
                 resets=0, emergencias=0, recompras=0)
    for d in historial_diario:
        ev = d.get('eventos', {})
        for k in total:
            total[k] += ev.get(k, 0)
    return total, len(historial_diario)


def construye(estado, diario_hoy, historial_diario, ahora_iso=None, ahora_monotono=0.0,
              mercado_snapshots=None, incidencias_recientes=None, incidencias_contadores=None,
              cifras_citadas=None, pendientes_extra=None, nivel_registro=None,
              identidad_nt8=None):
    """`estado`: el dict de estado.json (ya cargado). `diario_hoy`: la línea
    de diario del día actual (o None si no ha corrido ningún día todavía).
    `historial_diario`: lista de líneas de diario (para E6/bloque 6) -- en
    la prueba de D-C esto es el diario de los 504 días del replay; en
    producción, el diario real acumulado hasta hoy.

    `nivel_registro` (DECISION_DEGRADACION_N3.md §3/§5, test 5: "que la
    causa tipada llega al panel y se pinta"): el dict que devuelve
    `bot/seguridad.py::lee_nivel(ruta_nivel)` (o `None` si quien llama
    todavía no lo ha leído -- este módulo NUNCA lee ficheros él mismo, ver
    docstring de arriba) -- mismo principio que `mercado_snapshots`/
    `incidencias_recientes`: datos YA cargados, nunca una ruta.

    `identidad_nt8` (D9 §3.5 reducida, `DECISION_CREDENCIALES_Y_FASE.md`,
    autorización R6, 22-08-2026): `{'cuenta': str|None, 'modo':
    'SIMULADA'|'REAL'|None, 'fase': str|None}`, ya resuelto por quien llama
    (mismo principio que `nivel_registro`: este módulo no le pregunta nada a
    NT8 él mismo). `None` -- el valor por defecto, y el que siguen usando
    todos los llamadores de antes de este cambio -- pinta la banda como "no
    declarado", nunca inventa un valor."""
    cfg = config.obtener()
    rancio_seg = cfg.dashboard.rancio_seg.valor()
    dias_por_mes = cfg.tesoreria.dias_por_mes.valor()
    mercado_snapshots = mercado_snapshots or []
    incidencias_recientes = incidencias_recientes or []
    incidencias_contadores = incidencias_contadores or {}
    pendientes_extra = pendientes_extra or []
    nivel_registro = nivel_registro or seguridad.nivel_de_fabrica()

    direccion = diario_hoy['direccion'] if diario_hoy else estado.get('direccion', 1)
    ventana = diario_hoy['ventana'] if diario_hoy else '—'

    # --- bloque 1: AHORA -------------------------------------------------
    patas = []
    if estado['eval']['activa']:
        patas.append(dict(cuenta='eval', tipo='k', cantidad=None))
    if estado['funded']['activa']:
        patas.append(dict(cuenta='fondeada', tipo='k', cantidad=None))
    ultimo_snap = mercado_snapshots[-1] if mercado_snapshots else None
    conexiones = [
        dict(nombre='hedge (AMP/CQG)', hay_conexion=True,
             estado_feed=(ultimo_snap['estado_feed'] if ultimo_snap else 'DESCONOCIDO')),
        dict(nombre='prop (MFF/Tradovate)', hay_conexion=True, estado_feed='DESCONOCIDO'),
    ]
    nivel_hoy = nivel_registro.get('nivel', 'N0')
    historial_nivel = nivel_registro.get('historial', [])
    ultima_transicion = historial_nivel[-1] if historial_nivel else None
    contencion = dict(
        nivel=nivel_hoy, nombre=seguridad.NOMBRES.get(nivel_hoy, nivel_hoy),
        causa=(ultima_transicion or {}).get('causa'), motivo=(ultima_transicion or {}).get('motivo'),
        quien=(ultima_transicion or {}).get('quien'),
    )
    ahora_block = dict(
        direccion=direccion, ventana=ventana, barra_actual=None,
        patas=patas, conexiones=conexiones,
        # DECISION_DEGRADACION_N3.md §3: "una sola escalera" -- el semáforo
        # global ahora refleja el nivel N0-N4 de verdad (antes solo miraba
        # `degradado`, que es una de las CAUSAS posibles, no la única).
        semaforo_global=('bien' if nivel_hoy == 'N0'
                          else ('critico' if nivel_hoy in ('N3', 'N4') else 'grave')),
        contencion=contencion,
    )

    # --- bloque 2: RIESGO --------------------------------------------------
    m_eval_hoy = cfg.sizing.m_eval.valor() if estado['eval']['activa'] else 0.0
    exp_eval_hoy = cfg.sizing.exp_eval_usd.valor() if estado['eval']['activa'] else 0.0
    muro = tesoreria.muro_dinamico(m_eval_hoy, exp_eval_hoy)
    riesgo = dict(
        caja=estado['caja'], retirado=estado['retirado'], muro=muro,
        distancia_degradacion=(estado['caja'] - estado['retirado']) + muro,
        degradado=estado['degradado'],
    )

    # --- bloque 3: PENDIENTES DEL HUMANO ------------------------------------
    # DOS RELOJES DISTINTOS (03_CONFIG.yaml §10, corregido 20-08-2026 tras la
    # revision del operador sobre D-C: "5 dias" y "~7 dias" NO son la misma
    # cifra citada dos veces -- son dos eventos distintos y hay que mostrar
    # los DOS, no fundirlos en uno). Para cada pendiente que trae
    # `dias_esperando` (una cuenta bloqueada esperando intervencion humana):
    #   - reloj del BOT: `dias_esperando` contra `bloqueada_escalada_dias`
    #     (cuando el propio bot sube el aviso a un canal mas ruidoso) --
    #     ya lo pintaba dashboard.py antes de esta revision.
    #   - reloj del PROVEEDOR (nuevo): cuanto le queda antes de que
    #     MyFundedFutures mate la cuenta por inactividad -- `SUPUESTO`,
    #     con la virgulilla de su propia fuente (01_ESPECIFICACION_E2E.md
    #     R-2.4), nunca se disimula como si fuera DADO.
    escalada_dias = cfg.alertas.bloqueada_escalada_dias.valor()
    proveedor_dias = cfg.alertas.proveedor_mata_cuenta_dias.valor()
    pendientes = []
    for it in list(estado.get('pendientes_humano', [])) + pendientes_extra:
        it = dict(it)
        if 'dias_esperando' in it:
            it.setdefault('umbral_escalada_dias', escalada_dias)
            it.setdefault('proveedor_mata_cuenta_dias', proveedor_dias)
            it.setdefault('dias_hasta_proveedor_mata',
                          max(0, proveedor_dias - it['dias_esperando']))
        pendientes.append(it)

    # --- bloque 4: CUENTAS ---------------------------------------------------
    cuentas = dict(
        eval={k: v for k, v in estado['eval'].items()},
        funded={k: v for k, v in estado['funded'].items()},
        recamara=estado['recamara'],
        pool=estado['pool'],
    )

    # --- bloque 5: MERCADO Y FRICCIÓN -----------------------------------------
    disponible = False
    motivo = "sin snapshots de mercado todavía (D-A/rama B no corriendo)"
    friccion_optimista = friccion_realista = horquilla_actual = None
    if ultimo_snap is not None:
        estado_feed = ultimo_snap.get('estado_feed', 'DESCONOCIDO')
        if estado_feed != 'TIEMPO_REAL':
            motivo = f"feed retrasado (estado_feed={estado_feed})"
        else:
            valor_punto = cfg.hedge_broker.valor_punto_usd.valor()
            comision_rt = cfg.hedge_broker.comision_rt_usd.valor()
            horquilla_actual = (ultimo_snap['ask'] - ultimo_snap['bid']) * valor_punto
            friccion_optimista = comision_rt + 1 * horquilla_actual
            friccion_realista = comision_rt + 2 * horquilla_actual
            disponible = True
    mercado = dict(disponible=disponible, motivo_no_disponible=motivo,
                    horquilla_actual=horquilla_actual,
                    friccion_optimista=friccion_optimista, friccion_realista=friccion_realista,
                    # §6.1: "todo número lleva su frescura" -- se pasa el ts_monotono del
                    # snapshot que alimentó E1 para que dashboard.py pinte vivo/rancio.
                    ts_monotono=(ultimo_snap['ts_monotono'] if ultimo_snap else None))

    # --- bloque 6: MODELO vs REALIDAD (E6, 08_LABORATORIO.md §3) --------------
    agregados, dias_operados = _agrega_eventos(historial_diario)
    tasas_esperadas = (cifras_citadas or {}).get('tasas_evento_mes', {})
    modelo_vs_realidad = []
    # claves EXACTAS de modelo/cifras_citadas.json:tasas_evento_mes (verificado
    # contra el fichero real -- no son las etiquetas de la tabla "bonita" de
    # 08_LABORATORIO.md §3, que usa nombres para humanos distintos de las claves).
    mapa_nombres = dict(intentos=('intentos de eval', 'intentos_eval'),
                         aprobaciones=('aprobaciones', 'aprobaciones'),
                         muertes_funded=('muertes de fondeada', 'muertes_funded'),
                         muertes_eval=('muertes de eval', 'muertes_eval'),
                         emergencias=('emergencias', 'emergencias'),
                         recompras=('recompras', 'recompras'),
                         resets=('resets gratis', 'resets_gratis'))
    for clave, (nombre, clave_json) in mapa_nombres.items():
        n = agregados[clave]
        tasa_obs = (n / dias_operados * dias_por_mes) if dias_operados else 0.0
        ref = tasas_esperadas.get(clave_json, {})
        modelo_vs_realidad.append(dict(
            evento=nombre, tasa_observada=tasa_obs, n=n,
            tasa_esperada=ref.get('por_mes'), sd=ref.get('sd'),
            concluye=(n >= 25),   # 08_LABORATORIO.md §5: ±20% de precision, referencia de "empieza a significar algo"
        ))

    # --- bloque 7: LABORATORIO -------------------------------------------------
    laboratorio = [
        dict(nombre='E1', n=0, intervalo='—', estado='sin datos de papel', n_minimo=None),
        dict(nombre='E2', n=0, intervalo='—', estado='sin datos de papel', n_minimo=1000),
        dict(nombre='E3', n=0, intervalo='—', estado='sin datos de papel', n_minimo=None),
        dict(nombre='E4', n=0, intervalo='—', estado='sin datos de papel', n_minimo=None),
        dict(nombre='E5', n=sum(incidencias_contadores.values()), intervalo='—',
             estado='diagnóstico, sin n mínimo', n_minimo=None),
        dict(nombre='E6', n=dias_operados, intervalo='±dias', estado='acumulando',
             n_minimo=25),
    ]

    incidencias = dict(ultimas=incidencias_recientes, contadores=incidencias_contadores)

    # --- banda de identidad (D9 §3.5 reducida) ------------------------------
    identidad = dict(cuenta=None, modo=None, fase=None)
    identidad.update(identidad_nt8 or {})

    return dict(
        generado_ts=ahora_iso or '—', ahora_monotono=ahora_monotono, rancio_seg=rancio_seg,
        ahora=ahora_block, riesgo=riesgo, pendientes=pendientes, cuentas=cuentas,
        mercado_friccion=mercado, modelo_vs_realidad=modelo_vs_realidad,
        laboratorio=laboratorio, incidencias=incidencias,
        desviaciones_activas=estado.get('desviaciones_activas', []),
        identidad=identidad,
    )
