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


def bucle_del_dia(fuente_barras, adaptador,
                   cuenta_hedge_eval, cuenta_prop_eval, cuenta_hedge_funded, cuenta_prop_funded,
                   instrumento_prop, ruta_estado, ruta_nivel, ruta_ordenes, ruta_lock,
                   dir_instantaneas, dias_retenidos, ruta_diario,
                   modo_auto_confirma=True, rng=None, reloj=None, dormir=None):
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

    Devuelve el `st` final, o `None` si `estado.json` está corrupto (ya
    reaccionado a N4 antes de devolver)."""
    import random as _random
    import time as _time
    reloj = reloj or _time.monotonic
    dormir = dormir or _time.sleep

    with bloqueo_proceso.adquiere(ruta_lock):
        try:
            st = estado.cargar(ruta_estado)
        except estado.EstadoInvalidoError as ex:
            SEG.reacciona_a_estado_invalido(ruta_nivel, detalle=str(ex))
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
            if SEG.nivel_actual(ruta_nivel) != 'N0':
                # cualquier nivel de degradación detiene el bucle -- N1/N2 se
                # desescalan solos en otro punto (seguridad.baja_automatica,
                # ver ORDEN_DE_TRABAJO_D8.md §5, hueco documentado: "cuándo
                # exactamente" no está grounded en este diseño); N3/N4 solo
                # con un humano.
                break

            ctx = fuente_barras.abre_dia()
            resuelve_eval = resuelve_funded = None   # None -> procesa_dia() usa sesion.resolver_dia
            resuelve_concurrente = None               # solo se liga en el camino EN VIVO, ver abajo

            if ctx.direccion is not None:
                # REPLAY: todo forzado desde el pack, exactamente como hacía
                # orquestador.py::procesa_dia_replay antes de esta extracción.
                direccion = ctx.direccion
                ventana_txt = ctx.ventana_txt
                b0v = cfg.sesion.cal_rth.b0_rth.valor() if ventana_txt == "RTH" else 0
                ph, pl, pc = calendario.refleja_camino(ctx.ph, ctx.pl, ctx.pc, direccion)
                n_resets_hoy = ctx.n_resets_hoy
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
                    ruta_nivel=ruta_nivel, dia_negociacion=dia_de_hoy, reloj=reloj, dormir=dormir)

            st, fin_de_dia, diario = orquestador.procesa_dia(
                st, direccion, ventana_txt, ph, pl, pc, b0v, n_resets_hoy,
                resuelve_dia_eval=resuelve_eval, resuelve_dia_funded=resuelve_funded,
                modo_auto_confirma=modo_auto_confirma, resuelve_concurrente=resuelve_concurrente)

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
