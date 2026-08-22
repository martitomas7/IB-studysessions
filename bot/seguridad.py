# -*- coding: utf-8 -*-
"""seguridad.py · D8 · 10_SEGURIDAD.md

Marco de contención: el invariante PLANO/CUBIERTO/TRANSICION (§1), la
clasificación CONOCIDO-SEGURO/CONOCIDO-INSEGURO/DESCONOCIDO (§2, "la que de
verdad importa: qué sabemos, no qué ha pasado"), y la escalera de
degradación N0-N4 (§3): "el sistema sube solo; solo baja con un humano."

PROHIBIDO (mismo principio que el resto de `bot/`): este módulo no decide
sizing ni sesión, no habla con el bróker -- clasifica lo que YA se sabe
(posiciones leídas, legibilidad de esa lectura) y lleva la cuenta del nivel
de contención. Quien llama (D8.4, todavía sin construir) es quien de
verdad ejecuta aplanamientos/paradas -- este módulo dice QUÉ toca, nunca lo
hace.

**Por qué el nivel vive en SU PROPIO fichero (`nivel.json`), nunca dentro
de `estado.json`:** un `estado.json` corrupto es uno de los propios
disparadores de N4 (10_SEGURIDAD.md §4.D) -- si el nivel de seguridad
viviera dentro de `estado.json`, un `estado.json` roto se llevaría consigo
la propia contención justo cuando más hace falta. Separar los dos ficheros
es también lo que hace posible el requisito literal de N3 ("no reanuda
aunque lo reinicien"): el nivel sobrevive al reinicio del PROCESO porque no
depende de que `estado.json` se pueda leer -- se lee ANTES, con su propia
escritura atómica (mismo patrón que `estado.py`/`comandos.py`)."""
import json
import os

NIVELES = ('N0', 'N1', 'N2', 'N3', 'N4')
_RANGO = {n: i for i, n in enumerate(NIVELES)}
NOMBRES = {
    'N0': 'NORMAL',
    'N1': 'SIN_APERTURAS',
    'N2': 'PLANO_Y_PARADO_HOY',
    'N3': 'KILL',
    'N4': 'CONGELADO',
}

# DECISION_DEGRADACION_N3.md §3 (revisión operador 21-08-2026): "la escalera
# responde a 'qué le está permitido hacer al bot ahora mismo', y esa pregunta
# es la misma venga la causa de un descuadre de patas o de un muro de
# capital. Dos sistemas de escalada en paralelo es peor que uno." UNA sola
# escalera, con causa TIPADA -- para que el panel diga por qué está donde
# está. Vocabulario MÍNIMO que da el operador: reconciliacion,
# posicion_descuadrada, estado_corrupto, degradacion_tesoreria -- más
# `presupuesto_reinicios` (añadido aquí, no en la respuesta del operador:
# `reacciona_a_presupuesto_reinicios_agotado`, ya existente, no encajaba en
# ninguna de las cuatro -- "reversible: si más adelante molesta, se separa").
CAUSAS = frozenset({
    'reconciliacion', 'posicion_descuadrada', 'estado_corrupto',
    'degradacion_tesoreria', 'presupuesto_reinicios',
})
# 10_SEGURIDAD.md §3, columna "quién lo baja": N1 ("solo, al desaparecer la
# causa") y N2 ("solo, al día siguiente") admiten desescalado AUTOMÁTICO;
# N3 y N4 ("humano, explícito") NUNCA. El pedido de trabajo D8 §2 lo repite
# como puerta explícita: "una prueba que demuestre que NO existe ningún
# camino de código que baje de N3 o N4 sin intervención."
_NIVELES_SOLO_HUMANO = frozenset({'N3', 'N4'})


class NivelInvalidoError(RuntimeError):
    """Un nivel que no es uno de los 5 legales, un intento de desescalar sin
    la autorización que ese nivel exige, o una llamada que no es
    genuinamente una bajada de nivel."""


# --- §1: PLANO / CUBIERTO / TRANSICION / VIOLACION ----------------------

def clasifica_posicion(cantidad_hedge, cantidad_prop, m_esperado, k_esperado,
                        en_ventana_transicion):
    """10_SEGURIDAD.md §1, a partir de lo que el bróker YA reporta
    (`leer_posicion()` en las dos cuentas) -- nunca de lo que el bot cree
    que debería tener.

    - **PLANO**: las dos cuentas en cero.
    - **CUBIERTO**: las dos abiertas Y con tamaños que se corresponden
      (`|cantidad_hedge| == m_esperado` y `|cantidad_prop| == k_esperado`
      -- "la reconciliación compara tamaño, no solo presencia", §4.E). Dos
      patas abiertas con un tamaño que NO cuadra no es CUBIERTO, aunque las
      dos existan.
    - **TRANSICION**: exactamente una pata abierta, y `en_ventana_transicion`
      es `True` (dentro de `N`/`N_hedge`, con acción compensatoria ya
      decidida -- eso lo garantiza quien llama; esta función solo
      clasifica, nunca decide si la ventana sigue abierta).
    - **VIOLACION**: cualquier otra combinación -- una pata sola FUERA de
      la ventana de transición, o dos patas con tamaños que no se
      corresponden (catálogo G, "forzar tamaños que no se corresponden
      entre patas"). "Fuera de la ventana de transición, 'una pata' no es
      un estado: es una emergencia" (§1)."""
    hedge_abierto = cantidad_hedge != 0
    prop_abierto = cantidad_prop != 0

    if not hedge_abierto and not prop_abierto:
        return 'PLANO'
    if hedge_abierto and prop_abierto:
        if abs(cantidad_hedge) == m_esperado and abs(cantidad_prop) == k_esperado:
            return 'CUBIERTO'
        return 'VIOLACION'
    return 'TRANSICION' if en_ventana_transicion else 'VIOLACION'


# --- §2: CONOCIDO-SEGURO / CONOCIDO-INSEGURO / DESCONOCIDO --------------

def clasifica_conocimiento(hedge_legible, prop_legible, estado_posicion):
    """10_SEGURIDAD.md §2 -- "la clasificación que de verdad importa: qué
    sabemos, no qué ha pasado". Combina si se pudo LEER cada pata con
    certeza (`hedge_legible`/`prop_legible`: `leer_posicion()` no lanzó, la
    conexión está viva) con el resultado de `clasifica_posicion()`.

    **DESCONOCIDO es la regla contraintuitiva** (§2): si CUALQUIERA de las
    dos patas no se pudo leer con certeza, la respuesta es DESCONOCIDO --
    sin importar qué diga `estado_posicion` (puede que ni siquiera se haya
    podido calcular). "Ante la duda no se espera a saber más -- se
    aplana." Generaliza `07_ADAPTADOR_NT8.md §5.3`: "si no se puede
    demostrar que es una, se fuerza a ninguna."

    Si las dos son legibles: PLANO/CUBIERTO -> CONOCIDO-SEGURO;
    TRANSICION/VIOLACION -> CONOCIDO-INSEGURO ("sé que tengo una pata
    sola" cubre TRANSICION; VIOLACION es sabido pero malo, misma
    reacción: cerrar la pata expuesta, subir de nivel, alertar)."""
    if not hedge_legible or not prop_legible:
        return 'DESCONOCIDO'
    if estado_posicion in ('PLANO', 'CUBIERTO'):
        return 'CONOCIDO-SEGURO'
    return 'CONOCIDO-INSEGURO'


# --- §3: la escalera N0-N4 -----------------------------------------------

def nivel_de_fabrica():
    """Arranque en frío: N0, sin historial de fallos previo."""
    return {"nivel": "N0", "historial": []}


def lee_nivel(ruta):
    """Lee `nivel.json`. Si no existe todavía, N0 de fábrica -- mismo
    principio que un `estado.json` que nunca se ha escrito: "sin historial
    de fallos" es una lectura legítima de "nunca ha pasado nada", no un
    error. Un `nivel.json` que SÍ existe pero está corrupto (JSON roto)
    propaga la excepción cruda de `json.loads` a propósito -- si no se
    puede confiar ni en el propio registro de nivel, eso ES una condición
    de DESCONOCIDO/N4 para quien llama, no algo que este módulo deba
    adivinar u ocultar."""
    if not os.path.isfile(ruta):
        return nivel_de_fabrica()
    with open(ruta, encoding='utf-8') as fh:
        return json.load(fh)


def _guarda_nivel(registro, ruta):
    """Escritura atómica (tmp+fsync+replace) -- mismo patrón que
    `estado.py`/`comandos.py` en todo el proyecto."""
    directorio = os.path.dirname(os.path.abspath(ruta)) or '.'
    os.makedirs(directorio, exist_ok=True)
    tmp = os.path.join(directorio, f".{os.path.basename(ruta)}.tmp")
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(registro, fh, indent=1, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)


def nivel_actual(ruta):
    return lee_nivel(ruta)['nivel']


def sube_a(ruta, nivel_nuevo, motivo, causa, dia_negociacion=None):
    """§3: "el sistema sube solo" -- NUNCA exige autorización humana. Si
    `nivel_nuevo` no es más severo que el nivel ya alcanzado, no hace
    nada -- subir nunca reduce ni reescribe un nivel ya vigente (un fallo
    de menor severidad detectado DESPUÉS de un N3 no lo baja a N2:
    escalar es monótono). Devuelve el nivel final (el nuevo, o el que ya
    había si `nivel_nuevo` no era más severo).

    `causa` (DECISION_DEGRADACION_N3.md §3, revisión operador
    21-08-2026): OBLIGATORIA, uno de `CAUSAS` -- para que el panel diga
    POR QUÉ está donde está, no solo un `motivo` de texto libre. Idempotente
    en la práctica: llamar de nuevo con la MISMA causa/nivel, ya vigente o
    menos severo, no hace nada (la monotonía de arriba ya lo cubre) -- así
    una guarda puede llamarse todos los días sin comprobar antes el nivel
    actual (DECISION_DEGRADACION_N3.md §5, test #3: "evaluada cada día").

    `dia_negociacion` (ORDEN_DE_TRABAJO_D9.md §3.1, opcional -- SOLO N1/N2
    lo necesitan hoy, ninguna otra causa desciende sola): el día en que se
    fijó ESTA transición, para que `intenta_bajar_automatico()` pueda
    aplicar "N2 baja al día siguiente, no el mismo" sin parsear el texto
    libre de `motivo`. `None` para las causas que nunca bajan solas
    (N3/N4) -- no hace falta ensuciar su historial con un dato que nadie
    va a leer."""
    if nivel_nuevo not in NIVELES:
        raise NivelInvalidoError(f"nivel desconocido: {nivel_nuevo!r}")
    if causa not in CAUSAS:
        raise NivelInvalidoError(f"causa desconocida: {causa!r} -- debe ser una de {sorted(CAUSAS)}")
    registro = lee_nivel(ruta)
    actual = registro.get('nivel', 'N0')
    if _RANGO[nivel_nuevo] > _RANGO[actual]:
        registro['nivel'] = nivel_nuevo
        registro.setdefault('historial', []).append(
            dict(de=actual, a=nivel_nuevo, motivo=motivo, causa=causa, quien='sistema',
                 dia_negociacion=dia_negociacion))
        _guarda_nivel(registro, ruta)
        return nivel_nuevo
    return actual


def baja_automatica(ruta, nivel_nuevo, motivo):
    """§3: SOLO legal si el nivel actual es N1 o N2 ("solo, al desaparecer
    la causa" / "solo, al día siguiente"). Lanza `NivelInvalidoError` si
    el nivel actual es N3 o N4 -- exactamente el camino de código que
    10_SEGURIDAD.md §3 y `ORDEN_DE_TRABAJO_D8.md` §2 exigen que NO
    exista ("ningún camino de código que baje de N3 o N4 sin
    intervención"). También lanza si `nivel_nuevo` no es genuinamente
    menos severo que el actual."""
    if nivel_nuevo not in NIVELES:
        raise NivelInvalidoError(f"nivel desconocido: {nivel_nuevo!r}")
    registro = lee_nivel(ruta)
    actual = registro.get('nivel', 'N0')
    if actual in _NIVELES_SOLO_HUMANO:
        raise NivelInvalidoError(
            f"desescalar automáticamente desde {actual} ({NOMBRES[actual]}) está prohibido "
            f"(10_SEGURIDAD.md §3: solo baja con un humano, explícito) -- usa baja_humana()")
    if _RANGO[nivel_nuevo] >= _RANGO[actual]:
        raise NivelInvalidoError(
            f"baja_automatica() exige un nivel MENOS severo que el actual "
            f"({actual} -> {nivel_nuevo} no es una bajada)")
    registro['nivel'] = nivel_nuevo
    registro.setdefault('historial', []).append(
        dict(de=actual, a=nivel_nuevo, motivo=motivo, quien='sistema'))
    _guarda_nivel(registro, ruta)
    return nivel_nuevo


def baja_humana(ruta, nivel_nuevo, quien, motivo):
    """Desescala con autorización humana EXPLÍCITA -- válida desde
    CUALQUIER nivel, incluidos N3/N4 (§3: "humano, explícito"). `quien`
    es obligatorio y no puede ser `'sistema'` -- esa palabra está
    reservada para las transiciones automáticas de `sube_a()`/
    `baja_automatica()`, y rechazarla aquí es la barrera que impide que
    código automatizado se haga pasar por la autorización humana que N3/
    N4 exigen."""
    if nivel_nuevo not in NIVELES:
        raise NivelInvalidoError(f"nivel desconocido: {nivel_nuevo!r}")
    if not quien or quien == 'sistema':
        raise NivelInvalidoError(
            "bajar de nivel exige 'quien' explícito y humano -- 'sistema' está reservado "
            "para las transiciones automáticas (10_SEGURIDAD.md §3)")
    registro = lee_nivel(ruta)
    actual = registro.get('nivel', 'N0')
    if _RANGO[nivel_nuevo] >= _RANGO[actual]:
        raise NivelInvalidoError(
            f"baja_humana() exige un nivel MENOS severo que el actual "
            f"({actual} -> {nivel_nuevo} no es una bajada)")
    registro['nivel'] = nivel_nuevo
    registro.setdefault('historial', []).append(
        dict(de=actual, a=nivel_nuevo, motivo=motivo, quien=quien))
    _guarda_nivel(registro, ruta)
    return nivel_nuevo


def intenta_bajar_automatico(ruta, dia_negociacion, causa_sigue_activa):
    """ORDEN_DE_TRABAJO_D9.md §3.1 -- la guardia diaria que cierra el hueco
    documentado en `bucle_del_dia.py` ("N1/N2 se desescalan solos en otro
    punto... 'cuándo exactamente' no está grounded en este diseño"): mismo
    patrón que `reacciona_a_degradacion_tesoreria()` -- se llama TODOS los
    días, sin comprobar antes el nivel actual (no-op si no hay nada que
    bajar), y usa `baja_automatica()` sin reimplementar sus barreras
    (N3/N4 siguen prohibidos ahí, esta función ni lo intenta).

    `causa_sigue_activa`: **tri-estado**, calculado por quien llama
    volviendo a correr el MISMO clasificador que disparó la subida (nunca
    un detector nuevo -- "semántica ya escrita, no la inventes"):
    - `False` -- la causa ya no se observa. N1 baja YA ("al desaparecer
      la causa"); N2 baja SOLO si `dia_negociacion` es POSTERIOR al día en
      que `sube_a()` la fijó ("al día siguiente, no el mismo").
    - `True` -- la causa sigue presente. Nunca baja, sea cual sea el día
      (test del operador: "N2 con la causa presente -> no baja").
    - `None` -- no se pudo verificar (equivalente a DESCONOCIDO otra vez).
      Nunca baja -- "ante la duda, no se resume" es la misma norma que
      "ante la duda, se aplana" mirada desde el lado de bajar (test del
      operador: "N1 por UNKNOWN -> no baja nunca").

    Devuelve el nivel final (bajado o el que ya había)."""
    registro = lee_nivel(ruta)
    actual = registro.get('nivel', 'N0')
    if actual not in ('N1', 'N2'):
        return actual   # N0: nada que bajar. N3/N4: baja_automatica() los rechaza; ni lo intentamos.
    if causa_sigue_activa is None or causa_sigue_activa:
        return actual
    historial = registro.get('historial', [])
    ultimo = historial[-1] if historial else {}
    causa = ultimo.get('causa')
    if actual == 'N1':
        return baja_automatica(ruta, 'N0', motivo=f"causa desaparecida (causa={causa})")
    # N2: "al día siguiente" -- dia_fijado ausente (registro antiguo, sin
    # dia_negociacion) se trata como "no se sabe cuándo", nunca como "ya
    # pasó un día" -- la misma cautela que el resto de esta función.
    dia_fijado = ultimo.get('dia_negociacion')
    if dia_fijado is not None and dia_negociacion > dia_fijado:
        return baja_automatica(ruta, 'N0',
                                motivo=f"día siguiente ({dia_fijado} -> {dia_negociacion}), "
                                       f"causa desaparecida (causa={causa})")
    return actual


# --- reacciones cableadas del catálogo (10_SEGURIDAD.md §4) --------------
# Cada una traduce un hecho YA detectado por su propio módulo (estado.py,
# deteccion_liquidacion.py) al nivel que le corresponde -- ninguna decide
# NADA nuevo, solo aplica la tabla de §3. D8.4 (todavía sin construir) es
# quien las llama en el momento oportuno del bucle del día.

def reacciona_a_estado_invalido(ruta_nivel, detalle):
    """§3/§4.D: "estado corrupto o ausente -> N4. No se adivina, no se
    reconstruye a la brava y se sigue." Se llama desde el `except
    EstadoInvalidoError` de quien arranca el bot -- el propio
    `estado.json` roto es la razón por la que el nivel NO puede vivir ahí
    (ver docstring del módulo)."""
    return sube_a(ruta_nivel, 'N4', motivo=f"estado.json inválido: {detalle}", causa='estado_corrupto')


def reacciona_a_liquidacion_forzosa(ruta_nivel, detalle, dia_negociacion):
    """§4.B/D8.3: el proveedor liquidó la prop por su cuenta -> el hedge se
    cierra (ya lo hace `deteccion_liquidacion.resuelve_liquidacion_forzosa`)
    y el nivel sube a N2 ("plano y parado hoy").

    `dia_negociacion` obligatorio desde ORDEN_DE_TRABAJO_D9.md §3.1: N2 es
    uno de los dos niveles que bajan solos, y necesita saber desde qué día
    quedó fijado para aplicar "al día siguiente, no el mismo"."""
    return sube_a(ruta_nivel, 'N2', motivo=f"liquidación forzosa: {detalle}", causa='reconciliacion',
                  dia_negociacion=dia_negociacion)


def reacciona_a_presupuesto_reinicios_agotado(ruta_nivel, detalle):
    """§5: "R reinicios en M minutos -> se deja de reiniciar y se sube a
    N3." La lógica de CONTAR reinicios y decidir "se acabó el
    presupuesto" vive hoy en `watchdog_bot.ps1` (PowerShell, artefacto de
    despliegue real para la máquina Windows -- fuera de alcance tocar más
    sin esa máquina, `ORDEN_DE_TRABAJO_D8.md` §6). Esta función es el lado
    Python de la reacción -- lista para que, cuando exista acceso a esa
    máquina, el script solo tenga que llamarla (o su equivalente
    PowerShell escriba el mismo `nivel.json`) en vez de limitarse a
    `exit 1`."""
    return sube_a(ruta_nivel, 'N3', motivo=f"presupuesto de reinicios agotado: {detalle}",
                  causa='presupuesto_reinicios')


def reacciona_a_desconocido(ruta_nivel, detalle, dia_negociacion):
    """§2: DESCONOCIDO fuerza a PLANO (aplanar las dos, confirmando cada
    una -- responsabilidad de quien llama) y sube a N2 ("parar hasta
    intervención humana", que aquí empieza por no reabrir hoy; si la
    causa persiste al día siguiente, quien llama puede volver a subir).

    `dia_negociacion` obligatorio, mismo motivo que en
    `reacciona_a_liquidacion_forzosa`."""
    return sube_a(ruta_nivel, 'N2', motivo=f"estado DESCONOCIDO: {detalle}", causa='reconciliacion',
                  dia_negociacion=dia_negociacion)


def reacciona_a_violacion_tamanos(ruta_nivel, detalle):
    """Catálogo G, caso 10 / puerta R3 §6.10: "forzar tamaños que no se
    corresponden entre patas -> reconciliación lo caza -> N3". A
    diferencia de DESCONOCIDO (falta de información) o de una pata sola
    dentro de ventana (TRANSICION, esperado), un tamaño que NO corresponde
    con dos patas SÍ leídas es una violación del invariante que solo se
    explica por un bug propio o una manipulación -- más grave que N2."""
    return sube_a(ruta_nivel, 'N3', motivo=f"tamaños de las dos patas no corresponden: {detalle}",
                  causa='posicion_descuadrada')


def reacciona_a_degradacion_tesoreria(ruta_nivel, dia_negociacion, dia_degradacion):
    """DECISION_DEGRADACION_N3.md (revisión operador 21-08-2026): R-7.2
    ("caja - retirado < -muro") es PEGAJOSA por norma -- una vez `True`,
    nunca se revierte sola. N1/N2 se bajan solos ("al desaparecer la
    causa" / "al día siguiente"), pero con una causa que por diseño NUNCA
    desaparece, usarlos prometería un descenso automático que o no llega
    (N1) o llega mañana reanudando la operación con el capital ya
    perforado (N2). N3 es el único nivel cuya salida es "humano,
    explícito" -- exactamente la semántica de un estado irreversible.
    Cruzar el muro significa "el capital ya no cubre lo que el circuito
    compromete" (`muro = capital - margen y exposición comprometidos`):
    abrir mañana sería operar el hedge sin el margen que la propia
    identidad de cobertura da por supuesto.

    Quien llama (`bot/bucle_del_dia.py`) invoca esto TODOS los días en que
    `estado['degradado']` sea `True`, sin comprobar antes el nivel actual
    -- `sube_a()` ya es monótono/idempotente, así que si un humano bajase
    el nivel a mano con `degradado` todavía `True`, el bot vuelve a subir
    a N3 solo, al día siguiente (la barrera no es decorativa).

    IMPORTANTE (norma, no solo del bot): el modelo congelado (`modelo/`,
    `pipeline3.py`) NO simula el régimen degradado -- mide una
    probabilidad, no opera un capital, así que sigue corriendo más allá
    del cruce del muro sin parar (fiel a lo que es: un simulador). Por
    tanto, TODO resultado del modelo (P(degradar), la cifra de $/mes, el
    replay de 504 días) correspondiente a un linaje que cruza el muro deja
    de ser válido a partir de ese día -- el bot, aquí, SÍ para; el modelo
    seguía midiendo. No son la misma cosa y no hay que confundirlas."""
    motivo = f"degradación de tesorería (R-7.2), día {dia_negociacion}"
    if dia_degradacion is not None and dia_degradacion != dia_negociacion:
        motivo += f" (fijada originalmente el día {dia_degradacion})"
    return sube_a(ruta_nivel, 'N3', motivo=motivo, causa='degradacion_tesoreria')
