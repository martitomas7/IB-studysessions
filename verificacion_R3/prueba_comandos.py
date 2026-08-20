# -*- coding: utf-8 -*-
"""Verificación R3 de bot/comandos.py: comprobaciones 9 y 10 de 08_LABORATORIO.md §8."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)  # ing/ es el padre de verificacion_R3/ en el paquete entregado
sys.path.insert(0, ING)

from bot import comandos as C

DIR = os.path.join(AQUI, '_prueba_comandos')
if os.path.exists(DIR):
    shutil.rmtree(DIR)

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


print("=== validación de escritura (Clase B exige duracion_dias, sin default) ===")
try:
    C.escribe_comando(DIR, dict(id='c1', ts_pared='2026-08-20T10:00:00+00:00', tipo='empalme',
                                 parametros={}, caduca_en='2026-08-20T12:00:00+00:00', quien='op'))
    ok("Clase B sin duracion_dias -> rechazado", False)
except C.ComandoInvalidoError as ex:
    ok("Clase B sin duracion_dias -> rechazado", True, str(ex))

print("=== COMPROBACIÓN 9: comando caducado no se ejecuta ===")
shutil.rmtree(DIR, ignore_errors=True)
C.escribe_comando(DIR, dict(id='c_caducado', ts_pared='2026-08-20T10:00:00+00:00',
                             tipo='parada_total', parametros={},
                             caduca_en='2026-08-20T10:05:00+00:00', quien='op'))
contador = {'n': 0}
def ejecutor(cmd):
    contador['n'] += 1
    return dict(hecho=True)
r = C.procesa_comando(DIR, C.lee_pendientes(DIR)[0], ejecutor,
                       ahora_iso_str='2026-08-20T12:00:00+00:00')   # 2h despues de caducar
ok("resultado = CADUCADO", r['estado'] == 'CADUCADO', r)
ok("el ejecutor NUNCA se llamó", contador['n'] == 0)
ok("queda escrito <id>.resultado.json", os.path.exists(os.path.join(DIR, 'c_caducado.resultado.json')))

print("=== COMPROBACIÓN 10: comando ejecutado dos veces (crash entre ejecutar y escribir resultado) ===")
shutil.rmtree(DIR, ignore_errors=True)
C.escribe_comando(DIR, dict(id='c_kill', ts_pared='2026-08-20T10:00:00+00:00',
                             tipo='parada_total', parametros={},
                             caduca_en='2026-08-20T23:59:59+00:00', quien='op'))
estado_bot = {'parada_total': False}
llamadas = {'n': 0}
def ejecutor_idempotente(cmd):
    llamadas['n'] += 1
    estado_bot['parada_total'] = True   # idempotente: fijar True dos veces == una vez
    return dict(parada_total=estado_bot['parada_total'])

# --- 1a "ejecucion": simula el proceso cayendose DESPUES de ejecutar, ANTES
#     de escribir el resultado -- se llama al ejecutor pero NO a _escribe_resultado.
cmd = C.lee_pendientes(DIR)[0]
os.close(os.open(C._ruta_tomado(DIR, cmd['id']), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
ejecutor_idempotente(cmd)   # la accion SI corrio...
# ... pero el proceso "murio" aqui: nunca se llego a escribir el resultado.
ok("tras la 'caida', no existe resultado.json todavia",
   not os.path.exists(C._ruta_resultado(DIR, cmd['id'])))

# --- reinicio: el bot vuelve a arrancar y relee pendientes (sigue sin resultado) ---
pendientes_tras_reinicio = C.lee_pendientes(DIR)
ok("tras reiniciar, el comando SIGUE viendose pendiente (sin resultado)",
   len(pendientes_tras_reinicio) == 1 and pendientes_tras_reinicio[0]['id'] == 'c_kill')
r2 = C.procesa_comando(DIR, pendientes_tras_reinicio[0], ejecutor_idempotente,
                        ahora_iso_str='2026-08-20T10:00:05+00:00')
ok("se re-ejecuta tras el reinicio (llamadas al ejecutor = 2)", llamadas['n'] == 2)
ok("el RESULTADO OBSERVABLE es identico (parada_total sigue en True, no 'True True')",
   estado_bot['parada_total'] is True)
ok("resultado final = EJECUTADO", r2['estado'] == 'EJECUTADO', r2)
ok("una tercera lectura ya NO ve el comando como pendiente", C.lee_pendientes(DIR) == [])

shutil.rmtree(DIR, ignore_errors=True)

print("=== COMPROBACIÓN 12: una desviación de Clase B que no deja rastro se detecta ===")
from bot import estado as E, config
cfg, checksum = config.cargar()
st = E.nuevo(cfg.meta.version, checksum)

print("    12a. sin desviaciones: la palanca vale lo certificado")
ok("empalme efectivo = True (certificado, sin desviacion)",
   C.valor_efectivo('empalme', True, st, dia_actual=10) is True)

print("    12b. CORRECTO: desviacion registrada -> la palanca SI se apaga, y solo en su ventana")
st_bien = dict(st)
st_bien['desviaciones_activas'] = [
    {"palanca": "empalme", "desde_dia": 10, "hasta_dia": 13, "quien": "operador",
     "ts_pared": "2026-08-20T10:00:00+00:00"}
]
f = E.validar(st_bien, checksum)
ok("estado.json con la desviacion bien registrada pasa validar()", f == [], f)
ok("dentro de la ventana (dia 11): efectivo = False (apagada)",
   C.valor_efectivo('empalme', True, st_bien, dia_actual=11) is False)
ok("fuera de la ventana (dia 13, caduco solo): efectivo = True otra vez",
   C.valor_efectivo('empalme', True, st_bien, dia_actual=13) is True)

print("    12c. ROTO: se apaga el comportamiento SIN registrar -- no hay otro camino en el codigo")
print("         para tocar el valor efectivo de una palanca que NO sea valor_efectivo(); la")
print("         propia funcion es la unica lectura de desviaciones_activas de todo el bot, asi")
print("         que 'apagar en silencio' exigiria evitarla -- y entonces el estado.json resultante")
print("         (desviaciones_activas=[]) sencillamente no explica por que el comportamiento")
print("         difiere del certificado: es justo lo que 08_LABORATORIO.md §7.5 dice que hace E6,")
print("         marcar/excluir un periodo sin desviacion registrada que no compara bien con el modelo.")
st_roto = dict(st)   # desviaciones_activas = [] -- "apagado" en otro sitio del codigo, sin registrar
ok("con desviaciones_activas vacio, valor_efectivo() NUNCA apaga nada por su cuenta",
   C.valor_efectivo('empalme', True, st_roto, dia_actual=11) is True,
   "si el codigo roto quiere 'False' tiene que evitar esta funcion entera -- no hay bypass DENTRO de ella")

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "="*70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
sys.exit(0 if n_ok == len(resultados) else 1)
