# -*- coding: utf-8 -*-
"""R3 (REVISION_REV5.md §3, 20-08-2026): `tesoreria.py::muro_dinamico()` tiene
que leer `circuito.capital_usd`, NO `capital.capital_usd` -- son el mismo
número en el `03_CONFIG.yaml` real (mientras solo haya un circuito), así que
un test contra el fichero real NO puede distinguir "lee el campo correcto"
de "lee el otro, que hoy da la casualidad de que vale lo mismo". Se
construye, en memoria, una vista `Inmutable` de `03_CONFIG.yaml` donde los
dos DIFIEREN a propósito (rompiendo aposta la igualdad que
`_validar_derivados` normalmente exige, pero sin pasar por `config.cargar()`
-- esa validación es justo lo que se está esquivando a propósito, porque lo
que se prueba es `muro_dinamico()`, no `config.cargar()`) y se confirma que
el muro sale del valor de `circuito`, nunca del de `capital`."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

import yaml  # ya lo usa bot/config.py -- disponible en el entorno

from bot import config, tesoreria as T

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


RUTA_REAL = os.path.join(ING, "03_CONFIG.yaml")

with open(RUTA_REAL) as fh:
    datos = yaml.safe_load(fh)

capital_original = datos["capital"]["capital_usd"]["valor"]
capital_circuito_divergente = capital_original + 500000.0  # deliberadamente MUY distinto
datos["circuito"]["capital_usd"]["valor"] = capital_circuito_divergente

print(f"=== capital.capital_usd={capital_original}  circuito.capital_usd={capital_circuito_divergente} "
      f"(a propósito distintos) ===")

# NOTA (segundo bug real del propio arnés, cazado al EJECUTAR la primera
# versión de este test, no solo al escribirla): `config.cargar(ruta)` ya no
# admite este fichero -- `_validar_derivados` (bot/config.py) exige
# exactamente que circuito.capital_usd == capital.capital_usd, así que pasar
# por `cargar()` para construir la config de prueba lanza ConfigInvalidoError
# antes de llegar a probar nada. Eso es correcto para `cargar()` (es lo que
# el propio DERIVADO existe para pillar -- ver prueba de config rota más
# abajo en el resto de la batería), pero significa que ESTE test, que no
# prueba `cargar()` sino `muro_dinamico()`, tiene que construir el objeto
# `Inmutable` directamente, sin pasar por la validación de derivados.
cfg_prueba = config.Inmutable(datos)

# IMPORTANTE (bug real del propio arnés de prueba, cazado al escribir esto):
# `config.obtener(ruta)` con una ruta explícita NO toca el cache global de
# `ruta=None` (ver bot/config.py::obtener -- devuelve una config fresca pero
# deja `_CACHE` intacto). Como `tesoreria.py` llama SIEMPRE a
# `config.obtener()` sin argumentos, pasarle una ruta aquí no dirige nada --
# hacía falta parchear el propio `config.obtener` para que, DURANTE esta
# comprobación, devuelva la config de prueba -- mismo patrón que
# `prueba_detector_en_vivo.py` (envolver-y-restaurar la función real, nunca
# tocar tests/modelo, R6).
_obtener_original = config.obtener
config.obtener = lambda *a, **kw: cfg_prueba
try:
    muro_con_prueba = T.muro_dinamico(0.0, 0.0)
finally:
    config.obtener = _obtener_original

margen = cfg_prueba.sesion.cal_rth.margen_usd.valor()
m_fun = cfg_prueba.sizing.m_fun.valor()
exp_fun = cfg_prueba.sizing.exp_fun_usd.valor()
muro_esperado_si_lee_circuito = capital_circuito_divergente - (m_fun * margen + exp_fun)
muro_esperado_si_leyera_capital = capital_original - (m_fun * margen + exp_fun)

print(f"  muro_dinamico(0,0) con la config de prueba: {muro_con_prueba}")
print(f"  esperado SI lee circuito.capital_usd: {muro_esperado_si_lee_circuito}")
print(f"  esperado SI leyera capital.capital_usd (el bug viejo): {muro_esperado_si_leyera_capital}")

ok("muro_dinamico() sale del valor de circuito.capital_usd, NO de capital.capital_usd",
   abs(muro_con_prueba - muro_esperado_si_lee_circuito) < 1e-6, muro_con_prueba)
ok("y NO coincide con lo que daría si (por error) leyera capital.capital_usd",
   abs(muro_con_prueba - muro_esperado_si_leyera_capital) > 1000, muro_con_prueba)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
