# -*- coding: utf-8 -*-
"""comandos.py · D-C · 05_ORDEN_DE_CONSTRUCCION.md · 08_LABORATORIO.md §7.3

La cola de intención en fichero que le permite al dashboard (HTML autocontenido,
sin servidor) actuar sobre el bot: escribe una intención, el bot la lee y la
ejecuta -- el bot sigue siendo lo único que toca al bróker, que es lo que hace
esto auditable.

**Sobre "exactamente una vez" (08_LABORATORIO.md §7.3).** Sin una transacción
de dos fases no hay forma de garantizar "exactamente una vez" en sentido
estricto para una acción arbitraria que se cae a mitad. Lo que SÍ se puede
garantizar, y es lo que hace este módulo, es la combinación de dos cosas:
  1. **Como mucho una CLAIM concurrente** -- un marcador `<id>.tomado` creado
     con apertura exclusiva (`O_CREAT|O_EXCL`, atómica a nivel de sistema de
     ficheros: si dos procesos lo intentan a la vez, solo uno gana).
  2. **Acciones idempotentes por diseño** -- cada `ejecutor` que se le pasa a
     `procesa_comando()` está construido para que repetirlo no cambie el
     resultado: aplanar sobre una posición ya plana es un no-op del propio
     puerto de `07_ADAPTADOR_NT8.md` §1; fijar `parada_total=True` dos veces
     es lo mismo que una vez; una desviación de Clase B con el mismo `id` no
     se re-registra dos veces (ver `bot/ciclo_vida.py` o quien la aplique).
Con las dos, si el proceso se cae DESPUÉS de ejecutar y ANTES de escribir el
resultado, al reiniciar el comando sigue viéndose "sin resultado" -- se
re-ejecuta, y como es idempotente, el resultado OBSERVABLE es idéntico a
haberlo ejecutado una sola vez. Eso es lo que exige la comprobación 10 de
`08_LABORATORIO.md` §8.
"""
import json
import os
from datetime import datetime, timezone


class ComandoInvalidoError(RuntimeError):
    """Un comando mal formado, o de un tipo desconocido."""


# 08_LABORATORIO.md §7.2: las clases de acción, textuales.
CLASE_A = frozenset({'aplanar_ambas', 'parada_dia', 'parada_total', 'cancelar_orden'})
CLASE_B = frozenset({'empalme', 'contra', 'emergencia', 'pausa_eval'})
CAMPOS_OBLIGATORIOS = frozenset({'id', 'ts_pared', 'tipo', 'parametros', 'caduca_en', 'quien'})


def clase_de(tipo):
    """'A', 'B', o None si el tipo no se reconoce (08_LABORATORIO.md §7.2:
    Clase C -- aumentar exposición o tocar la norma -- NO tiene comandos:
    no existe un tipo de Clase C que este modulo sepa nombrar)."""
    if tipo in CLASE_A:
        return 'A'
    if tipo in CLASE_B:
        return 'B'
    return None


def ahora_iso():
    return datetime.now(timezone.utc).isoformat()


def _parsea(ts_iso):
    return datetime.fromisoformat(ts_iso)


def escribe_comando(directorio, comando):
    """Escribe `comandos/<id>.json`. Append-only: si el `id` ya existe, es un
    error de uso -- los comandos no se editan, se escribe uno nuevo con `id`
    distinto (08_LABORATORIO.md §7.3: 'nunca se editan ni se borran')."""
    faltan = CAMPOS_OBLIGATORIOS - set(comando)
    if faltan:
        raise ComandoInvalidoError(f"faltan campos obligatorios: {sorted(faltan)}")
    clase = clase_de(comando['tipo'])
    if clase is None:
        raise ComandoInvalidoError(
            f"tipo de comando desconocido o de Clase C (prohibida en el dashboard): "
            f"{comando['tipo']!r}")
    if clase == 'B' and 'duracion_dias' not in comando.get('parametros', {}):
        # 08_LABORATORIO.md §11 (revisión 3): "D-C debe preguntar, no inventar"
        # una duración por defecto -- por eso NO hay valor por defecto aquí: un
        # comando de Clase B sin duración explícita es inválido, sin excepción.
        raise ComandoInvalidoError(
            "un comando de Clase B exige 'duracion_dias' explícito en 'parametros' -- "
            "no hay valor por defecto (08_LABORATORIO.md §11, decisión abierta cerrada "
            "así: sin número inventado)")
    os.makedirs(directorio, exist_ok=True)
    ruta = os.path.join(directorio, f"{comando['id']}.json")
    if os.path.exists(ruta):
        raise ComandoInvalidoError(f"ya existe un comando con id={comando['id']} (append-only)")
    tmp = ruta + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(comando, fh, indent=1, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)
    return ruta


def _ruta_resultado(directorio, id_):
    return os.path.join(directorio, f"{id_}.resultado.json")


def _ruta_tomado(directorio, id_):
    return os.path.join(directorio, f"{id_}.tomado")


def lee_pendientes(directorio, clase=None):
    """Lista los comandos SIN `<id>.resultado.json` todavía, opcionalmente
    filtrados por clase ('A' o 'B') -- 08_LABORATORIO.md §7.3: Clase A se
    sondea de forma continua durante la sesión, Clase B solo en el punto de
    decisión del día siguiente. Orden estable (por nombre de fichero, que
    incluye el `id`) para que el procesamiento sea determinista."""
    if not os.path.isdir(directorio):
        return []
    pendientes = []
    for nombre in sorted(os.listdir(directorio)):
        if not nombre.endswith('.json') or nombre.endswith('.resultado.json') \
                or nombre.endswith('.tmp'):
            continue
        id_ = nombre[:-len('.json')]
        if os.path.exists(_ruta_resultado(directorio, id_)):
            continue
        with open(os.path.join(directorio, nombre), encoding='utf-8') as fh:
            comando = json.load(fh)
        if clase is not None and clase_de(comando['tipo']) != clase:
            continue
        pendientes.append(comando)
    return pendientes


def _escribe_resultado(directorio, id_, resultado):
    ruta = _ruta_resultado(directorio, id_)
    tmp = ruta + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(resultado, fh, indent=1, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)


def valor_efectivo(palanca, valor_certificado, estado, dia_actual, valor_apagado=False):
    """08_LABORATORIO.md §7.5: el valor REAL que debe usar el orquestador para
    una palanca de Clase B (empalme/contra/emergencia/pausa_eval) es el
    certificado de `03_CONFIG.yaml`, SALVO que exista una desviación activa
    para esa palanca y ese día en `estado.desviaciones_activas`, en cuyo caso
    la palanca está APAGADA (las cuatro son interruptores on/off, "desactivar
    / reactivar" -- 08_LABORATORIO.md §7.2). Esta es la ÚNICA función que debe
    decidir el valor efectivo de una palanca de Clase B en todo el bot: si
    `ciclo_vida.py`/`calendario.py` leen la palanca por otro camino (el config
    certificado directamente), están estructuralmente ciegos a una desviación
    activa (romperían R-3, no reflejarían el interruptor) -- pero el reverso
    también es cierto y es la garantía que pide la comprobación 12: NINGÚN
    código puede apagar una palanca sin pasar por aquí, porque aquí es donde
    vive la ÚNICA lectura de `desviaciones_activas` que decide el comportamiento.

    `valor_apagado`: qué significa "apagada" para ESTA palanca. Las tres
    booleanas (`empalme`, `emergencia`, `pausa_eval`) usan el default `False`.
    `contra` no es booleana -- es un número de días (`contra_dias`) -- así que
    su llamador pasa `valor_apagado=0` (desactivar CONTRA = 0 días de
    persistencia forzada, el mismo efecto que "sin CONTRA" en `calendario.py`).

    CABLEADA (revisión operador 20-08-2026): `ciclo_vida.py::procesa_dia_eval`
    (empalme, pausa_eval) y `toma_sub` (emergencia) ya llaman a esta función;
    `calendario.py::sortea_direccion` la llama para `contra`. Con
    `desviaciones_activas=[]` (el caso de todo el replay de 504 días, que no
    simula ningún comando), esta función SIEMPRE devuelve `valor_certificado`
    sin tocarlo -- por construcción, no por casualidad -- así que cablearla no
    puede, por sí sola, mover ni un dígito del resultado del replay."""
    activa = any(d['palanca'] == palanca and d['desde_dia'] <= dia_actual < d['hasta_dia']
                 for d in estado.get('desviaciones_activas', []))
    return valor_apagado if activa else valor_certificado


def procesa_comando(directorio, comando, ejecutor, ahora_iso_str=None):
    """Procesa UN comando: caducidad -> claim (idempotencia) -> ejecuta ->
    resultado. `ejecutor(comando) -> dict` es el callable que de verdad hace
    la acción -- este módulo no sabe QUÉ hace un comando, solo que se
    ejecuta como mucho una vez de forma observable (ver docstring del
    módulo). `ahora_iso_str` es inyectable para pruebas deterministas.

    Devuelve el dict de resultado (el mismo que queda en
    `<id>.resultado.json`): `{id, estado, ts_resultado, ...}`, con `estado`
    ∈ {'CADUCADO', 'EJECUTADO'}."""
    ahora = ahora_iso_str or ahora_iso()
    id_ = comando['id']

    if _parsea(ahora) > _parsea(comando['caduca_en']):
        resultado = dict(id=id_, estado='CADUCADO', ts_resultado=ahora,
                          motivo=f"caducó en {comando['caduca_en']}, procesado en {ahora}")
        _escribe_resultado(directorio, id_, resultado)
        return resultado

    ruta_tomado = _ruta_tomado(directorio, id_)
    try:
        fd = os.open(ruta_tomado, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        pass  # ya reclamado -- por otra ejecución concurrente, o por una caída
              # previa entre "ejecutar" y "escribir el resultado" (recuperación)

    # Se llega aquí SIEMPRE que no exista <id>.resultado.json todavía --
    # incluida la recuperación tras caída. Seguro porque `ejecutor` es
    # idempotente por diseño (ver docstring del módulo).
    salida = ejecutor(comando)
    resultado = dict(id=id_, estado='EJECUTADO', ts_resultado=ahora, salida=salida)
    _escribe_resultado(directorio, id_, resultado)
    return resultado
