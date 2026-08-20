# -*- coding: utf-8 -*-
"""resolucion_en_vivo.py · D8.4 · ORDEN_DE_TRABAJO_D8.md §0-§1 · diseño
arquitectónico grounded (panel de ángulos + síntesis, 20-08-2026)

La pieza que sustituye a `sesion.resolver_dia` en el camino EN VIVO,
inyectada vía el parámetro `resuelve_dia` que ganaron
`ciclo_vida.procesa_dia_eval`/`procesa_dia_funded`. `bot/sesion.py` NO se
toca (R6) -- esto es una reimplementación INDEPENDIENTE, verificada por
equivalencia contra el oráculo, mismo patrón que
`bot/detector_en_vivo.py` (0 discrepancias sobre 902 estados reales +
1.500 sintéticos).

Este fichero, en su primera pieza (la única construida hasta ahora), solo
contiene la aritmética de reflexión dirección-corta -- réplica ESCALAR de
`calendario.refleja_camino` pero anclada en `p0_real` (el precio de fill
real de la entrada) en vez de `pc_crudo[0]` (el cierre crudo de la barra
0, que en vivo no existe como tal sin una llamada extra al adaptador).

Verificado matemáticamente (la síntesis del diseño, y el test de
equivalencia de abajo): la reflexión es afín (`x -> 2*A - x`), y TODA la
aritmética de R-3/`DetectorEnVivo` solo usa diferencias respecto al
ancla -- nunca el valor absoluto -- así que cualquier ancla sirve; usar
`p0_real` (que YA se tiene, sin llamada adicional al adaptador) es
estrictamente más simple."""


def _refleja_escalar(x, p0_real, direccion):
    """Réplica ESCALAR, a propósito, de `calendario.refleja_camino`
    (mismo `x -> 2*A - x` si la dirección es corta, identidad si es
    larga) pero con `A = p0_real` en vez de `pc_crudo[0]` -- verificado
    matemáticamente equivalente para toda diferencia respecto a `p0`
    (que es todo lo que R-3/`DetectorEnVivo` usan; ver
    `verificacion_R3/prueba_reflexion_en_vivo.py`)."""
    return x if direccion >= 0 else 2.0 * p0_real - x


def _refleja_bar(ph_b, pl_b, pc_b, p0_real, direccion):
    """Réplica de `calendario.refleja_camino` aplicada a UNA barra --
    incluido el intercambio alto↔bajo que la reflexión exige (el máximo
    reflejado sale del MÍNIMO crudo, y viceversa): imprescindible para
    alimentar `DetectorEnVivo`, que espera el camino YA reflejado, tal
    como lo ve `sesion.resolver_dia` en el camino de replay."""
    if direccion >= 0:
        return ph_b, pl_b, pc_b
    return (2.0 * p0_real - pl_b,   # el máximo reflejado sale del MÍNIMO crudo
            2.0 * p0_real - ph_b,   # y viceversa
            2.0 * p0_real - pc_b)


class _CentinelaCaminoNoUsado:
    """Se pasa como `ph`/`pl`/`pc` a `procesa_dia_eval`/`procesa_dia_funded`
    cuando `resuelve_dia` es un `ResuelveDiaEnVivo` -- `ciclo_vida.py`
    NUNCA debería indexar `ph`/`pl`/`pc` en modo vivo (es el único módulo
    del repo donde esos tres nombres aparecen exclusivamente como
    argumentos de reenvío hacia `resuelve_dia`, nunca indexados
    directamente). Si algún cambio futuro a `ciclo_vida.py` empezara a
    indexarlos, esto falla RUIDOSO (`AssertionError` nombrando la
    invariante rota) en vez de silenciosamente (un `TypeError` genérico
    sobre `None`, o peor, un `IndexError` sin contexto)."""

    def __len__(self):
        raise AssertionError(
            "ciclo_vida.py indexó ph/pl/pc en modo vivo -- invariante rota, ese módulo "
            "solo debe REENVIAR estos argumentos a resuelve_dia, nunca leerlos (D8.4)")

    def __getitem__(self, i):
        raise AssertionError(
            "ciclo_vida.py indexó ph/pl/pc en modo vivo -- invariante rota, ese módulo "
            "solo debe REENVIAR estos argumentos a resuelve_dia, nunca leerlos (D8.4)")

    def __repr__(self):
        return "CAMINO_NO_USADO_EN_VIVO"


CAMINO_NO_USADO_EN_VIVO = _CentinelaCaminoNoUsado()


import itertools
import time

from bot import config, deteccion_liquidacion, idempotencia_ordenes as IO
from bot import protocolo_dos_patas as DP
from bot import seguridad as SEG
from bot.detector_en_vivo import DetectorEnVivo


class ResuelveDiaEnVivo:
    """La pieza que `ciclo_vida.procesa_dia_eval`/`procesa_dia_funded`
    invocan en vez de `sesion.resolver_dia` cuando `bot/bucle_del_dia.py`
    (D8.4) corre en vivo -- MISMA firma posicional/keyword que
    `sesion.resolver_dia`, pero en vez de barrer un array de barras ya
    conocido: abre las dos patas (D-C), coloca el bracket en reposo
    (D8.2), vigila con sondeo real (D8.3 incluido), y resuelve al fill
    real -- nunca a un nivel teórico.

    `ph`/`pl`/`pc`/`barra_inicio` que `ciclo_vida.py` reenvía se IGNORAN a
    propósito (son `CAMINO_NO_USADO_EN_VIVO`/0 en modo vivo, ver
    `bot/bucle_del_dia.py`) -- el `p0` real sale del fill de la propia
    apertura, nunca de un array.

    Una instancia se construye UNA VEZ por (día, slot) y se reutiliza para
    las dos posibles llamadas de `procesa_dia_eval` (intento 0 y empalme)
    -- `self._intento` distingue las dos en el `intent_id` de D8.5 y en
    los eventos, sin que ningún estado se filtre entre ellas (verificado
    en R3, prueba de reentrancia)."""

    _CONTADOR_GLOBAL = itertools.count(1)   # desambigua id_grupo_oco entre instancias en pruebas

    def __init__(self, adaptador, cuenta_hedge, cuenta_prop, instrumento_prop, direccion,
                 fuente_barras, ruta_ordenes, ruta_nivel, slot, dia_negociacion,
                 eventos=None, reloj=None, dormir=None):
        self.adaptador = adaptador
        self.cuenta_hedge = cuenta_hedge
        self.cuenta_prop = cuenta_prop
        self.instrumento_prop = instrumento_prop
        self.direccion = direccion
        self.fuente_barras = fuente_barras
        self.ruta_ordenes = ruta_ordenes
        self.ruta_nivel = ruta_nivel
        self.slot = slot
        self.dia_negociacion = dia_negociacion
        self.eventos = eventos if eventos is not None else []
        self.reloj = reloj or time.monotonic
        self.dormir = dormir or time.sleep
        self._intento = 0

    def _intent_id(self, fase):
        return f"{self.dia_negociacion}:{self.slot}:{self._intento}:{fase}"

    def __call__(self, ph, pl, pc, barra_inicio, plan_resultado, m, fric, deslizamiento=0.0,
                 redondea=False):
        cfg = config.obtener()
        valor_punto = cfg.hedge_broker.valor_punto_usd.valor()
        MES = cfg.hedge_broker.instrumento

        # 1. bloqueo (R-2.4): ni siquiera se llama al adaptador -- misma
        #    semántica que resolver_dia(bloq=True), sin gastar una orden real.
        if plan_resultado['bloqueo']:
            self._intento += 1
            return dict(dx_puntos=0.0, hedge_dolares=0.0, comision=0.0, muere=False,
                        pausa=False, objetivo=False, barra_evento=barra_inicio)

        # 2. D8.5: abre las dos patas -- NO idempotente, se protege con testigo
        #    intención/resultado (nunca se reintenta a ciegas; ver docstring de
        #    idempotencia_ordenes.py).
        intent_abre = self._intent_id('abre')
        apertura = IO.resultado_de(self.ruta_ordenes, intent_abre)
        if apertura is None:
            IO.escribe_intencion(self.ruta_ordenes, intent_abre,
                                  dict(cuenta_hedge=self.cuenta_hedge, cuenta_prop=self.cuenta_prop,
                                       instrumento_prop=self.instrumento_prop,
                                       direccion=self.direccion, m=m, k=plan_resultado['k']))
            apertura = DP.abre_las_dos_patas(
                self.adaptador, self.cuenta_hedge, self.cuenta_prop, self.instrumento_prop,
                self.direccion, m, plan_resultado['k'], eventos=self.eventos,
                reloj=self.reloj, dormir=self.dormir)
            IO.marca_resultado(self.ruta_ordenes, intent_abre, apertura)

        if not apertura.get('abierto'):
            # DECISIÓN DE INGENIERÍA (no un caso que sesion.resolver_dia
            # contemple -- el replay siempre asume entrada exitosa, R-3.1):
            # una apertura fallida (rechazo limpio, timeout N/N_hedge --
            # protocolo_dos_patas.py ya deja las dos cuentas confirmadas
            # planas en todos esos casos) se trata como "no pasó nada hoy",
            # mismo dict cero que el bloqueo -- el slot sigue activo,
            # ciclo_vida.py lo reintentará el día siguiente. Se anota el
            # evento para que sea visible, nunca se oculta.
            self.eventos.append(dict(tipo='ENTRADA_FALLIDA_DIA_VACIO', slot=self.slot,
                                      motivo=apertura.get('motivo')))
            self._intento += 1
            return dict(dx_puntos=0.0, hedge_dolares=0.0, comision=0.0, muere=False,
                        pausa=False, objetivo=False, barra_evento=barra_inicio)

        # 3. p0 real -- el fill de la propia apertura, nunca un array.
        _, _, p0_real = self.adaptador.leer_fill(apertura['order_id_prop'])

        # 4. D8.2: coloca el bracket en reposo -- protegido igual que la apertura.
        ndn, nu = plan_resultado['ndn'], plan_resultado['nu']
        precio_stop_real = _refleja_escalar(p0_real - ndn, p0_real, self.direccion)
        precio_limite_real = _refleja_escalar(p0_real + nu, p0_real, self.direccion)
        intent_bracket = self._intent_id('bracket')
        bracket = IO.resultado_de(self.ruta_ordenes, intent_bracket)
        if bracket is None:
            IO.escribe_intencion(self.ruta_ordenes, intent_bracket,
                                  dict(precio_stop=precio_stop_real, precio_limite=precio_limite_real))
            bracket = self.adaptador.coloca_bracket(
                self.cuenta_prop, self.instrumento_prop, direccion_cierre=-self.direccion,
                cantidad=plan_resultado['k'], precio_stop=precio_stop_real,
                precio_limite=precio_limite_real)
            IO.marca_resultado(self.ruta_ordenes, intent_bracket, bracket)
        oid_stop, oid_lim = bracket['order_id_stop'], bracket['order_id_limite']

        # 5. DetectorEnVivo: SOLO diagnóstico (reloj de sesión + oráculo de
        #    divergencia) -- interfaz y lógica SIN TOCAR (R6, ya congelado en
        #    la revisión de 07_ADAPTADOR_NT8.md).
        det = DetectorEnVivo(p0=p0_real, ndn=ndn, nu=nu, m=m, fric=fric,
                              deslizamiento=deslizamiento, valor_punto=valor_punto,
                              k=plan_resultado['k'], cst=plan_resultado['comision'],
                              Mm=plan_resultado['Mm'], bloqueado=False)

        # 6. vigilancia: D8.3 (liquidación forzosa) + sondeo del bracket +
        #    reloj de sesión (barras reales, para diagnóstico y para saber
        #    cuándo tocó campana).
        ganadora = None
        barra_actual = barra_inicio
        while True:
            if deteccion_liquidacion.detecta_liquidacion_forzosa(
                    self.adaptador, self.cuenta_prop, self.instrumento_prop,
                    cantidad_esperada=plan_resultado['k'],
                    ordenes_propias_conocidas=[oid_stop, oid_lim]):
                r = deteccion_liquidacion.resuelve_liquidacion_forzosa(
                    self.adaptador, self.cuenta_hedge, MES, eventos=self.eventos,
                    reloj=self.reloj, dormir=self.dormir)
                SEG.reacciona_a_liquidacion_forzosa(self.ruta_nivel, detalle=str(r))
                self._intento += 1
                return dict(dx_puntos=0.0, hedge_dolares=0.0, comision=plan_resultado['comision'],
                            muere=True, pausa=False, objetivo=False, barra_evento=barra_actual)

            barra = self.fuente_barras.siguiente_barra()
            # R-3.2 (misma disciplina que resolver_dia/DetectorEnVivo: "nunca
            # se evalúa la propia barra de entrada"): una fuente compartida
            # entre varias resoluciones del mismo día (empalme) o reconstruida
            # desde el principio (arneses de prueba) puede servir barras con
            # índice <= barra_inicio -- esas se IGNORAN a propósito, nunca
            # alimentan el detector ni cuentan como "campana".
            barra_usable = barra is not None and barra.b > barra_inicio
            if barra_usable:
                barra_actual = barra.b
                phr, plr, pcr = _refleja_bar(barra.ph, barra.pl, barra.pc, p0_real, self.direccion)
                det.alimenta_barra(barra.b, phr, plr, pcr, barra.es_ultima_barra_operable)

            est_stop = self.adaptador.leer_estado_orden(oid_stop)
            est_lim = self.adaptador.leer_estado_orden(oid_lim)
            if est_stop == 'LLENA':
                ganadora = 'stop'
                break
            if est_lim == 'LLENA':
                ganadora = 'limite'
                break
            if barra is None or (barra_usable and barra.es_ultima_barra_operable):
                # ninguna pata llenó antes de la campana -- cancela el grupo
                # y cierra a mercado (mismo camino que el modelo, "ninguno toca").
                self.adaptador.cancelar(oid_stop)   # cancela el grupo completo (D8.2)
                # Se cierra la prop A MANO primero (en vez de dejárselo entero a
                # cierra_las_dos_patas) SOLO para poder capturar el order_id de la
                # orden de cierre y leer su precio real -- cierra_las_dos_patas()
                # no devuelve ese order_id (ver DP._aplana_hasta_confirmar: solo
                # da (confirmado, intentos)). Es inofensivo: aplanar() es
                # idempotente por construcción, así que cuando
                # cierra_las_dos_patas() llegue a su propio paso de "cerrar la
                # prop" la encontrará YA plana (cantidad=0) y ese paso será un
                # no-op -- cierra_las_dos_patas sigue siendo la única que de
                # verdad cierra el hedge, sin duplicar lógica de reintento aquí.
                oid_cierre_prop = self.adaptador.aplanar(self.cuenta_prop, self.instrumento_prop)
                DP._poll_hasta(self.adaptador, oid_cierre_prop, DP.ESTADOS_TERMINALES, None,
                                self.reloj, self.dormir)
                _, _, precio_cierre_real = self.adaptador.leer_fill(oid_cierre_prop)
                DP.cierra_las_dos_patas(self.adaptador, self.cuenta_prop, self.instrumento_prop,
                                         self.cuenta_hedge, eventos=self.eventos, reloj=self.reloj,
                                         dormir=self.dormir)
                dx_real = _refleja_escalar(precio_cierre_real, p0_real, self.direccion) - p0_real
                resultado = self._resuelve_con_formula(det, plan_resultado['k'], dx_real,
                                                        low=False, tgt=False,
                                                        barra_evento=barra_actual)
                self._registra_divergencia(det, dx_real)
                self._intento += 1
                return resultado
            self.dormir(0.0)   # cede el hilo; en vivo, fuente_barras es quien de verdad espera

        # 7. una pata llenó -- cancela la hermana (defensa idempotente de
        #    respaldo, D8.2 síntesis: "D8 vigila igualmente y cancela por su
        #    cuenta") y cierra SOLO el hedge (la prop ya se cerró sola).
        oid_ganadora = oid_stop if ganadora == 'stop' else oid_lim
        oid_perdedora = oid_lim if ganadora == 'stop' else oid_stop
        self.adaptador.cancelar(oid_perdedora)
        _, _, precio_fill_real = self.adaptador.leer_fill(oid_ganadora)
        dx_real = _refleja_escalar(precio_fill_real, p0_real, self.direccion) - p0_real
        DP._aplana_hasta_confirmar(self.adaptador, self.cuenta_hedge, MES, self.reloj,
                                    self.dormir, self.eventos, 'hedge_tras_bracket_en_vivo')
        resultado = self._resuelve_con_formula(det, plan_resultado['k'], dx_real,
                                                low=(ganadora == 'stop'),
                                                tgt=(ganadora == 'limite'), barra_evento=barra_actual)
        self._registra_divergencia(det, dx_real)
        self._intento += 1
        return resultado

    def _resuelve_con_formula(self, det_diagnostico, k, dx_real, low, tgt, barra_evento):
        """Reutiliza la fórmula EXACTA de R-3.4/R-3.5 (muere/pausa/hedge_dolares)
        de `DetectorEnVivo._cierra` -- NUNCA reimplementada aparte -- pero
        aplicada al `dx_real` observado, vía una instancia SEPARADA (no
        `det_diagnostico`, que se queda con su propio resultado teórico
        derivado de las barras, para poder compararlo después). `k` se pasa
        explícito (el mismo `plan_resultado['k']` de la llamada) en vez de
        reconstruirlo desde `det_diagnostico.pv / valor_punto` -- evita un
        redondeo de coma flotante innecesario en una división que ya se
        conoce exacta."""
        det_calculo = DetectorEnVivo(
            p0=det_diagnostico.p0, ndn=det_diagnostico.ndn, nu=det_diagnostico.nu,
            m=det_diagnostico.m, fric=det_diagnostico.fric,
            deslizamiento=det_diagnostico.deslizamiento, valor_punto=det_diagnostico.valor_punto,
            k=k, cst=det_diagnostico.cst, Mm=det_diagnostico.Mm, bloqueado=False)
        det_calculo._cierra(dx_real, low=low, tgt=tgt, barra_evento=barra_evento)
        return det_calculo.resultado

    def _registra_divergencia(self, det_diagnostico, dx_real):
        """8. Oráculo de diagnóstico -- compara lo que el detector, alimentado
        SOLO con barras, habría predicho contra el dx REAL observado. NUNCA
        decide bookkeeping -- solo loguea."""
        if det_diagnostico.resuelto:
            dx_teorico = det_diagnostico.resultado['dx_puntos']
            if abs(dx_teorico - dx_real) > 1e-6:
                self.eventos.append(dict(tipo='DIVERGENCIA_ORACULO', slot=self.slot,
                                          dx_teorico=dx_teorico, dx_real=dx_real,
                                          diferencia=dx_real - dx_teorico))
