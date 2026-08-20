# -*- coding: utf-8 -*-
"""config.py · D0 · 05_ORDEN_DE_CONSTRUCCION.md

Responsabilidad UNICA (02_ARQUITECTURA.md §2): cargar y validar 03_CONFIG.yaml,
exponerlo como objeto de solo lectura, y comprobar los DERIVADOS con assert.
PROHIBIDO (mismo §2): contener cualquier numero de negocio.

Regla R2 (04_GUARDARRAILES): "un numero que no este en 03_CONFIG.yaml no existe."
Por eso NINGUNA formula de este fichero usa un literal numerico de negocio -- cada
formula de _validar_derivados() referencia EXCLUSIVAMENTE otras claves del propio
YAML, nunca una constante fija. Las unicas cifras que aparecen abajo (1e-2, 65536)
son tolerancia de comparacion en coma flotante y tamano de bloque de lectura de
fichero: ingenieria, no negocio -- ver la nota junto a cada una.
"""
import hashlib
import os
import yaml


class ConfigInvalidoError(RuntimeError):
    """Un DERIVADO no cuadra, o cualquier otra violacion fatal de 03_CONFIG.yaml.
    Lanzarla es "fallar al arrancar" (05_ORDEN D0): no hay modo degradado para
    una config que no se puede confiar."""


class Inmutable:
    """Envoltorio de solo lectura, recursivo, sobre el dict/list que carga PyYAML.

    No es un dict real: no expone __setitem__ ni __setattr__ que funcionen, asi
    que 03_CONFIG.yaml, una vez cargado, no se puede mutar por accidente desde
    otro modulo (Arquitectura §2: "config.py: PROHIBIDO contener cualquier numero"
    se lee tambien como "nadie mas escribe numeros aqui").
    """
    __slots__ = ('_datos',)

    def __init__(self, datos):
        object.__setattr__(self, '_datos', datos)

    def __getitem__(self, clave):
        return _envolver(self._datos[clave])

    def __getattr__(self, nombre):
        try:
            return _envolver(self._datos[nombre])
        except KeyError:
            raise AttributeError(
                f"'{nombre}' no existe en 03_CONFIG.yaml bajo este nodo (R2: "
                f"si el numero que buscas no esta aqui, no existe -- pregunta)")

    def __contains__(self, clave):
        return clave in self._datos

    def __iter__(self):
        return iter(self._datos)

    def __len__(self):
        return len(self._datos)

    def __eq__(self, otro):
        return self._datos == (otro._datos if isinstance(otro, Inmutable) else otro)

    def __repr__(self):
        return f"Inmutable({self._datos!r})"

    def __setattr__(self, nombre, valor):
        raise TypeError("03_CONFIG.yaml es de solo lectura (R2): no se puede asignar")

    def __setitem__(self, clave, valor):
        raise TypeError("03_CONFIG.yaml es de solo lectura (R2): no se puede asignar")

    def valor(self):
        """Si este nodo es una entrada {valor:..., unidad:..., tipo:...}, devuelve
        el propio valor (numero/bool/str). Si el nodo no tiene 'valor', es que
        hace falta seguir navegando -- eso es un error de uso, no de config."""
        if isinstance(self._datos, dict) and 'valor' in self._datos:
            return self._datos['valor']
        raise TypeError(
            f"este nodo no es una entrada con 'valor' (claves: {list(self._datos)}) "
            f"-- navega mas antes de pedir .valor()")


def _envolver(x):
    if isinstance(x, dict):
        return Inmutable(x)
    if isinstance(x, list):
        return tuple(_envolver(e) for e in x)
    return x


def _v(datos_crudos, *ruta):
    """Navega `ruta` sobre el dict CRUDO (antes de envolver en Inmutable) y
    desenvuelve {'valor': x} -> x. Vive aparte de Inmutable.valor() porque
    _validar_derivados() necesita trabajar sobre el dict crudo, antes de saber
    si el fichero es valido -- Inmutable solo se construye SI la validacion pasa."""
    x = datos_crudos
    for p in ruta:
        x = x[p]
    return x['valor'] if isinstance(x, dict) and 'valor' in x else x


def _validar_derivados(c):
    """Recalcula cada campo DERIVADO de 03_CONFIG.yaml a partir de las claves de
    las que la propia config dice que se deriva (Arquitectura §2: 'comprueba los
    DERIVADOS con assert'). Ninguna formula de aqui abajo contiene un literal de
    negocio: cada termino es _v(c, ...) sobre una clave del YAML. Devuelve la
    lista de discrepancias -- vacia significa que todo cuadra."""
    fallos = []

    # tolerancia de comparacion en coma flotante -- NO es un numero de negocio.
    # Los DERIVADOS se publican redondeados a 3 decimales (ver comentario del
    # propio 03_CONFIG.yaml), asi que una tolerancia mayor que el redondeo es
    # correcta aqui; el mismo valor que usa tests/comprueba_config.py:TOL.
    TOL = 1e-2

    def cerca(nombre, esperado, escrito):
        if abs(esperado - escrito) > TOL:
            fallos.append(f"{nombre}: 03_CONFIG.yaml dice {escrito}, recalculado da {esperado}")

    fx = _v(c, 'capital', 'fx_eur_usd')
    cerca('capital.capital_usd',
          _v(c, 'capital', 'capital_eur') * fx,
          _v(c, 'capital', 'capital_usd'))
    cerca('circuito.capital_usd',
          _v(c, 'capital', 'capital_usd'),
          _v(c, 'circuito', 'capital_usd'))
    cerca('sizing.b_eval_usd',
          _v(c, 'sizing', 'b_eval_eur') * fx,
          _v(c, 'sizing', 'b_eval_usd'))
    cerca('sizing.b_fun_usd',
          _v(c, 'sizing', 'b_fun_eur') * fx,
          _v(c, 'sizing', 'b_fun_usd'))

    margen = _v(c, 'hedge_broker', 'margen_intradia_usd')
    pares = (_v(c, 'sizing', 'm_fun') * margen + _v(c, 'sizing', 'exp_fun_usd')
             + _v(c, 'sizing', 'm_eval') * margen + _v(c, 'sizing', 'exp_eval_usd'))
    cerca('tesoreria.pares_usd', pares, _v(c, 'tesoreria', 'pares_usd'))
    cerca('tesoreria.holgura_usd',
          _v(c, 'capital', 'capital_usd') - _v(c, 'tesoreria', 'pares_usd'),
          _v(c, 'tesoreria', 'holgura_usd'))

    buf = _v(c, 'proveedor', 'buf_usd')
    w = _v(c, 'proveedor', 'w_bruto_usd')
    sp = _v(c, 'proveedor', 'split')
    co = _v(c, 'proveedor', 'cons')
    esc = c['proveedor']['escalera_retiro']
    cerca('proveedor.escalera_retiro.ciclo_1.umbral_bruto_usd',
          buf + w, _v(esc, 'ciclo_1', 'umbral_bruto_usd'))
    cerca('proveedor.escalera_retiro.ciclo_1.retira_usd',
          sp * w, _v(esc, 'ciclo_1', 'retira_usd'))
    cerca('proveedor.escalera_retiro.ciclo_1.tope_dia_usd',
          (buf + w) * co, _v(esc, 'ciclo_1', 'tope_dia_usd'))
    cerca('proveedor.escalera_retiro.ciclos_2_a_5.umbral_bruto_usd',
          w, _v(esc, 'ciclos_2_a_5', 'umbral_bruto_usd'))
    cerca('proveedor.escalera_retiro.ciclos_2_a_5.retira_usd',
          sp * w, _v(esc, 'ciclos_2_a_5', 'retira_usd'))
    cerca('proveedor.escalera_retiro.ciclos_2_a_5.tope_dia_usd',
          w * co, _v(esc, 'ciclos_2_a_5', 'tope_dia_usd'))

    return fallos


def _sha256_fichero(ruta):
    h = hashlib.sha256()
    with open(ruta, 'rb') as fh:
        # 65536 = tamano de bloque de lectura -- ingenieria de E/S, no negocio.
        for bloque in iter(lambda: fh.read(65536), b''):
            h.update(bloque)
    return h.hexdigest()


def cargar(ruta=None):
    """Carga 03_CONFIG.yaml, valida los DERIVADOS y devuelve (config_inmutable, sha256).

    Lanza ConfigInvalidoError si el fichero no existe o algun DERIVADO no cuadra --
    eso ES "fallar al arrancar" (05_ORDEN D0). Deliberadamente NO se ejecuta a la
    importacion del modulo: quien arranca el bot llama a cargar() explicitamente,
    para que importar `config` en un test no dependa de que exista un fichero.
    """
    if ruta is None:
        ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             '03_CONFIG.yaml')
    if not os.path.isfile(ruta):
        raise ConfigInvalidoError(f"no existe 03_CONFIG.yaml en {ruta}")

    with open(ruta, 'r', encoding='utf-8') as fh:
        crudo = yaml.safe_load(fh)

    fallos = _validar_derivados(crudo)
    if fallos:
        raise ConfigInvalidoError(
            "03_CONFIG.yaml tiene DERIVADOS que no cuadran con su propia formula "
            "(R2 -- el fichero llego roto o fue editado a mano):\n"
            + "\n".join(f"  - {x}" for x in fallos)
        )

    checksum = _sha256_fichero(ruta)
    return Inmutable(crudo), checksum


_CACHE = None


def obtener(ruta=None):
    """Punto de acceso comodo para el resto del bot: `from bot import config;
    config.obtener().sizing.m_eval.valor()`. Memoiza sobre la ruta por defecto
    (ruta=None) para no releer y re-validar el YAML en cada llamada; con una
    ruta explicita SIEMPRE recarga (asi los tests pueden pasar configs propias
    sin heredar el cache de otro test)."""
    global _CACHE
    if ruta is not None:
        cfg, _ = cargar(ruta)
        return cfg
    if _CACHE is None:
        _CACHE, _ = cargar()
    return _CACHE


if __name__ == '__main__':
    cfg, sha = cargar()
    print(f"03_CONFIG.yaml cargado y validado. sha256={sha}")
    # meta.version y meta.fecha_congelacion son strings sueltos en el YAML (sin
    # {valor:...}), por eso se leen directos, sin .valor() -- a diferencia de
    # las entradas de negocio, que sí llevan {valor, unidad, tipo, fuente}.
    print(f"version={cfg.meta.version}  congelado={cfg.meta.fecha_congelacion}")
