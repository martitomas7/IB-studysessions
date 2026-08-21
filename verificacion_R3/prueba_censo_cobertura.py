# -*- coding: utf-8 -*-
"""censo_cobertura.py · D8, ANALISIS_PUERTA_GRANDE.md §3/§6

"Un gate en verde sobre un camino con cobertura 0 no es información."
Este script instrumenta `orquestador.corre_replay()` sobre
`tests/replay_v10.json` (504 días) y cuenta, para CADA camino de negocio
relevante, cuántas veces lo ejercita el pack de verdad -- sin adivinar,
sin reconstruir a mano: contadores puestos directamente sobre las
funciones reales de `bot/ciclo_vida.py`/`bot/calendario.py` (R2/R3).

Se corre como PARTE de la regresión (no es un test aparte que se pueda
ignorar): además de escribir el censo a
`verificacion_R3/CENSO_COBERTURA.md` (regenerado cada vez, para que
nadie tenga que instrumentar a mano para verlo), ASEVERA los conteos
YA MEDIDOS e independientemente verificados dos veces (una por el
operador, otra por esta misma sesión) -- si alguno cambia, es una
regresión real en el camino de negocio correspondiente, no una cifra
que se pueda tocar sin darse cuenta.

Explícitamente NO cubre (cobertura 0, ver ANALISIS_PUERTA_GRANDE.md §3):
el sorteo de dirección + veto CONTRA (en replay la dirección la fuerza
el pack, el sorteo real nunca corre), el bloqueo de eval, el pool
agotado sin sub disponible, y la degradación -- esos son, precisamente,
el objeto de D8 §5 (días adversarios), no de este censo."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import calendario, ciclo_vida as CV, orquestador as O

RUTA_PACK = os.path.join(ING, "tests", "replay_v10.json")
RUTA_SALIDA = os.path.join(AQUI, "CENSO_COBERTURA.md")

# --- instrumentación: SOLO observa, nunca cambia el cálculo (mismo principio
#     que apoyo_puerta_grande.py::genera_secuencia_qok_contrato) -----------------
contadores = dict(empalme=0, activacion_funded=0, emergencia=0, pool_agotado=0,
                   contra_armada=0, bloqueo_funded=0, bloqueo_eval=0, tope_tesoreria=0,
                   sorteo_direccion_llamadas=0)

_orig_arma_empalme = CV.arma_empalme_eval
def _w_arma_empalme(*a, **kw):
    r = _orig_arma_empalme(*a, **kw)
    if r['arranca']:
        contadores['empalme'] += 1
    return r

_orig_activa_funded = CV.activa_funded_si_toca
def _w_activa_funded(funded_estado, recamara_dormidas):
    nuevo, dormidas, activada = _orig_activa_funded(funded_estado, recamara_dormidas)
    if activada:
        contadores['activacion_funded'] += 1
    return nuevo, dormidas, activada

_orig_toma_sub = CV.toma_sub
def _w_toma_sub(*a, **kw):
    r = _orig_toma_sub(*a, **kw)
    obtuvo, es_emerg = r[0], r[1]
    if obtuvo and es_emerg:
        contadores['emergencia'] += 1
    if not obtuvo:
        contadores['pool_agotado'] += 1
    return r

_orig_cierra_funded = CV.cierra_resolucion_funded
def _w_cierra_funded(*a, **kw):
    r = _orig_cierra_funded(*a, **kw)
    if r['bloqueo']:
        contadores['bloqueo_funded'] += 1
    return r

_orig_cierra_eval = CV.cierra_resolucion_eval
def _w_cierra_eval(*a, **kw):
    r = _orig_cierra_eval(*a, **kw)
    if r['bloqueo']:
        contadores['bloqueo_eval'] += 1
    return r

_orig_qcap = CV.qcap_abierto
_orig_qcap_tes = CV.qcap_abierto_por_tesoreria
_ultimo_qcap_normal = [None]
def _w_qcap(n):
    r = _orig_qcap(n)
    _ultimo_qcap_normal[0] = r
    return r

def _w_qcap_tes(caja, retirado):
    r = _orig_qcap_tes(caja, retirado)
    if (not _ultimo_qcap_normal[0]) and r:
        contadores['tope_tesoreria'] += 1
    return r

_orig_sortea = calendario.sortea_direccion
def _w_sortea(*a, **kw):
    r = _orig_sortea(*a, **kw)
    contadores['sorteo_direccion_llamadas'] += 1
    _, contra_pendiente = r
    if contra_pendiente > 0:
        contadores['contra_armada'] += 1
    return r


def genera_censo(ruta_pack=RUTA_PACK):
    """Corre corre_replay() con toda la instrumentación puesta, y devuelve
    (contadores, diarios, st) -- SOLO observación, el cálculo de negocio
    es el de siempre."""
    CV.arma_empalme_eval = _w_arma_empalme
    CV.activa_funded_si_toca = _w_activa_funded
    CV.toma_sub = _w_toma_sub
    CV.cierra_resolucion_funded = _w_cierra_funded
    CV.cierra_resolucion_eval = _w_cierra_eval
    CV.qcap_abierto = _w_qcap
    CV.qcap_abierto_por_tesoreria = _w_qcap_tes
    calendario.sortea_direccion = _w_sortea
    try:
        fines, diarios, st = O.corre_replay(ruta_pack)
    finally:
        CV.arma_empalme_eval = _orig_arma_empalme
        CV.activa_funded_si_toca = _orig_activa_funded
        CV.toma_sub = _orig_toma_sub
        CV.cierra_resolucion_funded = _orig_cierra_funded
        CV.cierra_resolucion_eval = _orig_cierra_eval
        CV.qcap_abierto = _orig_qcap
        CV.qcap_abierto_por_tesoreria = _orig_qcap_tes
        calendario.sortea_direccion = _orig_sortea
    return dict(contadores), diarios, st


if __name__ == '__main__':
    resultados = []
    def ok(nombre, cond, detalle=""):
        resultados.append((nombre, cond))
        print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))

    c, diarios, st = genera_censo()

    n_dias = len(diarios)
    muertes_eval = sum(d['eventos']['muertes_eval'] for d in diarios)
    muertes_funded = sum(d['eventos']['muertes_funded'] for d in diarios)
    aprobaciones = sum(d['eventos']['aprobaciones'] for d in diarios)
    recompras = sum(d['eventos']['recompras'] for d in diarios)

    filas = [
        ("Sesión base",                                    n_dias,               "machacado"),
        ("Empalme (R-4.3)",                                 c['empalme'],         "machacado" if c['empalme'] else "NUNCA"),
        ("Muertes de eval",                                 muertes_eval,         "machacado" if muertes_eval else "NUNCA"),
        ("Muertes de funded",                                muertes_funded,       "machacado" if muertes_funded else "NUNCA"),
        ("Activaciones de funded (relevo R-5.1)",           c['activacion_funded'], "machacado" if c['activacion_funded'] else "NUNCA"),
        ("Aprobaciones",                                    aprobaciones,          "machacado" if aprobaciones else "NUNCA"),
        ("Recompras",                                       recompras,             "machacado" if recompras else "NUNCA"),
        ("Compras de emergencia (pool sin frescas)",        c['emergencia'],       "machacado" if c['emergencia'] else "NUNCA"),
        ("CONTRA armada al cierre",                          c['contra_armada'],    "contador sí, efecto no (dirección forzada por el pack en replay)"),
        ("Bloqueo de funded (R-2.4)",                        c['bloqueo_funded'],   "tocado" if c['bloqueo_funded'] else "NUNCA"),
        ("Levantamiento del tope por tesorería",             c['tope_tesoreria'],   "tocado" if c['tope_tesoreria'] else "NUNCA"),
        ("Bloqueo de eval",                                  c['bloqueo_eval'],     "0 en el pack -- existe pero el pack no lo toca; §5 aún sin cubrir aparte"),
        ("Pool agotado sin sub disponible",                  c['pool_agotado'],     "0 en el pack -- existe pero el pack no lo toca; cubierto aparte en "
                                                                                     "verificacion_R3/prueba_pool_agotado.py (§5.3, 38/38)"),
        ("Degradación (degradado/dia_degradacion)",          1 if st['degradado'] else 0, "0 en el pack -- existe pero el pack no lo toca; cubierto aparte en "
                                                                                           "verificacion_R3/prueba_degradacion.py (§5.4, 10/10)"),
        ("Sorteo 50/50 + veto CONTRA decidiendo dirección",  0, "0 en el pack, ESTRUCTURALMENTE -- en replay la dirección la fuerza el pack "
                                                                 "(orquestador.py: \"candidata\" es relleno sin efecto) -- pero existe y funciona: "
                                                                 "cubierto aparte en verificacion_R3/prueba_sorteo_direccion_contra.py (§5.1, 9/9)"),
        ("Escalada N0-N4 / aviso humano por bloqueo sostenido de funded", 0,
         "0 (MECANISMO INEXISTENTE, no \"el pack no lo toca\" -- distinción del operador, "
         "RESPUESTA_D8_ITEM2_BLOQUEO.md §3): ausencia CONFIRMADA y certificada en "
         "verificacion_R3/prueba_ausencia_escalada_bloqueo.py (§5.2, 10/10) -- ningún camino "
         "de bot/ escribe pendientes_humano[].dias_esperando ni conecta "
         "alertas.bloqueada_escalada_dias/proveedor_mata_cuenta_dias a la escalera N0-N4. "
         "Confirmado por el operador: conocido, aceptado, NO se cablea ahora."),
    ]

    with open(RUTA_SALIDA, 'w', encoding='utf-8') as fh:
        fh.write("# Censo de cobertura -- 504 días de tests/replay_v10.json\n\n")
        fh.write("Regenerado por `verificacion_R3/prueba_censo_cobertura.py` -- instrumentación directa\n")
        fh.write("sobre `bot/ciclo_vida.py`/`bot/calendario.py`, nunca reconstrucción a mano (R2/R3).\n")
        fh.write("Ver `ANALISIS_PUERTA_GRANDE.md` §3 para el porqué de esta tabla: \"un gate en verde\n")
        fh.write("sobre un camino con cobertura 0 no es información\".\n\n")
        fh.write("| Camino | Veces en el pack | Estado |\n|---|---|---|\n")
        for nombre, n, estado in filas:
            fh.write(f"| {nombre} | {n} | {estado} |\n")

    print(open(RUTA_SALIDA).read())

    # --- aseveraciones -- pines de regresión sobre los caminos YA machacados,
    #     verificados independientemente dos veces (operador + esta sesión).
    #     Si alguno cambia, es una regresión real en ese camino de negocio.
    ok("504 días procesados", n_dias == 504, n_dias)
    ok("empalme (R-4.3): 150 -- machacado, no 0 (corregido tras ANALISIS_PUERTA_GRANDE.md)",
       c['empalme'] == 150, c['empalme'])
    ok("muertes de eval: 150", muertes_eval == 150, muertes_eval)
    ok("muertes de funded: 94", muertes_funded == 94, muertes_funded)
    ok("activaciones de funded (relevo): 96", c['activacion_funded'] == 96, c['activacion_funded'])
    ok("aprobaciones: 98", aprobaciones == 98, aprobaciones)
    ok("recompras: 98", recompras == 98, recompras)
    ok("compras de emergencia: 138", c['emergencia'] == 138, c['emergencia'])
    ok("CONTRA armada al cierre: 192", c['contra_armada'] == 192, c['contra_armada'])
    ok("bloqueo de funded: 1", c['bloqueo_funded'] == 1, c['bloqueo_funded'])
    ok("levantamiento del tope por tesorería: 1 (el día 269, D-5)", c['tope_tesoreria'] == 1,
       c['tope_tesoreria'])
    ok("bloqueo de eval: 0 (cobertura 0 conocida, no un bug)", c['bloqueo_eval'] == 0, c['bloqueo_eval'])
    ok("pool agotado: 0 (cobertura 0 conocida, no un bug)", c['pool_agotado'] == 0, c['pool_agotado'])
    ok("degradación: nunca (cobertura 0 conocida, no un bug)", not st['degradado'])

    print("\n" + "=" * 70)
    n_ok = sum(1 for _, cond in resultados if cond)
    print(f"{n_ok}/{len(resultados)} comprobaciones OK")
    if n_ok != len(resultados):
        sys.exit(1)
