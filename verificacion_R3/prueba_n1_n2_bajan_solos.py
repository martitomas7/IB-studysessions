# -*- coding: utf-8 -*-
"""D9 §3.1 (ORDEN_DE_TRABAJO_D9.md, autorización explícita R6): "N1 y N2
deben bajar solos" -- cierra el hueco que `bot/bucle_del_dia.py` documentaba
desde D8 ("N1/N2 se desescalan solos en otro punto... 'cuándo exactamente'
no está grounded en este diseño") y que `verificacion_R3/prueba_caos.py`
solo simulaba.

Semántica, EXACTA a 10_SEGURIDAD.md §3 (no inventada aquí):
- **N1** baja sola **al desaparecer la causa** -- sin esperar ningún día.
- **N2** baja sola **al día siguiente** -- Y SOLO SI la causa ya no está.
- **N3/N4** nunca bajan solos, pase lo que pase.

Mecanismo (`bot/seguridad.py::intenta_bajar_automatico()`): recibe un
tri-estado `causa_sigue_activa` (`False`=desaparecida, `True`=presente,
`None`=no se pudo verificar -- equivalente a DESCONOCIDO otra vez, nunca
baja) que el LLAMADOR calcula re-corriendo el MISMO clasificador que
disparó la subida (`bot/reconciliacion.py::verifica_reconciliado()`,
de solo lectura) -- este test prueba `intenta_bajar_automatico()` en
aislamiento, con el tri-estado fabricado directamente (la integración
real, con `verifica_reconciliado()` de verdad dentro de
`bucle_del_dia()`, ya está cubierta en `prueba_caos.py` §3-4).

Los 6 escenarios son los que pidió el operador, uno por uno."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import seguridad as S

DIR = "/tmp/prueba_n1_n2_bajan_solos"
RUTA_NIVEL = os.path.join(DIR, "nivel.json")

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def _reinicia():
    shutil.rmtree(DIR, ignore_errors=True)
    os.makedirs(DIR)


print("=== 1. N1 por conexión caída -> recuperada -> baja sola (sin esperar ningún día) ===")
_reinicia()
S.sube_a(RUTA_NIVEL, 'N1', 'conexión caída', causa='reconciliacion', dia_negociacion=5)
ok("sube a N1", S.nivel_actual(RUTA_NIVEL) == 'N1')
S.intenta_bajar_automatico(RUTA_NIVEL, dia_negociacion=5, causa_sigue_activa=False)
ok("recuperada EL MISMO día (dia=5, la causa ya subió y bajó dentro de la misma jornada) "
   "-> N1 baja YA, sin esperar 'al día siguiente' (esa regla es solo de N2)",
   S.nivel_actual(RUTA_NIVEL) == 'N0')

print("\n=== 2. N1 por UNKNOWN -> no baja nunca ===")
_reinicia()
S.sube_a(RUTA_NIVEL, 'N1', 'conexión caída', causa='reconciliacion', dia_negociacion=5)
for dia_futuro in (5, 6, 100):
    S.intenta_bajar_automatico(RUTA_NIVEL, dia_negociacion=dia_futuro, causa_sigue_activa=None)
    ok(f"causa_sigue_activa=None (no verificable) en el día {dia_futuro} -> sigue en N1, "
       f"nunca baja sola por muchos días que pasen",
       S.nivel_actual(RUTA_NIVEL) == 'N1')

print("\n=== 3. N2 baja al día siguiente, NO el mismo ===")
_reinicia()
S.sube_a(RUTA_NIVEL, 'N2', 'DESCONOCIDO', causa='reconciliacion', dia_negociacion=5)
ok("sube a N2", S.nivel_actual(RUTA_NIVEL) == 'N2')
S.intenta_bajar_automatico(RUTA_NIVEL, dia_negociacion=5, causa_sigue_activa=False)
ok("MISMO día (5), causa ya desaparecida -> NO baja (N2 exige 'al día siguiente')",
   S.nivel_actual(RUTA_NIVEL) == 'N2')
S.intenta_bajar_automatico(RUTA_NIVEL, dia_negociacion=6, causa_sigue_activa=False)
ok("día SIGUIENTE (6 > 5), causa desaparecida -> AHORA sí baja a N0",
   S.nivel_actual(RUTA_NIVEL) == 'N0')

print("\n=== 4. N2 con la causa presente -> no baja (aunque haya pasado un día) ===")
_reinicia()
S.sube_a(RUTA_NIVEL, 'N2', 'DESCONOCIDO', causa='reconciliacion', dia_negociacion=5)
S.intenta_bajar_automatico(RUTA_NIVEL, dia_negociacion=9, causa_sigue_activa=True)
ok("4 días después (9 > 5) pero causa_sigue_activa=True -> sigue en N2, el paso del "
   "tiempo NO sustituye a que la causa desaparezca", S.nivel_actual(RUTA_NIVEL) == 'N2')

print("\n=== 5. N3/N4 no bajan ni forzando (ni con auto-descenso, ni con el paso de los días) ===")
for nivel_alto, causa in (('N3', 'posicion_descuadrada'), ('N4', 'estado_corrupto')):
    _reinicia()
    S.sube_a(RUTA_NIVEL, nivel_alto, 'fabricado para la prueba', causa=causa, dia_negociacion=5)
    for causa_sigue_activa in (False, True, None):
        S.intenta_bajar_automatico(RUTA_NIVEL, dia_negociacion=999, causa_sigue_activa=causa_sigue_activa)
        ok(f"{nivel_alto} con causa_sigue_activa={causa_sigue_activa}, día 999 -> sigue en "
           f"{nivel_alto}, intenta_bajar_automatico() ni lo intenta (no es N1/N2)",
           S.nivel_actual(RUTA_NIVEL) == nivel_alto)
    lanzo = False
    try:
        S.baja_automatica(RUTA_NIVEL, 'N0', 'intento directo')
    except S.NivelInvalidoError:
        lanzo = True
    ok(f"baja_automatica() DIRECTA desde {nivel_alto} sigue rechazándose (barrera de más abajo "
       f"intacta, esta función nueva no la debilita)", lanzo)

print("\n=== 6. N1 -> N2 -> N1: incidentes independientes, sin saltar niveles ni perder la causa ===")
_reinicia()
# incidente A: N1 por reconciliacion, día 1 -> se resuelve el mismo día
S.sube_a(RUTA_NIVEL, 'N1', 'incidente A', causa='reconciliacion', dia_negociacion=1)
S.intenta_bajar_automatico(RUTA_NIVEL, dia_negociacion=1, causa_sigue_activa=False)
ok("incidente A (N1) resuelto, de vuelta en N0", S.nivel_actual(RUTA_NIVEL) == 'N0')

# incidente B: N2 por reconciliacion, día 3 -> se resuelve el día 4 (al siguiente)
S.sube_a(RUTA_NIVEL, 'N2', 'incidente B', causa='reconciliacion', dia_negociacion=3)
ok("incidente B escala directo a N2 (nunca pasa por N1 -- sube_a() no encadena niveles "
   "intermedios, salta al que corresponda)", S.nivel_actual(RUTA_NIVEL) == 'N2')
S.intenta_bajar_automatico(RUTA_NIVEL, dia_negociacion=3, causa_sigue_activa=False)
ok("incidente B, mismo día 3 -> NO baja (N2 exige el día siguiente, sin bleed del "
   "incidente A ya resuelto)", S.nivel_actual(RUTA_NIVEL) == 'N2')
S.intenta_bajar_automatico(RUTA_NIVEL, dia_negociacion=4, causa_sigue_activa=False)
ok("incidente B resuelto el día 4, de vuelta en N0", S.nivel_actual(RUTA_NIVEL) == 'N0')

# incidente C: un NUEVO N1 por reconciliacion, día 6 -- confirma que ni el día ni la
# causa del incidente B (ya resuelto) contaminan este tercero.
S.sube_a(RUTA_NIVEL, 'N1', 'incidente C', causa='reconciliacion', dia_negociacion=6)
ok("incidente C (N1 de nuevo) escala limpio, sin arrastrar nada de B", S.nivel_actual(RUTA_NIVEL) == 'N1')
historial = S.lee_nivel(RUTA_NIVEL)['historial']
ok("el historial completo tiene las 5 transiciones exactas, en orden, sin ninguna perdida "
   "ni ninguna de más", [(h['de'], h['a']) for h in historial] ==
   [('N0', 'N1'), ('N1', 'N0'), ('N0', 'N2'), ('N2', 'N0'), ('N0', 'N1')], historial)
S.intenta_bajar_automatico(RUTA_NIVEL, dia_negociacion=6, causa_sigue_activa=False)
ok("incidente C (N1) resuelto el MISMO día 6 -- N1 nunca hereda la regla 'día siguiente' "
   "de haber estado en N2 momentos antes", S.nivel_actual(RUTA_NIVEL) == 'N0')

print("\n=== R3: la comprobación del día-siguiente discrimina de verdad (no es un no-op) ===")
print("  (implementación deliberadamente rota: si se comparara con >= en vez de >, el ")
print("  escenario 3 -- 'mismo día no baja' -- pasaría a bajar en el acto. Se rompió a mano ")
print("  monkeypatcheando la función, se vio fallar el mismo assert de arriba, y se restauró.")
_reinicia()
S.sube_a(RUTA_NIVEL, 'N2', 'DESCONOCIDO', causa='reconciliacion', dia_negociacion=5)
_orig_rango = dict(S._RANGO)
def _intenta_bajar_ROTO(ruta, dia_negociacion, causa_sigue_activa):
    """Copia deliberadamente rota: usa >= en vez de > -- 'el mismo día' también bajaría."""
    registro = S.lee_nivel(ruta)
    actual = registro.get('nivel', 'N0')
    if actual not in ('N1', 'N2') or causa_sigue_activa is None or causa_sigue_activa:
        return actual
    historial = registro.get('historial', [])
    ultimo = historial[-1] if historial else {}
    if actual == 'N1':
        return S.baja_automatica(ruta, 'N0', motivo='roto')
    dia_fijado = ultimo.get('dia_negociacion')
    if dia_fijado is not None and dia_negociacion >= dia_fijado:   # BUG: >= en vez de >
        return S.baja_automatica(ruta, 'N0', motivo='roto')
    return actual
_intenta_bajar_ROTO(RUTA_NIVEL, dia_negociacion=5, causa_sigue_activa=False)
ok("la versión ROTA (>=) SÍ baja el mismo día -- confirma que el test de arriba (escenario 3) "
   "habría cazado este bug si la implementación real tuviera este fallo",
   S.nivel_actual(RUTA_NIVEL) == 'N0')

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
shutil.rmtree(DIR, ignore_errors=True)
if n_ok != len(resultados):
    sys.exit(1)
