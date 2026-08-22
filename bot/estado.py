# -*- coding: utf-8 -*-
"""estado.py · D2 (+ D-C, desviaciones_activas) · 05_ORDEN_DE_CONSTRUCCION.md · 02_ARQUITECTURA.md §4

Responsabilidad (Arquitectura §2): serializar/deserializar `estado.json`, con versión
y checksum. PROHIBIDO: lógica de negocio -- este módulo no decide nada, solo valida
la FORMA del estado y lo persiste.

Escritura ATÓMICA (fichero temporal + rename): un corte de luz a media escritura dejaría
un `estado.json` truncado si escribiéramos directamente; con temp+rename, o está el
fichero viejo completo, o está el nuevo completo -- nunca algo a medias que el bot
pudiera leer como válido.

Los 8 invariantes son FATALES (R7 de 04_GUARDARRAILES: "aplanar todo, parar, alertar" --
la parte de aplanar/parar es del orquestador; este módulo se limita a NEGARSE a dar
por bueno un estado que los viole, lanzando ConfigInvalidoError, mismo estilo que
config.py con 03_CONFIG.yaml).
"""
import json
import os

from bot import config


class EstadoInvalidoError(RuntimeError):
    """Uno de los 8 invariantes fatales de Arquitectura §4 no se cumple, o el
    checksum de config no coincide. No se arranca ni se opera con un estado así."""


VERSION_ESQUEMA = 1


def nuevo(version_config, checksum_config):
    """Arranque en frío: 'todo a cero, pool 2 frescas, recámara vacía' -- misma
    convención que usa `tests/replay_v10.json` para poder validarse contra él.
    `pool.frescas` sale de `orquestacion.pool_subs` (R2: no es un 2 de mi cabeza)."""
    frescas_ini = config.obtener().orquestacion.pool_subs.valor()
    return {
        "version_esquema": VERSION_ESQUEMA,
        "version_config": version_config,
        "checksum_config": checksum_config,
        "dia_negociacion": 0,
        "fecha_ultimo_cierre": None,
        "caja": 0.0,
        "retirado": 0.0,
        "direccion": 1,
        "contra_pendiente": 0,
        "funded": {
            "activa": False, "fase": 0, "bal": 0.0, "pico": 0.0,
            "H": 0.0, "s0": 0.0, "dias": 0, "espera": 0,
            "k": 0.0, "m": 0.0,   # recomendación 5 (revisión operador 20-08-2026):
        },                         # el tamaño real del día, no recalculado por el dashboard
        "eval": {
            "activa": False, "bal": 0.0, "pico": 0.0, "H": 0.0, "s0": 0.0,
            "aprobada_provisional": False, "aprobada_confirmada": False,
            "k": 0.0, "m": 0.0,
        },
        "recamara": {"dormidas": [], "n": 0, "sunk_total": 0.0},
        "pool": {"frescas": frescas_ini, "rotas": 0, "subs": []},
        "pendientes_humano": [],
        "acumulados_mes": {"peak": 0.0, "dias_desde_retiro": 0},
        "degradado": False,
        "dia_degradacion": None,
        # D-C (08_LABORATORIO.md §7.5): palancas de Clase B activas ahora
        # mismo -- "cada cambio de Clase B es un evento con marca de tiempo
        # ... con quién, cuándo y hasta cuándo" y "estado.json lleva un
        # bloque de desviaciones activas, validado al arrancar como
        # cualquier otro invariante" (ver validar(), más abajo). Vacía en
        # frío: sin D-C corriendo, el circuito opera con la config
        # certificada -- lo mismo que asume tests/replay_v10.json.
        "desviaciones_activas": [],
    }


PALANCAS_CLASE_B = frozenset({'empalme', 'contra', 'emergencia', 'pausa_eval'})


def validar(estado, checksum_config_actual):
    """Los 8 invariantes fatales de Arquitectura §4, en el mismo orden que el
    documento los enumera. Devuelve la lista de fallos -- vacía = todo bien."""
    f = []
    TOL = 1e-6

    rec = estado["recamara"]
    suma = sum(d["s0"] for d in rec["dormidas"])
    if abs(rec["sunk_total"] - suma) > TOL:
        f.append(f"1: recamara.sunk_total ({rec['sunk_total']}) != "
                 f"sum(dormidas[].s0) ({suma})")

    if rec["n"] != len(rec["dormidas"]):
        f.append(f"2: recamara.n ({rec['n']}) != len(recamara.dormidas) ({len(rec['dormidas'])})")

    pool_subs_total = config.obtener().orquestacion.pool_subs.valor()
    vivas = estado["pool"]["frescas"] + estado["pool"]["rotas"] + (1 if estado["eval"]["activa"] else 0)
    if vivas != pool_subs_total:
        f.append(f"3: pool.frescas+pool.rotas+(1 si eval.activa) ({vivas}) != "
                 f"orquestacion.pool_subs ({pool_subs_total})")

    if estado["funded"]["activa"] and not (1 <= estado["funded"]["fase"] <= 5):
        f.append(f"4: funded.activa pero funded.fase={estado['funded']['fase']} fuera de [1,5]")

    if estado["funded"]["espera"] > 0 and estado["funded"]["activa"]:
        f.append("5: funded.espera > 0 pero funded.activa es verdadero")

    if estado["checksum_config"] != checksum_config_actual:
        f.append(f"6: checksum_config del estado ({estado['checksum_config']}) != "
                 f"checksum de 03_CONFIG.yaml actual ({checksum_config_actual}) -- el bot NO arranca")

    if estado["eval"]["aprobada_confirmada"] and not estado["eval"]["aprobada_provisional"]:
        f.append("7: eval.aprobada_confirmada es verdadero sin aprobada_provisional")

    # D9 §3.6 (autorización R6, 22-08-2026): sizing_G/sizing_H/sizing_fric/
    # sizing_Mm son diagnóstico puro (REVISION_REV5.md §4.3, "sin las
    # entradas un residuo anómalo no se puede diagnosticar después") --
    # NUNCA se leen para decidir nada, así que no son uno de los 8
    # invariantes de Arquitectura §4 propiamente dichos: solo se comprueba
    # que, SI están presentes, sean numéricos -- TOLERANTE A SU AUSENCIA
    # (revisión operador, AUTORIZACION_3_6_CERRADA.md §2), para que un
    # estado.json escrito antes de este cambio siga cargando sin problema.
    for slot_nombre in ("eval", "funded"):
        slot = estado[slot_nombre]
        for clave in ("sizing_G", "sizing_H", "sizing_fric", "sizing_Mm"):
            if clave in slot and not isinstance(slot[clave], (int, float)):
                f.append(f"D-6.{slot_nombre}.{clave}: {slot[clave]!r} no es numérico "
                         f"(diagnóstico de sizing corrupto)")

    # 8: "ninguna dormida entra en recamara.dormidas sin aprobada_confirmada" es una
    # invariante de TRANSICIÓN (se comprueba en el momento de añadir, en ciclo_vida.py
    # -- ver `aprobar_eval()`), no una propiedad de una foto de estado ya guardada:
    # una vez la dormida está en la lista, no lleva un campo que diga cómo llegó ahí.
    # Se documenta aquí para que las ocho estén enumeradas en un solo sitio, tal
    # como pide Arquitectura §4.

    # D-C (08_LABORATORIO.md §7.5, no es uno de los 8 de Arquitectura §4 -- es la
    # invariante que D-C le añade a estado.json): cada palanca de Clase B tiene como
    # mucho UNA desviación activa a la vez (dos entradas activas de la misma palanca
    # son ambiguas: ¿cuál manda?), toda entrada trae los campos que exige §7.5
    # ("quién, cuándo y hasta cuándo"), la palanca es una de las cuatro de Clase B
    # (08_LABORATORIO.md §7.2), y el rango de días es coherente.
    vistas = set()
    for i, d in enumerate(estado.get("desviaciones_activas", [])):
        campos_esperados = {"palanca", "desde_dia", "hasta_dia", "quien", "ts_pared"}
        faltan = campos_esperados - set(d)
        if faltan:
            f.append(f"D-C.1: desviaciones_activas[{i}] le faltan campos {sorted(faltan)}")
            continue
        if d["palanca"] not in PALANCAS_CLASE_B:
            f.append(f"D-C.2: desviaciones_activas[{i}].palanca={d['palanca']!r} "
                     f"no es una palanca de Clase B conocida {sorted(PALANCAS_CLASE_B)}")
        if d["hasta_dia"] <= d["desde_dia"]:
            f.append(f"D-C.3: desviaciones_activas[{i}]: hasta_dia ({d['hasta_dia']}) <= "
                     f"desde_dia ({d['desde_dia']})")
        if d["palanca"] in vistas:
            f.append(f"D-C.4: dos desviaciones activas a la vez para la palanca "
                     f"{d['palanca']!r} -- ambiguo, cuál manda")
        vistas.add(d["palanca"])

    return f


def valida_tope_fase(estado, topes):
    """D9 §3.2 (autorización R6, 22-08-2026): el guardián de ARRANQUE del
    tope de fase -- deliberadamente SEPARADO de `validar()` (decisión
    explícita del operador, no mía): el tope de fase es política de
    DESPLIEGUE, no un invariante de `estado.json` -- el MISMO estado es
    válido bajo una fase y no bajo otra, y meterlo dentro de `validar()`
    destruiría lo que significa "invariante" (además de arrastrar la
    firma a `guardar()` y al replay, que deben quedar intactos). Por eso
    esta función vive aparte, y el llamador (`bot/bucle_del_dia.py`)
    decide cuándo invocarla -- justo después de `cargar()`, antes de
    operar nada.

    `topes`: el mismo dict que interpreta `orquestador.procesa_dia()`
    (`{'eval': int|None, 'funded': int|None, 'recamara': int|None, ...}`,
    la tabla fase→topes vive en `bucle_del_dia.py`, este módulo no sabe
    qué es 'f3.1'). `topes=None` -> nunca falla (fase='plena', sin tope).

    "Si `estado.json` ya tiene más cuentas activas que las que la fase
    pedida permite, el arranque debe FALLAR explícitamente, nunca truncar
    en silencio" -- por eso esto compara el estado YA CARGADO contra el
    tope, en vez de simplemente no operar más allá de él a partir de hoy.

    Devuelve la lista de fallos (vacía = arranca limpio) -- MISMO patrón
    que `validar()`, para que el llamador reaccione igual (típicamente
    envolviendo en `EstadoInvalidoError`, aunque esta función no lo hace
    ella misma -- no le corresponde decidir la reacción, solo medir)."""
    if topes is None:
        return []
    f = []
    tope_eval = topes.get('eval')
    eval_activas = 1 if estado['eval']['activa'] else 0
    if tope_eval is not None and eval_activas > tope_eval:
        f.append(f"tope de fase: eval activas ({eval_activas}) > tope permitido ({tope_eval})")
    tope_funded = topes.get('funded')
    funded_activas = 1 if estado['funded']['activa'] else 0
    if tope_funded is not None and funded_activas > tope_funded:
        f.append(f"tope de fase: funded activas ({funded_activas}) > tope permitido ({tope_funded})")
    tope_recamara = topes.get('recamara')
    if tope_recamara is not None and estado['recamara']['n'] > tope_recamara:
        f.append(f"tope de fase: recamara.n ({estado['recamara']['n']}) > "
                 f"tope permitido ({tope_recamara})")
    return f


def cargar(ruta):
    """Carga y valida `estado.json`. Lanza EstadoInvalidoError si algún invariante
    falla o si el checksum de config no coincide -- 'fallar al arrancar', mismo
    principio que `config.cargar()`.

    10_SEGURIDAD.md §4.D (hueco cazado en R3, revisión 20-08-2026): un fichero
    truncado lanzaba `json.JSONDecodeError`, y uno con campos ausentes lanzaba
    `KeyError` desde dentro de `validar()` -- las dos excepciones CRUDAS de
    Python, indistinguibles de un bug en el propio código de quien llama.
    "Estado corrupto" y "hay un bug en mi código" exigen respuestas distintas
    (10_SEGURIDAD.md §3: estado corrupto o ausente → N4, ni se adivina ni se
    reconstruye a la brava) -- pero solo se puede reaccionar distinto a dos
    cosas que se puedan DISTINGUIR. Ahora las dos se envuelven en
    `EstadoInvalidoError`, la misma excepción tipada que ya usan los 8
    invariantes -- quien llama no tiene que saber si fue un JSON roto, un
    campo ausente, o un invariante violado: los tres son "no se puede
    confiar en este estado", y los tres llevan a la misma reacción."""
    if not os.path.isfile(ruta):
        raise EstadoInvalidoError(f"no existe estado en {ruta}")
    with open(ruta, 'r', encoding='utf-8') as fh:
        contenido = fh.read()
    try:
        estado = json.loads(contenido)
    except json.JSONDecodeError as ex:
        raise EstadoInvalidoError(
            f"estado.json en {ruta} no es JSON válido (fichero corrupto o truncado) -- "
            f"el bot no arranca: {ex}") from ex
    _, checksum_actual = config.cargar()
    try:
        fallos = validar(estado, checksum_actual)
    except (KeyError, TypeError, AttributeError) as ex:
        raise EstadoInvalidoError(
            f"estado.json en {ruta} es JSON válido pero le falta o tiene mal formado un campo "
            f"esperado -- el bot no arranca (no se adivina el valor que falta): "
            f"{type(ex).__name__}: {ex}") from ex
    if fallos:
        raise EstadoInvalidoError(
            "estado.json viola invariantes fatales (Arquitectura §4 -- el bot no arranca):\n"
            + "\n".join(f"  - {x}" for x in fallos))
    return estado


def guarda_instantanea(estado, directorio, dia_negociacion, dias_retenidos):
    """10_SEGURIDAD.md §4.D, §7 (hueco no numerado, "ya estaba anotado"):
    instantánea diaria ROTATORIA de `estado.json`, ADEMÁS de (nunca en vez
    de) `guardar()`. La escritura atómica de `guardar()` ya protege contra
    un fichero roto A MEDIAS -- pero no contra un contenido VÁLIDO pero
    EQUIVOCADO, "que es peor porque no se nota" (cita literal del
    documento): un bug que corrompe silenciosamente `bal`/`H`/`s0` durante
    semanas no deja ningún rastro si solo existe el `estado.json` de hoy.
    Con instantáneas diarias, se puede comparar contra un punto anterior y
    ver cuándo empezó a divergir.

    `dias_retenidos` es OBLIGATORIO, sin valor por defecto -- a propósito:
    10_SEGURIDAD.md §8 dice explícitamente que "cuántos días de
    instantáneas se guardan" es una decisión del operador, no del código
    ("p. ej. 30 días" en el documento es un EJEMPLO del marco, no una
    cifra propuesta -- ver 03_CONFIG.yaml → pendientes). Exigir el
    parámetro sin default evita que alguien lo llame sin haber decidido
    el número, y que ese número por defecto se confunda con una decisión
    ya tomada."""
    os.makedirs(directorio, exist_ok=True)
    nombre = f"estado_dia_{dia_negociacion:04d}.json"
    ruta = os.path.join(directorio, nombre)
    tmp = os.path.join(directorio, f".{nombre}.tmp")
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(estado, fh, indent=1, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)

    if dias_retenidos > 0:
        existentes = sorted(f for f in os.listdir(directorio)
                             if f.startswith("estado_dia_") and f.endswith(".json"))
        for viejo in existentes[:-dias_retenidos]:
            try:
                os.remove(os.path.join(directorio, viejo))
            except FileNotFoundError:
                pass  # ya lo borró otra instantánea concurrente -- no es un fallo


def guardar(estado, ruta):
    """Escritura atómica: fichero temporal en el mismo directorio (para que el
    `rename` sea atómico incluso entre sistemas de ficheros distintos montados
    aparte) + `os.replace`. Valida ANTES de escribir -- nunca se persiste un
    estado que ya sabemos que viola un invariante."""
    _, checksum_actual = config.cargar()
    fallos = validar(estado, checksum_actual)
    if fallos:
        raise EstadoInvalidoError(
            "se intentó guardar un estado que viola invariantes fatales:\n"
            + "\n".join(f"  - {x}" for x in fallos))
    directorio = os.path.dirname(os.path.abspath(ruta)) or '.'
    tmp = os.path.join(directorio, f".{os.path.basename(ruta)}.tmp")
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(estado, fh, indent=1, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)
