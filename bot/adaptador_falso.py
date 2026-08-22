# -*- coding: utf-8 -*-
"""adaptador_falso.py · D-C · 05_ORDEN_DE_CONSTRUCCION.md

El "adaptador falso" que 08_LABORATORIO.md §8 (comprobaciones 6-12) y
`DATOS_Y_DASHBOARD.md` Parte 4 piden para poder demostrar el protocolo de
las dos patas y el comando de pánico SIN NT8. NO ES NT8: es un simulador en
memoria del puerto que define `07_ADAPTADOR_NT8.md` §1 (`abrir`, `aplanar`,
`cancelar`, `leer_estado_orden`, `leer_fill`, `leer_posicion`,
`hay_conexion`, `leer_cuenta`, `arrancar`/`parar`) y de la máquina de
estados de una orden (§4): `ENVIADA → ACEPTADA → {LLENA, PARCIAL→LLENA,
CANCELADA}` / `ENVIADA → RECHAZADA`.

`bot/protocolo_dos_patas.py` (que sí es el código de producción, reusable
cuando exista el adaptador NT8 real de D-A) no importa nada de este fichero
ni sabe que existe -- solo ve el puerto. Este simulador existe para poder
FABRICAR a propósito, de forma determinista y sin esperar segundos reales,
los escenarios que R3 exige poner a prueba: el timeout de `N`/`N_hedge`, la
carrera cancelar-vs-fill de §5.3, y el cierre que no confirma a la primera
de §5.4 (comprobación 11 de `08_LABORATORIO.md` §8, la del botón de pánico).

PROHIBIDO (mismo principio que el resto de `bot/`): este módulo no decide
nada de negocio -- no sabe qué es `k`, `m`, `s0`, ni por qué se abre o se
cierra una pata. Solo simula cómo se comporta UN bróker frente a órdenes,
con el comportamiento que cada prueba le pida explícitamente.
"""
import itertools


class AdaptadorFalso:
    """Simulador de pruebas del puerto de 07_ADAPTADOR_NT8.md §1.

    Comportamiento por defecto (sin configurar nada): toda orden que se abre
    se ACEPTA de inmediato y se LLENA en el siguiente sondeo -- el "camino
    feliz", para que una prueba que no está fabricando a propósito un
    escenario roto no tenga que configurar nada. Para fabricar un escenario
    distinto (timeout, carrera cancelar-vs-fill, cierre que no confirma a la
    primera) se usa `comportamiento=` al llamar a `abrir()`/`aplanar()` --
    p.ej. `fill_en_s=999` para que NUNCA llene dentro de un timeout de
    prueba -- o se pre-programa con `programa_aplanar()` las reaperturas
    del cierre (§5.4).

    `rechaza_aplanar_cantidad_cero` (DEFECTO 3, revisión operador 20-08-2026):
    por defecto `False` -- el simulador, complaciente, aceptaba un `aplanar()`
    sobre una cuenta YA plana como si fuera una orden normal. Un bróker real
    es probable que rechace una orden de cantidad cero. Con este modo en
    `True`, cualquier `aplanar()` sobre una posición ya en cero se crea
    directamente `RECHAZADA` -- para comprobar que `protocolo_dos_patas.py`
    nunca llega a mandarla (`_aplana_hasta_confirmar` comprueba la posición
    ANTES de aplanar, ver su docstring): "un simulador que solo simula el
    caso amable no sirve de red".
    """
    FILL_EN_S_POR_DEFECTO = 0.0

    def __init__(self, reloj=None, rechaza_aplanar_cantidad_cero=False):
        import time
        self.reloj = reloj or time.monotonic
        self.rechaza_aplanar_cantidad_cero = rechaza_aplanar_cantidad_cero
        self.ordenes = {}
        self._contador = itertools.count(1)
        self.posiciones = {}          # (cuenta, instrumento) -> cantidad neta firmada
        self.conexiones = {}          # cuenta -> bool; ausente = conectada
        self._comportamiento = {}     # order_id -> dict
        self._plan_aplanar = {}       # (cuenta, instrumento) -> lista de resultados por intento
        self._proximo_comportamiento = {}  # (cuenta, instrumento) -> dict, para la PROXIMA abrir()
        self.eventos = []             # log crudo, solo para diagnostico/pruebas
        self._grupos_oco = {}         # id_grupo_oco -> (order_id_stop, order_id_limite)
        self._contador_oco = itertools.count(1)

    def programa_abrir(self, cuenta, instrumento, **comportamiento):
        """Pre-registra el `comportamiento` (fill_en_s / en_cancelar / rechazar /
        precio_fill) que tomará la PRÓXIMA orden que `abrir()` cree sobre
        (cuenta, instrumento) -- así se fabrica un timeout de N/N_hedge o una
        carrera cancelar-vs-fill SIN que `protocolo_dos_patas.py` (código de
        producción) tenga que saber que existe este mecanismo de prueba: él
        solo llama a `abrir(cuenta, instrumento, direccion, cantidad)`, tal
        cual especifica el puerto de 07_ADAPTADOR_NT8.md §1."""
        self._proximo_comportamiento[(cuenta, instrumento)] = dict(comportamiento)

    # --- ciclo de vida del puente (07_ADAPTADOR_NT8.md §1, arrancar/parar) --
    def arrancar(self):
        return True

    def parar(self):
        return True

    def hay_conexion(self, cuenta):
        return self.conexiones.get(cuenta, True)

    def desconecta(self, cuenta):
        """Ayuda de pruebas: simula 'Connected(cuenta) = falso' (07_ADAPTADOR_NT8.md §7)."""
        self.conexiones[cuenta] = False

    def leer_cuenta(self, cuenta):
        return dict(caja=0.0, pnl_realizado=0.0, poder_de_compra=1e9)

    # --- órdenes -------------------------------------------------------
    def abrir(self, cuenta, instrumento, direccion, cantidad, comportamiento=None):
        clave = (cuenta, instrumento)
        pre = self._proximo_comportamiento.pop(clave, None)
        if pre is not None:
            comportamiento = {**pre, **(comportamiento or {})}
        return self._nueva_orden('abrir', cuenta, instrumento, direccion, cantidad, comportamiento)

    def programa_aplanar(self, cuenta, instrumento, resultados):
        """Pre-programa el RESULTADO de cada intento sucesivo de aplanar()
        sobre (cuenta, instrumento) -- p.ej. ['CANCELADA', 'RECHAZADA', 'LLENA']
        simula que el cierre de una pata no confirma a la primera (§5.4:
        'SE REINTENTA el cierre'). Si se agota la lista, el resultado por
        defecto para los intentos siguientes es 'LLENA' (converge, no cuelga
        la prueba indefinidamente)."""
        self._plan_aplanar[(cuenta, instrumento)] = list(resultados)

    def aplanar(self, cuenta, instrumento, comportamiento=None):
        clave = (cuenta, instrumento)
        plan = self._plan_aplanar.get(clave)
        if plan:
            resultado = plan.pop(0)
            pos = self.posiciones.get(clave, 0)
            direccion = -1 if pos > 0 else (1 if pos < 0 else 0)
            cantidad = abs(pos)
            oid = self._nueva_orden('aplanar', cuenta, instrumento, direccion, cantidad, None)
            o = self.ordenes[oid]
            o['estado'] = 'ACEPTADA'
            if resultado == 'LLENA':
                self._llena(o)
            else:
                o['estado'] = resultado
            self.eventos.append(('APLANAR_PROGRAMADO', oid, resultado))
            return oid
        pos = self.posiciones.get(clave, 0)
        direccion = -1 if pos > 0 else (1 if pos < 0 else 0)
        cantidad = abs(pos)
        if cantidad == 0 and self.rechaza_aplanar_cantidad_cero:
            # DEFECTO 3: un broker real puede rechazar una orden de cantidad
            # cero -- este modo lo simula, para comprobar que quien nos llama
            # nunca deberia llegar aqui con la posicion ya plana.
            comportamiento = {**(comportamiento or {}), 'rechazar': True}
        return self._nueva_orden('aplanar', cuenta, instrumento, direccion, cantidad, comportamiento)

    def _nueva_orden(self, tipo, cuenta, instrumento, direccion, cantidad, comportamiento,
                      estilo='MERCADO', precio=None, grupo_oco=None):
        oid = f"FAKE-{next(self._contador)}"
        self.ordenes[oid] = dict(
            order_id=oid, tipo=tipo, cuenta=cuenta, instrumento=instrumento,
            direccion=direccion, cantidad=cantidad, estado='ENVIADA',
            cantidad_llenada=0.0, precio_medio=None,
            ts_creacion=self.reloj(), cancelacion_pedida=False,
            # D8.2 (ORDEN_DE_TRABAJO_D8.md §1): estilo/precio/grupo_oco son
            # aditivos -- toda orden previa (abrir/aplanar, sin bracket)
            # sigue con estilo='MERCADO', precio=None, grupo_oco=None,
            # exactamente como antes de que existiera coloca_bracket().
            estilo=estilo, precio=precio, grupo_oco=grupo_oco,
        )
        comp = dict(comportamiento or {})
        comp.setdefault('fill_en_s', self.FILL_EN_S_POR_DEFECTO)
        self._comportamiento[oid] = comp
        self.eventos.append(('CREADA', oid, tipo, cuenta, instrumento, direccion, cantidad))
        return oid

    # --- D8.2: órdenes en reposo (bracket OCO) --------------------------
    def coloca_bracket(self, cuenta, instrumento, direccion_cierre, cantidad,
                        precio_stop, precio_limite):
        """ORDEN_DE_TRABAJO_D8.md §1 (D8.2): coloca, en una sola llamada, las
        DOS patas EN REPOSO -- stop en el suelo, límite en el objetivo --
        agrupadas en un grupo OCO. `precio_stop`/`precio_limite` vienen ya
        resueltos de `sizing.py::plan()` (p0-ndn, p0+nu) -- esta operación
        no calcula ni valida esos números, solo los coloca (mismo principio
        que el resto del puerto: "el adaptador nunca decide cuándo ni
        cuánto").

        A diferencia de `abrir()`/`aplanar()` (que llenan solas al primer
        sondeo, comportamiento por defecto pensado para el camino feliz),
        las dos patas de un bracket NUNCA auto-llenan por temporización
        (`fill_en_s=None`): este simulador no modela una trayectoria de
        precio real, así que una pata en reposo se queda viva hasta que una
        prueba resuelve explícitamente cuál "toca precio" -- ver
        `fabrica_resolucion_bracket()`.

        Devuelve {order_id_stop, order_id_limite, id_grupo_oco} -- la única
        operación del puerto que devuelve un diccionario en vez de un
        `order_id` único, porque coloca DOS órdenes de una vez."""
        grupo = f"OCO-{next(self._contador_oco)}"
        oid_stop = self._nueva_orden('bracket_stop', cuenta, instrumento, direccion_cierre,
                                      cantidad, {'fill_en_s': None}, estilo='STOP',
                                      precio=precio_stop, grupo_oco=grupo)
        oid_lim = self._nueva_orden('bracket_limite', cuenta, instrumento, direccion_cierre,
                                     cantidad, {'fill_en_s': None}, estilo='LIMITE',
                                     precio=precio_limite, grupo_oco=grupo)
        self._grupos_oco[grupo] = (oid_stop, oid_lim)
        self.eventos.append(('BRACKET_COLOCADO', grupo, oid_stop, oid_lim))
        return dict(order_id_stop=oid_stop, order_id_limite=oid_lim, id_grupo_oco=grupo)

    def fabrica_resolucion_bracket(self, id_grupo_oco, pierna, precio_fill=None):
        """SOLO PRUEBAS -- fabrica a propósito qué pata "toca precio":
        `pierna` ∈ {'stop', 'limite'}. La pata objetivo se llena (vía
        `_llena()`, que auto-cancela la hermana -- ver más abajo).
        `precio_fill=None` llena EXACTAMENTE al nivel pedido (pass 1 de la
        puerta grande, ORDEN_DE_TRABAJO_D8.md §4: fills perfectos, sin
        deslizamiento); un `precio_fill` explícito fabrica deslizamiento
        (pass 2)."""
        oid_stop, oid_lim = self._grupos_oco[id_grupo_oco]
        oid_objetivo = oid_stop if pierna == 'stop' else oid_lim
        o = self.ordenes[oid_objetivo]
        precio = precio_fill if precio_fill is not None else o['precio']
        self._llena(o, precio=precio)

    def fabrica_doble_fill_bracket(self, id_grupo_oco, precio_fill_stop=None, precio_fill_limite=None):
        """SOLO PRUEBAS -- fabrica el caso residual que 10_SEGURIDAD.md y el
        pedido de trabajo D8 reconocen como posible con un OCO real
        imperfecto: AMBAS patas llegan a LLENA. Deliberadamente NO pasa por
        `_llena()` (que auto-cancelaría la hermana) -- rellena las dos a
        mano, sin autocancelación cruzada, para darle a D8 un caso real que
        ejercitar en su rama de incidente. No representa el comportamiento
        normal del simulador (que sí mantiene el OCO); solo existe para
        fabricar el escenario a propósito."""
        oid_stop, oid_lim = self._grupos_oco[id_grupo_oco]
        for oid, precio_fill in ((oid_stop, precio_fill_stop), (oid_lim, precio_fill_limite)):
            o = self.ordenes[oid]
            o['estado'] = 'LLENA'
            o['cantidad_llenada'] = o['cantidad']
            o['precio_medio'] = precio_fill if precio_fill is not None else o['precio']
            clave = (o['cuenta'], o['instrumento'])
            self.posiciones[clave] = self.posiciones.get(clave, 0) + o['direccion'] * o['cantidad']
            self.eventos.append(('LLENA_SIN_AUTOCANCELAR_OCO', oid))

    def cancelar(self, order_id):
        """§4: 'solo aplica a órdenes no llenas'. `comportamiento['en_cancelar']`
        (un callable `hook(adaptador, orden)`) decide la carrera
        cancelar-vs-fill -- así se fabrica a propósito el escenario que
        07_ADAPTADOR_NT8.md §5.3 (revisión 2) tiene que resolver bien: si el
        hook no está, la cancelación es limpia (gana el cancelar).

        Idempotente y veraz (D8.2, ORDEN_DE_TRABAJO_D8.md §1): si `order_id`
        ya está `LLENA`, esto devuelve `LLENA` -- NUNCA fabrica `CANCELADA`
        sobre una orden que de hecho se ejecutó (ya era así antes de D8.2,
        se deja documentado aquí porque D8.2 depende de esta garantía).

        Grupo OCO: si `order_id` pertenece a un grupo colocado por
        `coloca_bracket()`, cancelar CUALQUIERA de las dos patas cancela el
        GRUPO COMPLETO -- nunca deja una pata huérfana viva. Una pata ya
        `LLENA` del grupo nunca se toca (ni se pisa su estado ni se re-
        cancela)."""
        o = self.ordenes[order_id]
        self._avanza(o)
        if o['estado'] in ('LLENA', 'CANCELADA', 'RECHAZADA'):
            self.eventos.append(('CANCELAR_NOOP_YA_TERMINAL', order_id, o['estado']))
            return o['estado']
        o['cancelacion_pedida'] = True
        hook = self._comportamiento[order_id].get('en_cancelar')
        if hook is not None:
            hook(self, o)
        else:
            o['estado'] = 'CANCELADA'
        self.eventos.append(('CANCELAR_PEDIDO', order_id, o['estado']))
        grupo = o.get('grupo_oco')
        if grupo is not None:
            for oid_hermano in self._grupos_oco.get(grupo, ()):
                if oid_hermano == order_id:
                    continue
                hermano = self.ordenes[oid_hermano]
                self._avanza(hermano)
                if hermano['estado'] not in ('LLENA', 'CANCELADA', 'RECHAZADA'):
                    hermano['estado'] = 'CANCELADA'
                    hermano['cancelacion_pedida'] = True
                    self.eventos.append(('CANCELAR_PEDIDO_GRUPO_OCO', oid_hermano, 'CANCELADA'))
        return o['estado']

    def leer_estado_orden(self, order_id):
        o = self.ordenes[order_id]
        self._avanza(o)
        return o['estado']

    def leer_fill(self, order_id):
        o = self.ordenes[order_id]
        self._avanza(o)
        return o['estado'] == 'LLENA', o['cantidad_llenada'], o['precio_medio']

    def leer_fill_detalle(self, order_id):
        """07_ADAPTADOR_NT8.md §1 (D9 §3.4/3.6 fusionadas, autorización R6):
        la cadena de trazabilidad completa de UNA orden -- la que hace falta
        para poder distinguir "el precio se movió" (deslizamiento) de "la
        noticia llegó tarde" (retraso), que `leer_fill()` por sí solo no
        puede separar. Aditivo: `leer_fill()` NO se toca (ver docstring de
        más arriba), este es un método nuevo del puerto, no un reemplazo.

        Devuelve un dict con `feed_origen`, `ts_orden`, `ts_fill_broker`,
        `ts_fill_recibido` -- y `ts_feed` (aquí SIEMPRE `None`: este
        simulador no modela un feed de mercado independiente del propio
        bróker, solo el ciclo de vida de una orden). La regla que hace esto
        compatible con R2 (sin excepciones, revisión operador): un campo
        que este adaptador NO PUEDA dar de verdad es `None` con su propio
        `..._motivo` explícito -- nunca un valor sustituido, nunca una
        estimación, nunca este mismo reloj haciéndose pasar por el reloj
        del feed o del bróker. El adaptador NT8 real, cuando exista, deberá
        cumplir el mismo contrato (documentado en 07_ADAPTADOR_NT8.md §1) --
        con motivos distintos si a él SÍ le falta algún campo por otra
        razón (p.ej. la ATI no expone el timestamp del feed)."""
        o = self.ordenes[order_id]
        self._avanza(o)
        llena = o['estado'] == 'LLENA'
        return dict(
            feed_origen=o['cuenta'],
            ts_feed=None,
            ts_feed_motivo='adaptador_falso_no_simula_feed_de_mercado_independiente',
            ts_orden=o['ts_creacion'],
            ts_fill_broker=(o.get('ts_fill') if llena else None),
            ts_fill_broker_motivo=(None if llena else 'orden_todavia_no_llena'),
            ts_fill_recibido=(self.reloj() if llena else None),
            ts_fill_recibido_motivo=(None if llena else 'orden_todavia_no_llena'),
        )

    def leer_posicion(self, cuenta, instrumento):
        cantidad = self.posiciones.get((cuenta, instrumento), 0)
        return cantidad, (100.0 if cantidad else None)

    def fuerza_fill(self, order_id, precio=100.0):
        """Ayuda de pruebas para usar DENTRO de un hook `en_cancelar`: fabrica
        a propósito 'la cancelación llegó tarde, el fill ganó la carrera'."""
        self._llena(self.ordenes[order_id], precio=precio)

    def fuerza_posicion_externa(self, cuenta, instrumento, cantidad):
        """Ayuda de pruebas (D8.3, pedido de trabajo D8 §1, 10_SEGURIDAD.md §7
        hueco 1): fabrica 'el proveedor liquidó la posición por su cuenta' --
        cambia `self.posiciones` DIRECTAMENTE, sin pasar por ninguna orden.
        A diferencia de `fuerza_fill` (que resuelve una orden YA EN VUELO),
        esto simula un movimiento de posición que no tiene ningún `order_id`
        que lo explique -- exactamente la señal que
        `bot/deteccion_liquidacion.py::detecta_liquidacion_forzosa()` tiene
        que cazar: `leer_posicion()` cambia sin que ninguna orden propia
        conocida esté en estado LLENA."""
        self.posiciones[(cuenta, instrumento)] = cantidad
        self.eventos.append(('POSICION_FORZADA_EXTERNA', cuenta, instrumento, cantidad))

    def _avanza(self, o):
        if o['estado'] in ('LLENA', 'CANCELADA', 'RECHAZADA'):
            return
        comp = self._comportamiento[o['order_id']]
        if comp.get('rechazar'):
            o['estado'] = 'RECHAZADA'
            self.eventos.append(('RECHAZADA', o['order_id']))
            return
        if o['estado'] == 'ENVIADA':
            o['estado'] = 'ACEPTADA'
        fill_en_s = comp.get('fill_en_s')
        if (fill_en_s is not None and not o['cancelacion_pedida']
                and (self.reloj() - o['ts_creacion']) >= fill_en_s):
            self._llena(o)

    def _llena(self, o, precio=100.0):
        o['estado'] = 'LLENA'
        o['cantidad_llenada'] = o['cantidad']
        o['precio_medio'] = self._comportamiento.get(o['order_id'], {}).get('precio_fill', precio)
        # D9 §3.4/3.6 fusionadas: `ts_fill` es "según el bróker" -- en este
        # simulador el único reloj que existe es el suyo, así que este es el
        # instante más fiel posible (un adaptador NT8 real lo sacaría del
        # propio evento de ejecución de la ATI, no de este reloj). Ver
        # `leer_fill_detalle()`.
        o['ts_fill'] = self.reloj()
        clave = (o['cuenta'], o['instrumento'])
        self.posiciones[clave] = self.posiciones.get(clave, 0) + o['direccion'] * o['cantidad']
        self.eventos.append(('LLENA', o['order_id'], self.posiciones[clave]))
        # D8.2: si esta orden pertenece a un grupo OCO, la hermana se
        # auto-cancela SOLA en cuanto esta llena -- sin que el llamador
        # tenga que pedirlo. `cancelar()` desde D8 sobre la hermana sigue
        # siendo una defensa idempotente barata (no hace nada si ya llegó
        # aquí primero), nunca el mecanismo primario.
        grupo = o.get('grupo_oco')
        if grupo is not None:
            for oid_hermano in self._grupos_oco.get(grupo, ()):
                if oid_hermano == o['order_id']:
                    continue
                hermano = self.ordenes[oid_hermano]
                if hermano['estado'] not in ('LLENA', 'CANCELADA', 'RECHAZADA'):
                    hermano['estado'] = 'CANCELADA'
                    hermano['cancelacion_pedida'] = True
                    self.eventos.append(('CANCELADA_OCO_AUTOMATICA', oid_hermano, o['order_id']))
