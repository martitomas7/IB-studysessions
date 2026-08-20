# -*- coding: utf-8 -*-
"""R3 (D8.4, paso 3): `resolucion_en_vivo._refleja_escalar`/`_refleja_bar`
son la réplica escalar de `calendario.refleja_camino`, anclada en
`p0_real` en vez de `pc_crudo[0]`. Se verifica sobre una malla de
`(p0_real, direccion, ndn, nu)` que da EXACTAMENTE lo mismo que
`calendario.refleja_camino` -- golden de equivalencia matemática, no
"parece correcto"."""
import os
import random
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import calendario
from bot.resolucion_en_vivo import CAMINO_NO_USADO_EN_VIVO, _refleja_bar, _refleja_escalar

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


print("=== 1. _refleja_escalar() da EXACTAMENTE lo mismo que calendario.refleja_camino "
      "sobre una malla de casos, dirección larga y corta ===")
rng = random.Random(20260820)
discrepancias = []
for _ in range(2000):
    p0_real = rng.uniform(4000.0, 6000.0)
    direccion = rng.choice([1, -1])
    x = p0_real + rng.uniform(-50.0, 50.0)
    # camino crudo de control: [p0_real, x] -- el ancla real es pc_crudo[0]=p0_real
    esperado = calendario.refleja_camino([p0_real, x], [p0_real, x], [p0_real, x], direccion)[2][1]
    obtenido = _refleja_escalar(x, p0_real, direccion)
    if abs(esperado - obtenido) > 1e-9:
        discrepancias.append((p0_real, direccion, x, esperado, obtenido))
ok(f"0 discrepancias sobre 2000 combinaciones aleatorias (p0_real, dirección, x)",
   len(discrepancias) == 0, discrepancias[:5])

print("\n=== 2. dirección larga es identidad pura (sin reflejar) ===")
ok("direccion=1 -> x sin cambios", _refleja_escalar(5010.0, 5000.0, 1) == 5010.0)
ok("direccion=1 -> x sin cambios incluso muy alejado", _refleja_escalar(4800.0, 5000.0, 1) == 4800.0)

print("\n=== 3. dirección corta refleja alrededor de p0_real ===")
ok("direccion=-1, x=5010 con p0_real=5000 -> 4990 (2*5000-5010)",
   _refleja_escalar(5010.0, 5000.0, -1) == 4990.0)
ok("reflejar dos veces vuelve al original (involución)",
   _refleja_escalar(_refleja_escalar(5010.0, 5000.0, -1), 5000.0, -1) == 5010.0)

print("\n=== 4. consistencia de negocio: el nivel de suelo/objetivo reflejado da el dx correcto ===")
# suelo real de una posición CORTA: el precio SUBE a p0_real+ndn -> dx (en
# convención reflejada, lo que sesion.resolver_dia/DetectorEnVivo esperan)
# tiene que salir exactamente -ndn, igual que R-3.3 "toca suelo".
p0_real, ndn, nu = 5000.0, 8.0, 8.0
precio_stop_real = _refleja_escalar(p0_real - ndn, p0_real, -1)     # = p0_real + ndn (subida real)
ok("precio_stop_real para dirección corta es p0_real+ndn (el suelo real está ARRIBA en corto)",
   abs(precio_stop_real - (p0_real + ndn)) < 1e-9, precio_stop_real)
dx_si_toca_stop = _refleja_escalar(precio_stop_real, p0_real, -1) - p0_real
ok("si el precio real toca exactamente el nivel del stop, dx reflejado = -ndn (R-3.3, 'toca suelo')",
   abs(dx_si_toca_stop - (-ndn)) < 1e-9, dx_si_toca_stop)

precio_limite_real = _refleja_escalar(p0_real + nu, p0_real, -1)    # = p0_real - nu (bajada real)
ok("precio_limite_real para dirección corta es p0_real-nu (el objetivo real está ABAJO en corto)",
   abs(precio_limite_real - (p0_real - nu)) < 1e-9, precio_limite_real)
dx_si_toca_limite = _refleja_escalar(precio_limite_real, p0_real, -1) - p0_real
ok("si el precio real toca exactamente el nivel del límite, dx reflejado = +nu (objetivo)",
   abs(dx_si_toca_limite - nu) < 1e-9, dx_si_toca_limite)

print("\n=== 5. _refleja_bar(): intercambio alto↔bajo en dirección corta, equivalente a "
      "calendario.refleja_camino barra a barra ===")
discrepancias_bar = []
for _ in range(500):
    p0_real = rng.uniform(4000.0, 6000.0)
    direccion = rng.choice([1, -1])
    ph_b = p0_real + rng.uniform(0.0, 30.0)
    pl_b = p0_real - rng.uniform(0.0, 30.0)
    pc_b = p0_real + rng.uniform(-15.0, 15.0)
    ph_esp, pl_esp, pc_esp = calendario.refleja_camino([p0_real, ph_b], [p0_real, pl_b],
                                                        [p0_real, pc_b], direccion)
    ph_obt, pl_obt, pc_obt = _refleja_bar(ph_b, pl_b, pc_b, p0_real, direccion)
    if (abs(ph_esp[1] - ph_obt) > 1e-9 or abs(pl_esp[1] - pl_obt) > 1e-9
            or abs(pc_esp[1] - pc_obt) > 1e-9):
        discrepancias_bar.append((p0_real, direccion, ph_b, pl_b, pc_b))
ok("0 discrepancias sobre 500 barras aleatorias (incluido el intercambio alto/bajo en corto)",
   len(discrepancias_bar) == 0, discrepancias_bar[:5])

print("\n=== 6. CAMINO_NO_USADO_EN_VIVO: falla RUIDOSO si algo lo indexa ===")
try:
    len(CAMINO_NO_USADO_EN_VIVO)
    fallo_len = False
except AssertionError as ex:
    fallo_len = 'ciclo_vida.py' in str(ex)
ok("len(CAMINO_NO_USADO_EN_VIVO) lanza AssertionError nombrando la invariante rota", fallo_len)
try:
    CAMINO_NO_USADO_EN_VIVO[5]
    fallo_getitem = False
except AssertionError as ex:
    fallo_getitem = 'ciclo_vida.py' in str(ex)
ok("CAMINO_NO_USADO_EN_VIVO[5] lanza AssertionError nombrando la invariante rota", fallo_getitem)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
