# -*- coding: utf-8 -*-
"""apoyo_pasada2.py · SOLO verificacion_R3/, NUNCA bot/ (R1/R6)

Apoyo de la Pasada 2 de LA PUERTA GRANDE (ANALISIS_PUERTA_GRANDE.md §4):
el ruido de ejecución, anclado y barrido, nunca inventado.

REVISIÓN DE DISEÑO (21-08-2026) -- por qué esto NO fabrica una desviación
de PRECIO de fill en el adaptador (como hacía un primer intento descartado
aquí mismo): el propio §4 confirma, leyendo `bot/detector_en_vivo.py`, que
`slip_usd_micro` "se aplica solo en la salida por muerte y solo sobre la
pata del hedge" -- es decir, sobre `hedge_dolares` (`h`), JAMÁS sobre
`dx_puntos` (que es lo que alimenta `eval.bal`/`funded.bal`, R-2.x). Un
experimento decisivo (ver el diagnóstico de esta sesión, no incluido aquí)
lo confirma empíricamente: variar SOLO `slip_usd_micro` (0 vs el valor de
`03_CONFIG.yaml`) sobre el mismo subconjunto de 30 días deja `eval.bal`/
`funded.bal` BIT A BIT idénticos día a día, y `caja` cae de forma limpia,
monótona y aditiva (ver `verificacion_R3/prueba_pasada2_ruido.py`, parte
0). En cambio, fabricar la desviación en el PRECIO DE FILL reportado por
el adaptador (`AdaptadorReplaySobrePack`, que es lo que alimenta
`dx_real` -- ver `bot/resolucion_en_vivo.py::leer_fill`/`_refleja_escalar`)
SÍ cambia `dx_puntos`, y por tanto SÍ cambia `bal` -- lo cual encadena
efectos de estado (pool/relevo/sizing del día siguiente) que NADA tienen
que ver con "cuánto cuesta un fill peor", y que rompen por completo la
premisa aditiva/lineal de la predicción pre-registrada del operador (676
$ por 1 $/micro). Esa vía quedó descartada -- `apoyo_puerta_grande.py` se
revirtió a su estado limpio, sin ningún parámetro de ruido.

En vez de eso, `con_ruido_ejecucion()` GENERALIZA el mismo canal ya usado
por `slip_usd_micro`, aplicado exactamente en el mismo punto y con la
misma garantía de aislamiento (nunca toca `dx_puntos`/`bal`/`pool`/
`muere` -- solo el `$` que ya fluye, aislado, hacia `caja`):

1. **Salida de muerte** (`ruido_muerte_ticks`): reemplaza el campo
   `deslizamiento` que ya devuelven `arma_intento_eval`/
   `arma_intento_funded`/`arma_empalme_eval` (`bot/ciclo_vida.py`,
   `deslizamiento=slip_usd_micro*m`) por `ruido_muerte_ticks * tick_usd *
   m` -- el MISMO canal, camino y garantía de aislamiento que
   `slip_usd_micro` ya tiene hoy (verificado arriba), solo con la
   magnitud viniendo de un barrido en ticks en vez del dato fijo de
   `03_CONFIG.yaml`. Con `ruido_muerte_ticks` = 2,50/1,25 = 2 (el ancla),
   esto reproduce EXACTAMENTE lo que `slip_usd_micro` ya hace -- por
   construcción, no por coincidencia (§4b). REGLA DE NO DOBLE COBRO
   (§4a): al REEMPLAZAR el campo (nunca sumar encima), el `slip_usd_micro`
   analítico de `03_CONFIG.yaml` quede automáticamente fuera de la cuenta
   en cuanto este gestor está activo -- no hace falta un segundo mecanismo
   para "apagarlo".

2. **Fills normales** (`ruido_normal_ticks`, entrada/objetivo/campana --
   "lo que hoy NO está modelado", §4): `_cierra()`
   (`bot/detector_en_vivo.py`) recalcula `h`/`dx_puntos`/`fric` de CERO
   cada día que un intento se resuelve -- incluida la campana, que cierra
   Y reabre la posición cada día (aplanar()+abrir() frescos) -- así que
   CADA día resuelto sin muerte es, económicamente, un ida-y-vuelta
   completo, exactamente como un día CON muerte lo es. No existe hoy un
   knob para esto (el `if muere: h -= deslizamiento` de `_cierra` nunca
   se ejecuta si no hay muerte) -- así que en vez de fabricar un campo
   `bot/` no ofrece, este gestor envuelve `ciclo_vida.cierra_resolucion_eval`/
   `cierra_resolucion_funded` (los DOS puntos donde `dia["hedge_dolares"]`
   entra a `caja_delta`, `bot/ciclo_vida.py:231,524`) y, SOLO cuando
   `dia['muere']` es False, resta `ruido_normal_ticks * tick_usd * m` del
   `caja_delta` YA CALCULADO por la función original -- de nuevo: nunca
   toca `eval_estado`/`funded_estado`/`pool_estado`, solo ajusta el
   `caja_delta` de salida, exactamente el mismo principio de
   observar/ajustar usado en toda esta sesión."""
import inspect
from contextlib import contextmanager

from bot import ciclo_vida as CV
from bot import config


def _tick_usd():
    return config.obtener().hedge_broker.tick_usd.valor()


def _con_deslizamiento_de_ticks(fn, ruido_muerte_ticks):
    """Envuelve arma_intento_eval/arma_intento_funded/arma_empalme_eval --
    reemplaza `deslizamiento` (presente en el dict devuelto SOLO cuando el
    intento arranca de verdad, `arranca=True` o funded siempre) por
    `ruido_muerte_ticks * tick_usd * m` -- mismo `m` que la función
    original ya calculó para ESE intento (eval=2/funded=4, `03_CONFIG.yaml`
    `sizing.m_eval`/`sizing.m_fun`, nunca reinventado aquí)."""
    def _envoltorio(*a, **kw):
        r = fn(*a, **kw)
        if isinstance(r, dict) and 'deslizamiento' in r and 'm' in r:
            r = dict(r, deslizamiento=ruido_muerte_ticks * _tick_usd() * r['m'])
        return r
    return _envoltorio


def _indice_de(fn, nombre):
    """Posición (0-based) del parámetro `nombre` en la firma de `fn` --
    para leer `dia`/`m_eval`/`m_fun` de una llamada posicional sin
    hardcodear el índice (bot/bucle_de_tiempo.py llama a las dos
    `cierra_resolucion_*` siempre por posición, nunca por palabra clave)."""
    return list(inspect.signature(fn).parameters).index(nombre)


def _con_ruido_normal_en_cierre(fn, indice_dia, indice_m, ruido_normal_ticks):
    """Envuelve cierra_resolucion_eval/cierra_resolucion_funded -- tras
    llamar a la función original (que ya actualizó `bal`/`pool`/`eventos`
    con el `dia` SIN tocar), si ESE `dia` no fue una muerte, resta el
    coste de ruido normal del `caja_delta` YA devuelto -- nunca antes de
    llamar (para que la función original calcule con el `dia` intacto)."""
    def _envoltorio(*a, **kw):
        r = fn(*a, **kw)
        dia = a[indice_dia] if indice_dia < len(a) else kw.get('dia')
        m = a[indice_m] if indice_m < len(a) else None
        if dia is not None and not dia['muere'] and ruido_normal_ticks and m is not None:
            r = dict(r, caja_delta=r['caja_delta'] - ruido_normal_ticks * _tick_usd() * m)
        return r
    return _envoltorio


@contextmanager
def con_ruido_ejecucion(ruido_normal_ticks=0.0, ruido_muerte_ticks=0.0):
    """Gestor único de la Pasada 2 -- activa los dos ejes del barrido del
    operador (§4b) a la vez, cada uno por su canal aislado propio (ver
    docstring del módulo). `ruido_muerte_ticks=0` dentro de este gestor
    reproduce exactamente `sin_deslizamiento_analitico()` (deslizamiento
    puesto a 0); `ruido_muerte_ticks=2` reproduce exactamente el
    `slip_usd_micro` de `03_CONFIG.yaml` sin activar este gestor en
    absoluto (2 * 1,25 = 2,50 = slip_usd_micro -- el ancla, §4b) -- ambos
    son el mismo mecanismo, nunca dos mecanismos que puedan sumarse."""
    orig_eval = CV.arma_intento_eval
    orig_funded = CV.arma_intento_funded
    orig_empalme = CV.arma_empalme_eval
    orig_cierra_eval = CV.cierra_resolucion_eval
    orig_cierra_funded = CV.cierra_resolucion_funded

    ix_dia_eval = _indice_de(orig_cierra_eval, 'dia')
    ix_m_eval = _indice_de(orig_cierra_eval, 'm_eval')
    ix_dia_fun = _indice_de(orig_cierra_funded, 'dia')
    ix_m_fun = _indice_de(orig_cierra_funded, 'm_fun')

    CV.arma_intento_eval = _con_deslizamiento_de_ticks(orig_eval, ruido_muerte_ticks)
    CV.arma_intento_funded = _con_deslizamiento_de_ticks(orig_funded, ruido_muerte_ticks)
    CV.arma_empalme_eval = _con_deslizamiento_de_ticks(orig_empalme, ruido_muerte_ticks)
    CV.cierra_resolucion_eval = _con_ruido_normal_en_cierre(
        orig_cierra_eval, ix_dia_eval, ix_m_eval, ruido_normal_ticks)
    CV.cierra_resolucion_funded = _con_ruido_normal_en_cierre(
        orig_cierra_funded, ix_dia_fun, ix_m_fun, ruido_normal_ticks)
    try:
        yield
    finally:
        CV.arma_intento_eval = orig_eval
        CV.arma_intento_funded = orig_funded
        CV.arma_empalme_eval = orig_empalme
        CV.cierra_resolucion_eval = orig_cierra_eval
        CV.cierra_resolucion_funded = orig_cierra_funded


@contextmanager
def sin_deslizamiento_analitico():
    """Caso particular de `con_ruido_ejecucion()` -- solo pone
    `deslizamiento` a 0 (ruido_muerte_ticks=0, ruido_normal_ticks=0),
    conservado como herramienta suelta para otras verificaciones que
    solo necesiten "apagar el deslizamiento analítico", sin barrer nada."""
    with con_ruido_ejecucion(ruido_normal_ticks=0.0, ruido_muerte_ticks=0.0):
        yield


def _cuenta(fn, m_fijo, contador):
    def _envoltorio(*a, **kw):
        r = fn(*a, **kw)
        ix_dia = _indice_de(fn, 'dia')
        dia = a[ix_dia] if ix_dia < len(a) else kw.get('dia')
        contador['micros_totales'] += m_fijo
        if dia['muere']:
            contador['micros_muerte'] += m_fijo
        else:
            contador['micros_sin_muerte'] += m_fijo
        return r
    return _envoltorio


@contextmanager
def censo_micro_sesiones(contador):
    """Cuenta, directo de la corrida (nunca a mano, R2), cuántas
    micro-sesiones (cada resolución de `cierra_resolucion_eval`/
    `cierra_resolucion_funded`, contada por su propio `m`, no por
    llamada) hay en total y cuántas son sin muerte -- la base del factor
    de conversión `spr_usd` <-> `desviacion_fill_normal_usd_tick`
    (REVISION_D8_S5_PASADA2.md §2.1: 1 tick del eje nuevo equivale a
    `micros_sin_muerte / micros_totales` veces `tick_usd` $/micro de
    `spr_usd`). `contador` es un dict con claves `micros_totales`,
    `micros_muerte`, `micros_sin_muerte` -- inicializado a 0 por el
    llamador, relleno aquí. Puramente observador -- nunca cambia
    `caja_delta` ni ningún otro resultado (a diferencia de
    `con_ruido_ejecucion()`, con el que se puede combinar sin
    interferir: cada uno envuelve una capa distinta)."""
    orig_eval = CV.cierra_resolucion_eval
    orig_funded = CV.cierra_resolucion_funded
    m_eval = config.obtener().sizing.m_eval.valor()
    m_fun = config.obtener().sizing.m_fun.valor()
    CV.cierra_resolucion_eval = _cuenta(orig_eval, m_eval, contador)
    CV.cierra_resolucion_funded = _cuenta(orig_funded, m_fun, contador)
    try:
        yield
    finally:
        CV.cierra_resolucion_eval = orig_eval
        CV.cierra_resolucion_funded = orig_funded
