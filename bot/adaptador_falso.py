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

    def _nueva_orden(self, tipo, cuenta, instrumento, direccion, cantidad, comportamiento):
        oid = f"FAKE-{next(self._contador)}"
        self.ordenes[oid] = dict(
            order_id=oid, tipo=tipo, cuenta=cuenta, instrumento=instrumento,
            direccion=direccion, cantidad=cantidad, estado='ENVIADA',
            cantidad_llenada=0.0, precio_medio=None,
            ts_creacion=self.reloj(), cancelacion_pedida=False,
        )
        comp = dict(comportamiento or {})
        comp.setdefault('fill_en_s', self.FILL_EN_S_POR_DEFECTO)
        self._comportamiento[oid] = comp
        self.eventos.append(('CREADA', oid, tipo, cuenta, instrumento, direccion, cantidad))
        return oid

    def cancelar(self, order_id):
        """§4: 'solo aplica a órdenes no llenas'. `comportamiento['en_cancelar']`
        (un callable `hook(adaptador, orden)`) decide la carrera
        cancelar-vs-fill -- así se fabrica a propósito el escenario que
        07_ADAPTADOR_NT8.md §5.3 (revisión 2) tiene que resolver bien: si el
        hook no está, la cancelación es limpia (gana el cancelar)."""
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
        return o['estado']

    def leer_estado_orden(self, order_id):
        o = self.ordenes[order_id]
        self._avanza(o)
        return o['estado']

    def leer_fill(self, order_id):
        o = self.ordenes[order_id]
        self._avanza(o)
        return o['estado'] == 'LLENA', o['cantidad_llenada'], o['precio_medio']

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
        clave = (o['cuenta'], o['instrumento'])
        self.posiciones[clave] = self.posiciones.get(clave, 0) + o['direccion'] * o['cantidad']
        self.eventos.append(('LLENA', o['order_id'], self.posiciones[clave]))
