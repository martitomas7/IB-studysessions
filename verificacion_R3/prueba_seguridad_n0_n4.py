# -*- coding: utf-8 -*-
"""R3 (10_SEGURIDAD.md §1-§5, ORDEN_DE_TRABAJO_D8.md §2): el marco
PLANO/CUBIERTO/TRANSICION, la clasificación CONOCIDO-*/DESCONOCIDO, y la
escalera N0-N4 -- "sube sola, solo baja con un humano". Cubre
explícitamente la puerta que pide el pedido de trabajo: "una prueba por
cada transición automática, y una que demuestre que NO existe ningún
camino de código que baje de N3 o N4 sin intervención"."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import seguridad as S, estado as E

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def _lanza(fn):
    """True si `fn()` lanza S.NivelInvalidoError -- False si no lanza nada."""
    try:
        fn()
        return False
    except S.NivelInvalidoError:
        return True


DIR = "/tmp/prueba_seguridad_n0_n4"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)
RUTA_NIVEL = os.path.join(DIR, "nivel.json")


print("=== §1: clasifica_posicion() -- PLANO / CUBIERTO / TRANSICION / VIOLACION ===")
ok("las dos en cero -> PLANO",
   S.clasifica_posicion(0, 0, m_esperado=4, k_esperado=10, en_ventana_transicion=False) == 'PLANO')
ok("las dos abiertas con tamaños que corresponden -> CUBIERTO",
   S.clasifica_posicion(-4, 10, m_esperado=4, k_esperado=10, en_ventana_transicion=False) == 'CUBIERTO')
ok("las dos abiertas con un tamaño que NO corresponde -> VIOLACION (catálogo G, caso 10)",
   S.clasifica_posicion(-3, 10, m_esperado=4, k_esperado=10, en_ventana_transicion=False) == 'VIOLACION')
ok("una sola pata DENTRO de la ventana de transición -> TRANSICION",
   S.clasifica_posicion(-4, 0, m_esperado=4, k_esperado=10, en_ventana_transicion=True) == 'TRANSICION')
ok("una sola pata FUERA de la ventana -> VIOLACION ('no es un estado: es una emergencia')",
   S.clasifica_posicion(-4, 0, m_esperado=4, k_esperado=10, en_ventana_transicion=False) == 'VIOLACION')

print("\n=== §2: clasifica_conocimiento() -- DESCONOCIDO es la regla contraintuitiva ===")
ok("las dos legibles y PLANO -> CONOCIDO-SEGURO",
   S.clasifica_conocimiento(True, True, 'PLANO') == 'CONOCIDO-SEGURO')
ok("las dos legibles y CUBIERTO -> CONOCIDO-SEGURO",
   S.clasifica_conocimiento(True, True, 'CUBIERTO') == 'CONOCIDO-SEGURO')
ok("las dos legibles y TRANSICION -> CONOCIDO-INSEGURO",
   S.clasifica_conocimiento(True, True, 'TRANSICION') == 'CONOCIDO-INSEGURO')
ok("las dos legibles y VIOLACION -> CONOCIDO-INSEGURO",
   S.clasifica_conocimiento(True, True, 'VIOLACION') == 'CONOCIDO-INSEGURO')
ok("hedge NO legible (aunque prop sí, y aunque PLANO sería 'seguro') -> DESCONOCIDO de todos modos",
   S.clasifica_conocimiento(False, True, 'PLANO') == 'DESCONOCIDO')
ok("prop NO legible -> DESCONOCIDO",
   S.clasifica_conocimiento(True, False, 'CUBIERTO') == 'DESCONOCIDO')
ok("ninguna legible -> DESCONOCIDO",
   S.clasifica_conocimiento(False, False, None) == 'DESCONOCIDO')

print("\n=== §3: sube_a() -- escala sola, monótona, nunca baja ===")
ok("arranque en frío: nivel_actual = N0", S.nivel_actual(RUTA_NIVEL) == 'N0')
ok("N0 -> N1 (transición automática 1)",
   S.sube_a(RUTA_NIVEL, 'N1', 'causa de prueba', causa='reconciliacion') == 'N1')
ok("nivel.json persiste el cambio", S.nivel_actual(RUTA_NIVEL) == 'N1')
ok("N1 -> N2 (transición automática 2)",
   S.sube_a(RUTA_NIVEL, 'N2', 'causa de prueba', causa='reconciliacion') == 'N2')
ok("intentar 'subir' a N1 (menos severo que N2 actual) NO hace nada -- sube_a nunca baja",
   S.sube_a(RUTA_NIVEL, 'N1', 'no debería aplicar', causa='reconciliacion') == 'N2')
ok("sigue en N2 tras el intento anterior", S.nivel_actual(RUTA_NIVEL) == 'N2')
ok("N2 -> N4 (salto directo, transición automática 3 -- escalar no exige pasar por N3)",
   S.sube_a(RUTA_NIVEL, 'N4', 'causa de prueba', causa='estado_corrupto') == 'N4')
ok("historial registra las tres subidas con quien='sistema'",
   all(h['quien'] == 'sistema' for h in S.lee_nivel(RUTA_NIVEL)['historial']))
ok("causa desconocida -- sube_a() la rechaza (vocabulario tipado, "
   "DECISION_DEGRADACION_N3.md §3)",
   _lanza(lambda: S.sube_a(RUTA_NIVEL, 'N1', 'motivo', causa='inventada_sin_ton_ni_son')))

print("\n=== §3: LA PUERTA CRÍTICA -- ningún camino de código baja de N3/N4 sin humano ===")
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR)
S.sube_a(RUTA_NIVEL, 'N3', 'fabricado para la prueba', causa='posicion_descuadrada')
try:
    S.baja_automatica(RUTA_NIVEL, 'N2', 'intento de bajar N3 sin humano')
    disparo_mal = True
except S.NivelInvalidoError as ex:
    disparo_mal = False
    detalle_n3 = str(ex)
ok("baja_automatica() DESDE N3 lanza NivelInvalidoError -- nunca desciende en silencio",
   not disparo_mal, detalle_n3 if not disparo_mal else "NO LANZÓ")
ok("tras el intento fallido, sigue en N3 (nivel.json no se tocó)", S.nivel_actual(RUTA_NIVEL) == 'N3')

S.sube_a(RUTA_NIVEL, 'N4', 'fabricado para la prueba', causa='estado_corrupto')
try:
    S.baja_automatica(RUTA_NIVEL, 'N1', 'intento de bajar N4 sin humano')
    disparo_mal4 = True
except S.NivelInvalidoError:
    disparo_mal4 = False
ok("baja_automatica() DESDE N4 lanza NivelInvalidoError igual", not disparo_mal4)
ok("sigue en N4", S.nivel_actual(RUTA_NIVEL) == 'N4')

# exhaustivo: NINGUNA combinación (nivel_actual en {N3,N4}) x (nivel_nuevo en NIVELES)
# logra bajar vía baja_automatica -- la propia lista blanca de niveles-solo-humano
# se re-verifica aquí en vez de darla por buena de nombre.
combinaciones_bloqueadas = 0
for nivel_alto in ('N3', 'N4'):
    shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR)
    S.sube_a(RUTA_NIVEL, nivel_alto, 'fabricado', causa='reconciliacion')
    for nivel_bajo in S.NIVELES:
        if S._RANGO[nivel_bajo] >= S._RANGO[nivel_alto]:
            continue
        try:
            S.baja_automatica(RUTA_NIVEL, nivel_bajo, 'barrido exhaustivo')
        except S.NivelInvalidoError:
            combinaciones_bloqueadas += 1
esperadas = sum(1 for n in ('N3', 'N4') for m in S.NIVELES if S._RANGO[m] < S._RANGO[n])
ok(f"barrido exhaustivo: TODAS las {esperadas} combinaciones (nivel_alto en {{N3,N4}} x nivel_nuevo "
   f"más bajo) quedan bloqueadas por baja_automatica()",
   combinaciones_bloqueadas == esperadas, f"{combinaciones_bloqueadas}/{esperadas}")

print("\n=== §3: baja_automatica() SÍ funciona desde N1/N2 (transiciones automáticas legítimas) ===")
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR)
S.sube_a(RUTA_NIVEL, 'N1', 'causa temporal', causa='reconciliacion')
ok("N1 -> N0 automático ('solo, al desaparecer la causa') -- transición automática 4",
   S.baja_automatica(RUTA_NIVEL, 'N0', 'causa desaparecida') == 'N0')
S.sube_a(RUTA_NIVEL, 'N2', 'fin de sesión con pérdida', causa='reconciliacion')
ok("N2 -> N0 automático ('solo, al día siguiente') -- transición automática 5",
   S.baja_automatica(RUTA_NIVEL, 'N0', 'nuevo día de negociación') == 'N0')

print("\n=== §3: baja_humana() SÍ funciona desde N3/N4, y exige 'quien' real ===")
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR)
S.sube_a(RUTA_NIVEL, 'N3', 'fabricado', causa='posicion_descuadrada')
try:
    S.baja_humana(RUTA_NIVEL, 'N0', quien='sistema', motivo='intento de colarse')
    colo = True
except S.NivelInvalidoError:
    colo = False
ok("baja_humana() con quien='sistema' se RECHAZA -- esa palabra está reservada",
   not colo)
ok("N3 -> N0 con un humano real y explícito", S.baja_humana(RUTA_NIVEL, 'N0', quien='operador_martitomas7',
   motivo='revisado manualmente, causa resuelta') == 'N0')
ok("el historial registra quien='operador_martitomas7', no 'sistema'",
   S.lee_nivel(RUTA_NIVEL)['historial'][-1]['quien'] == 'operador_martitomas7')

print("\n=== 10_SEGURIDAD.md §6, puerta #5: corromper estado.json de tres formas -> N4, nunca N0 ===")
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR)
DIR_ESTADO = os.path.join(DIR, "estados")
os.makedirs(DIR_ESTADO)

def _intenta_arrancar_y_reacciona(ruta_estado_rota):
    """Simula lo que hará D8.4 al arrancar: cargar estado.json, y SI falla
    con EstadoInvalidoError, reaccionar subiendo a N4 -- sin adivinar, sin
    reconstruir a la brava (§4.D)."""
    try:
        E.cargar(ruta_estado_rota)
        return False  # no debería llegar aquí -- las tres formas de abajo SIEMPRE rompen
    except E.EstadoInvalidoError as ex:
        S.reacciona_a_estado_invalido(RUTA_NIVEL, str(ex))
        return True

# forma 1: fichero truncado (JSON roto)
ruta1 = os.path.join(DIR_ESTADO, "roto1.json")
with open(ruta1, 'w') as fh:
    fh.write('{"version_esquema": 1, "dia_neg')  # truncado a propósito
ok("forma 1 (JSON truncado) reacciona subiendo a N4", _intenta_arrancar_y_reacciona(ruta1)
   and S.nivel_actual(RUTA_NIVEL) == 'N4')

# forma 2: JSON válido pero le falta un campo esperado
import json as _json
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR_ESTADO)
ruta2 = os.path.join(DIR_ESTADO, "roto2.json")
_json.dump({"version_esquema": 1, "caja": 0.0}, open(ruta2, 'w'))  # sin 'recamara' ni el resto
ok("forma 2 (campo ausente) reacciona subiendo a N4", _intenta_arrancar_y_reacciona(ruta2)
   and S.nivel_actual(RUTA_NIVEL) == 'N4')

# forma 3: JSON válido, campos presentes, pero un invariante fatal roto
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR_ESTADO)
from bot import config as C
_, checksum = C.cargar()
st_roto3 = E.nuevo("v10", checksum)
st_roto3["recamara"]["n"] = 99  # invariante 2 roto: n != len(dormidas)
ruta3 = os.path.join(DIR_ESTADO, "roto3.json")
_json.dump(st_roto3, open(ruta3, 'w'))
ok("forma 3 (invariante fatal roto) reacciona subiendo a N4", _intenta_arrancar_y_reacciona(ruta3)
   and S.nivel_actual(RUTA_NIVEL) == 'N4')
ok("NUNCA quedó en N0 en ninguna de las tres formas (re-vista sobre el registro completo)",
   all(h['a'] != 'N0' for h in S.lee_nivel(RUTA_NIVEL)['historial']))

print("\n=== 10_SEGURIDAD.md §6, puerta #3: liquidación forzosa (D8.3) -> N2, cableado con seguridad.py ===")
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR)
from bot.adaptador_falso import AdaptadorFalso
from bot.deteccion_liquidacion import detecta_liquidacion_forzosa, resuelve_liquidacion_forzosa
a = AdaptadorFalso()
oid_prop = a.abrir("CTA-PROP", "MES", 1, 10); a.leer_estado_orden(oid_prop)
oid_hedge = a.abrir("CTA-HEDGE", "MES", -1, 4); a.leer_estado_orden(oid_hedge)
a.fuerza_posicion_externa("CTA-PROP", "MES", 0)
if detecta_liquidacion_forzosa(a, "CTA-PROP", "MES", cantidad_esperada=10, ordenes_propias_conocidas=[]):
    r = resuelve_liquidacion_forzosa(a, "CTA-HEDGE", "MES")
    S.reacciona_a_liquidacion_forzosa(RUTA_NIVEL, "detectada en R3")
ok("tras la liquidación forzosa detectada y resuelta, el nivel sube a N2",
   S.nivel_actual(RUTA_NIVEL) == 'N2')

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
