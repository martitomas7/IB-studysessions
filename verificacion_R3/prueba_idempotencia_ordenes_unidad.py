# -*- coding: utf-8 -*-
"""R3 (D8.5, unidad): bot/idempotencia_ordenes.py en aislamiento -- el
testigo intención/resultado, sin reintento ciego. La integración completa
(matar el proceso entre escribe_intencion y marca_resultado, reiniciar,
reconciliar) vive en verificacion_R3/prueba_idempotencia_ordenes.py, una
vez exista bot/reconciliacion.py."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import idempotencia_ordenes as I

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


DIR = "/tmp/prueba_idempotencia_ordenes_unidad"
shutil.rmtree(DIR, ignore_errors=True)

print("=== 1. sin intención ni resultado: resultado_de() = None (nunca se mandó) ===")
ok("resultado_de() de un intent_id que no existe -> None",
   I.resultado_de(DIR, "1:eval:0:abre") is None)

print("\n=== 2. escribe_intencion() -> AÚN sin resultado: sigue None (mandado, no confirmado) ===")
I.escribe_intencion(DIR, "1:eval:0:abre", dict(cuenta_hedge="CTA-HEDGE", cuenta_prop="CTA-PROP", m=4, k=10))
ok("tras escribe_intencion, resultado_de() SIGUE None -- la intención sola no basta",
   I.resultado_de(DIR, "1:eval:0:abre") is None)
ok("intenciones_sin_resultado() SÍ la detecta (día 1)",
   I.intenciones_sin_resultado(DIR, dia_negociacion=1) == ["1:eval:0:abre"])

print("\n=== 3. marca_resultado() -> resultado_de() devuelve el resultado, deja de estar pendiente ===")
I.marca_resultado(DIR, "1:eval:0:abre", dict(order_id_hedge="FAKE-1", order_id_prop="FAKE-2"))
r = I.resultado_de(DIR, "1:eval:0:abre")
ok("resultado_de() devuelve exactamente lo registrado",
   r == dict(order_id_hedge="FAKE-1", order_id_prop="FAKE-2"), r)
ok("ya NO aparece en intenciones_sin_resultado()",
   I.intenciones_sin_resultado(DIR, dia_negociacion=1) == [])

print("\n=== 4. intenciones_sin_resultado() filtra por día -- no mezcla días distintos ===")
I.escribe_intencion(DIR, "2:funded:0:bracket", dict(cuenta="CTA-PROP"))
ok("día 1 sigue sin pendientes (la de hoy ya se resolvió)",
   I.intenciones_sin_resultado(DIR, dia_negociacion=1) == [])
ok("día 2 SÍ tiene la pendiente de hoy", I.intenciones_sin_resultado(DIR, dia_negociacion=2)
   == ["2:funded:0:bracket"])

print("\n=== 5. escritura atómica -- no hay .tmp huérfano tras varias escrituras ===")
huerfanos = [f for f in os.listdir(DIR) if f.startswith('.') and f.endswith('.tmp')]
ok("ningún .tmp huérfano queda tras las escrituras normales", huerfanos == [], huerfanos)

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
