# -*- coding: utf-8 -*-
"""orquestador.py · D2-D7 · el bucle que ata calendario + ciclo_vida + tesoreria + estado.

02_ARQUITECTURA.md §2 describe `bot.py` como "el bucle: leer estado → calendario →
sesión → persistir → dormir" y prohíbe que contenga reglas de negocio -- las reglas
viven en `ciclo_vida.py`/`tesoreria.py`/`calendario.py`; aquí solo se ENCADENAN.

Modo `--replay <fichero>` (Arquitectura §9): "fuerza dirección, ventana, resets y
barras desde el pack". Es el modo que valida este delta contra
`tests/replay_v10.json` -- 504 días, 0 divergencias, 0 invariantes rotos.

Nada de esto decide reglas de negocio nuevas: es pegamento. Toda la aritmética de una
sesión sale de `sizing.py`/`sesion.py` (D1, intocables por R6); toda la vida de una
cuenta sale de `ciclo_vida.py`; toda la tesorería de `tesoreria.py`; toda la dirección
y ventana de `calendario.py`.

--------------------------------------------------------------------------------------
HALLAZGO sobre `tests/replay_v10.json` (no es un bug de este código, es una propiedad
del fixture, documentada aquí porque cambia cómo se le llama):

El campo `dias[].barras.{ph,pl,pc}` del pack está redondeado a 2 decimales (así lo
escribe `tests/replay_v10.py`, para no disparar el tamaño del JSON). Pero los
`fin_de_dia` de referencia del propio pack salen de la simulación INTERNA de
`pipeline3.py`, que usa los precios en precisión completa (float64, sin redondear).
Usar directamente `barras` redondeada para la sesión de HOY reproduce `k` y el resto
de la aritmética exacta (verificado: `sesion.resolver_dia` con los datos redondeados
da BIT A BIT lo mismo que llamar a `pipeline3.sesion()` con esos mismos datos
redondeados) -- pero como el redondeo entra en el barrido (`ph[b]-p0 >= nu`), basta
que UN día cruce un umbral por una diferencia de precisión para que `dx` (y por tanto
`bal`) diverjan del valor de referencia por encima de la tolerancia de
`runner_replay_v10.py` (1e-3 $). Ocurrió por primera vez el día 21 de 504 (0,10 $ de
diferencia en `funded.bal`, muy por encima de la tolerancia).

Arreglo, sin tocar `tests/` ni `modelo/` (R6): reconstruir, para cada día, la fila
`j` de `modelo/datos/HG22.npy` cuyo `PC[j][:86]` redondeado a 2 decimales coincide
EXACTAMENTE con `dias[i].barras.pc` -- con 86 valores a 2 decimales el emparejamiento
es inequívoco (comprobado sobre los 504 días: 504 coincidencias únicas, 0 ambiguas,
0 sin coincidencia) -- y usar esa fila en precisión completa para la sesión del día.
Esto NO es parte del bot real (que recibe precios de mercado reales del adaptador,
nunca de `HG22.npy`): es exclusivo de la validación contra este fixture concreto.
--------------------------------------------------------------------------------------
"""
import json
import os
import sys

import numpy as np

from bot import config, estado as E, calendario, ciclo_vida as CV, tesoreria as T


def procesa_dia(st, direccion, ventana_txt, ph, pl, pc, b0v, n_resets_hoy,
                 resuelve_dia_eval=None, resuelve_dia_funded=None, modo_auto_confirma=True):
    """D8.4 (ORDEN_DE_TRABAJO_D8.md §0, revisión 20-08-2026, diseño grounded vía
    panel de ángulos + síntesis): el pegamento COMPARTIDO de un día -- pool,
    funded, eval, tesorería, retiro, `contra_pendiente` de mañana -- extraído
    SIN CAMBIOS del cuerpo que antes tenía `procesa_dia_replay` (que ahora es
    un envoltorio delgado sobre esta función, ver más abajo). No le importa de
    dónde vinieron `direccion`/`ph`/`pl`/`pc`/`n_resets_hoy` -- un pack de
    replay forzado, o un sorteo real en vivo (`bot/bucle_del_dia.py`, D8.4) --
    ni si `resuelve_dia_eval`/`resuelve_dia_funded` son `sesion.resolver_dia`
    (replay, el default si se deja `None`) o un `ResuelveDiaEnVivo`
    (`bot/resolucion_en_vivo.py`) que coloca un bracket en reposo (D8.2) y
    espera la resolución real del bróker.

    Esta extracción es lo que hace CIERTO, en sentido fuerte, "el bucle del
    día tiene que ser UNO SOLO" (§0): `bucle_del_dia` llama a ESTA función
    para cada día, tanto contra un pack de replay como en producción en vivo
    -- es literalmente la misma llamada Python, mismas ramas, en los dos
    mundos, nunca una aritmética "equivalente" reimplementada aparte.

    `resuelve_dia_eval`/`resuelve_dia_funded=None` -> usan el default de
    `ciclo_vida.py` (`sesion.resolver_dia`) -- así que `procesa_dia_replay`
    (su único llamador hasta hoy) no cambia de comportamiento ni un bit.

    Devuelve (st_nuevo, fin_de_dia_dict, diario_linea_dict) -- misma forma
    que siempre.
    """
    cfg = config.obtener()
    kwargs_eval = {} if resuelve_dia_eval is None else dict(resuelve_dia=resuelve_dia_eval)
    kwargs_funded = {} if resuelve_dia_funded is None else dict(resuelve_dia=resuelve_dia_funded)

    # --- pool: coste fijo diario + resets forzados del día ---------------------
    st["caja"] -= CV.coste_diario_pool()
    st["pool"]["frescas"], st["pool"]["rotas"] = CV.aplica_resets(
        st["pool"]["frescas"], st["pool"]["rotas"], n_resets_hoy)

    hubo_muerte_hoy = False
    ev_dia = dict(intentos=0, aprobaciones=0, muertes_funded=0, muertes_eval=0,
                  resets=n_resets_hoy, emergencias=0, recompras=0, cuotas_dia=0.0)

    # --- funded: relevo (R-5.1) + sesión (R-5.2 a R-5.5) ------------------------
    st["funded"], st["recamara"]["dormidas"], activada_hoy = CV.activa_funded_si_toca(
        st["funded"], st["recamara"]["dormidas"])
    st["recamara"]["n"] = len(st["recamara"]["dormidas"])
    st["recamara"]["sunk_total"] = sum(d["s0"] for d in st["recamara"]["dormidas"])
    if st["funded"]["activa"]:
        r = CV.procesa_dia_funded(st["funded"], direccion, ph, pl, pc, b0v,
                                   es_dia_nuevo=activada_hoy, **kwargs_funded)
        st["funded"] = r["funded_estado"]
        st["caja"] += r["caja_delta"]
        hubo_muerte_hoy = hubo_muerte_hoy or r["hubo_muerte"]
        ev_dia["muertes_funded"] += r["eventos"]["muertes_funded"]
    else:
        st["funded"]["espera"] = max(st["funded"]["espera"] - 1, 0)
    peor_dia_funded = 0.0
    if st["funded"]["activa"] or hubo_muerte_hoy:
        pass  # el detalle de peor_dia_funded/eval es diagnostico; ver runner propio mas abajo

    # --- eval: qcap se evalua UNA vez, con el estado ya actualizado por funded --
    qok = CV.qcap_abierto(st["recamara"]["n"]) or CV.qcap_abierto_por_tesoreria(
        st["caja"], st["retirado"])
    r_eval = CV.procesa_dia_eval(st["eval"], st["pool"], st["recamara"]["dormidas"],
                                  direccion, ph, pl, pc, b0v, qok,
                                  modo_auto_confirma=modo_auto_confirma,
                                  estado=st, dia_actual=st["dia_negociacion"] + 1, **kwargs_eval)
    st["eval"] = r_eval["eval_estado"]
    st["pool"] = r_eval["pool_estado"]
    st["caja"] += r_eval["caja_delta"]
    hubo_muerte_hoy = hubo_muerte_hoy or r_eval["hubo_muerte"]
    ev_dia["intentos"] += r_eval["eventos"]["intentos"]
    ev_dia["emergencias"] += r_eval["eventos"]["emergencias"]
    ev_dia["recompras"] += r_eval["eventos"]["recompras"]
    ev_dia["muertes_eval"] += r_eval["eventos"]["muertes_eval"]
    if r_eval["sunk_a_recamara"] is not None:
        ev_dia["aprobaciones"] += 1
        # reparto igual (ver docstring de ciclo_vida.activa_funded_si_toca):
        # pipeline3.py solo suma esta aportación a d_sunk (nunca la guarda
        # por separado), así que aquí se funde también en la media de TODA
        # la lista -- si no se rebalancea aquí, la próxima activación
        # (que retira exactamente `sunk_total/n`, no el valor propio de
        # ninguna entrada) rompería la invariante #1 de estado.py.
        nueva_lista = list(st["recamara"]["dormidas"])
        nueva_lista.append(
            {"s0": r_eval["sunk_a_recamara"], "desde_dia": st["dia_negociacion"] + 1})
        sunk_total_nuevo = sum(d["s0"] for d in nueva_lista)
        n_nuevo = len(nueva_lista)
        reparto = sunk_total_nuevo / n_nuevo
        st["recamara"]["dormidas"] = [dict(d, s0=reparto) for d in nueva_lista]
        st["recamara"]["n"] = n_nuevo
        st["recamara"]["sunk_total"] = sunk_total_nuevo

    # --- tesoreria: muro dinamico + degradacion ---------------------------------
    m_eval_hoy = cfg.sizing.m_eval.valor() if st["eval"]["activa"] else 0.0
    exp_eval_hoy = cfg.sizing.exp_eval_usd.valor() if st["eval"]["activa"] else 0.0
    muro = T.muro_dinamico(m_eval_hoy, exp_eval_hoy)
    st["degradado"] = T.comprueba_degradacion(st["caja"], st["retirado"], muro, st["degradado"])
    if st["degradado"] and st["dia_degradacion"] is None:
        st["dia_degradacion"] = st["dia_negociacion"] + 1

    st["dia_negociacion"] += 1
    if T.es_dia_de_retiro(st["dia_negociacion"]):
        sw = T.retiro_de_fin_de_mes(st["caja"], st["retirado"], True)
        st["retirado"] += sw
        st["acumulados_mes"]["dias_desde_retiro"] = 0
        st["acumulados_mes"]["peak"] = max(st["acumulados_mes"]["peak"], st["caja"])
    else:
        st["acumulados_mes"]["dias_desde_retiro"] += 1

    # contra_pendiente de MAÑANA: solo depende de si hubo muerte hoy, no de ningun
    # sorteo (ver calendario.sortea_direccion) -- el "candidata" es un relleno sin
    # efecto salvo que contra_pendiente llegue a 0, caso en el que la direccion de
    # MAÑANA la vuelve a forzar el pack de todos modos.
    _, st["contra_pendiente"] = calendario.sortea_direccion(
        candidata=direccion, direccion_anterior=direccion,
        contra_pendiente_anterior=st["contra_pendiente"], hubo_muerte_ayer=hubo_muerte_hoy,
        estado=st, dia_actual=st["dia_negociacion"])
    st["direccion"] = direccion

    fin_de_dia = dict(
        caja=round(st["caja"], 4), retirado=round(st["retirado"], 2),
        funded=dict(activa=st["funded"]["activa"], fase=st["funded"]["fase"],
                    bal=round(st["funded"]["bal"], 4), pico=round(st["funded"]["pico"], 4),
                    H=round(st["funded"]["H"], 4), s0=round(st["funded"]["s0"], 4),
                    dias=st["funded"]["dias"], espera=st["funded"]["espera"]),
        eval=dict(activa=st["eval"]["activa"], bal=round(st["eval"]["bal"], 4),
                   H=round(st["eval"]["H"], 4), s0=round(st["eval"]["s0"], 4)),
        recamara=dict(n=st["recamara"]["n"], sunk_total=round(st["recamara"]["sunk_total"], 4)),
        pool=dict(frescas=st["pool"]["frescas"], rotas=st["pool"]["rotas"]))

    diario = dict(dia=st["dia_negociacion"], direccion=direccion, ventana=ventana_txt,
                  eventos=ev_dia, fin_de_dia=fin_de_dia)
    return st, fin_de_dia, diario


def procesa_dia_replay(st, dia_pack):
    """Procesa UN día forzado desde el replay pack. `dia_pack` es
    `replay_v10.json['dias'][i]` (direccion, ventana, barras crudas, ya viene sin
    reflejar -- ver `calendario.refleja_camino`).

    Modo replay: `modo_auto_confirma=True` (el motor congelado aprueba y confirma
    al instante, R-4.7 -- ver el docstring de `ciclo_vida.procesa_dia_eval`). Los
    resets del pool y la ventana/dirección del día son los que trae el pack, no
    un sorteo propio (Arquitectura §9).

    D8.4 (ORDEN_DE_TRABAJO_D8.md §0, revisión 20-08-2026): esta función es ahora
    un envoltorio DELGADO -- deriva `direccion`/`ventana_txt`/`b0v`/`ph,pl,pc`
    (reflejados)/`n_resets_hoy` de `dia_pack` (exactamente como hacía antes de la
    extracción) y delega el resto en `procesa_dia()`, compartida con
    `bot/bucle_del_dia.py` (en vivo). Firma y comportamiento SIN NINGÚN CAMBIO
    para su único llamador, `corre_replay()` -- verificado bit a bit
    (`verificacion_R3/prueba_orquestador_extraccion.py`).

    Devuelve (st_nuevo, fin_de_dia_dict, diario_linea_dict).
    """
    st = json.loads(json.dumps(st))  # copia profunda barata, sin dependencias extra
    cfg = config.obtener()

    direccion = dia_pack["direccion"]
    ventana_txt = dia_pack["ventana"]
    b0v = cfg.sesion.cal_rth.b0_rth.valor() if ventana_txt == "RTH" else 0
    ph_crudo = dia_pack["barras"]["ph"]
    pl_crudo = dia_pack["barras"]["pl"]
    pc_crudo = dia_pack["barras"]["pc"]
    ph, pl, pc = calendario.refleja_camino(ph_crudo, pl_crudo, pc_crudo, direccion)
    n_resets_hoy = dia_pack["eventos"]["resets"]

    return procesa_dia(st, direccion, ventana_txt, ph, pl, pc, b0v, n_resets_hoy)


def _recupera_precision_completa(pack, ruta_modelo=None):
    """Ver el bloque HALLAZGO del docstring del módulo. Devuelve una copia de
    `pack['dias']` con `barras.{ph,pl,pc}` sustituidas por los valores en
    precisión completa de `modelo/datos/HG22.npy`, encontrados por
    emparejamiento exacto contra la versión redondeada que trae el pack.
    Lanza AssertionError si algún día no tiene una coincidencia única -- eso
    significaría que el fixture cambió y este arreglo ya no aplica."""
    if ruta_modelo is None:
        ruta_modelo = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'modelo')
    ruta_modelo = os.path.abspath(ruta_modelo)
    if ruta_modelo not in sys.path:
        sys.path.insert(0, ruta_modelo)
    import motor_exp as M
    PH, PL, PC = M.carga('HG22')
    nb = config.obtener().sesion.barras_por_dia.valor()
    PC_r = np.round(PC[:, :nb], 2)

    dias_nuevos = []
    for i, d in enumerate(pack['dias']):
        pc_pack = np.array(d['barras']['pc'])
        candidatos = np.where((PC_r == pc_pack).all(axis=1))[0]
        assert len(candidatos) == 1, (
            f"dia {i+1}: {len(candidatos)} coincidencias (se esperaba exactamente 1) -- "
            f"el fixture pudo haber cambiado, revisar el hallazgo del docstring del módulo")
        j = int(candidatos[0])
        d2 = json.loads(json.dumps(d))
        d2['barras'] = dict(ph=PH[j][:nb].tolist(), pl=PL[j][:nb].tolist(), pc=PC[j][:nb].tolist())
        dias_nuevos.append(d2)
    return dias_nuevos


def corre_replay(ruta_pack, ruta_salida_estados=None, ruta_salida_diario=None,
                  precision_completa=True):
    """Corre los 504 días del pack y devuelve la lista de `fin_de_dia` -- la misma
    forma que `tests/runner_replay_v10.py` compara. Si se dan rutas, también las
    escribe a disco (estados.json para el runner; el diario JSONL para inspección).

    `precision_completa=True` (por defecto) aplica el arreglo del HALLAZGO de
    arriba. Se puede poner a False para reproducir el comportamiento "tal cual
    trae el pack" (útil solo para volver a demostrar el problema)."""
    _, checksum = config.cargar()
    pack = json.load(open(ruta_pack))
    st = E.nuevo(version_config="v10", checksum_config=checksum)

    dias = _recupera_precision_completa(pack) if precision_completa else pack["dias"]

    fines, diarios = [], []
    for dia_pack in dias:
        st, fin_de_dia, diario = procesa_dia_replay(st, dia_pack)
        fallos = E.validar(st, checksum)
        if fallos:
            raise E.EstadoInvalidoError(
                f"dia {st['dia_negociacion']}: invariante roto tras procesar el dia:\n"
                + "\n".join(f"  - {x}" for x in fallos))
        fines.append(fin_de_dia)
        diarios.append(diario)

    if ruta_salida_estados:
        json.dump(fines, open(ruta_salida_estados, 'w'), indent=1)
    if ruta_salida_diario:
        with open(ruta_salida_diario, 'w') as fh:
            for d in diarios:
                fh.write(json.dumps(d) + "\n")
    return fines, diarios, st


if __name__ == '__main__':
    AQUI = os.path.dirname(os.path.abspath(__file__))
    RUTA_PACK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        AQUI, '..', 'tests', 'replay_v10.json')
    SALIDA = sys.argv[2] if len(sys.argv) > 2 else os.path.join(AQUI, '..', 'estados_replay.json')
    fines, diarios, st_final = corre_replay(RUTA_PACK, ruta_salida_estados=SALIDA)
    print(f"replay corrido: {len(fines)} dias -> {SALIDA}")
    print(f"caja final: {st_final['caja']:.2f} $  ·  degradado: {st_final['degradado']}")
