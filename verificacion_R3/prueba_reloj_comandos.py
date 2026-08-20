# -*- coding: utf-8 -*-
"""R3 (10_SEGURIDAD.md §7, pedido de trabajo D8 §2, hueco nuevo): "mover el
reloj de pared atrás -> un comando caducado no debe resucitar".

`bot/comandos.py::procesa_comando()` decide caducidad comparando `ahora`
(por defecto `datetime.now()`, inyectable por pruebas) contra
`comando['caduca_en']`. Si el reloj de pared del sistema retrocede (paso de
NTP, reloj de VM, manipulación deliberada) DESPUÉS de que el bot ya haya
observado un instante más tardío, un comando que en tiempo real ya está
muerto podría evaluarse con un `ahora` artificialmente temprano y
EJECUTARSE de verdad -- no solo marcarse mal. Se reproduce primero contra
una reimplementación fiel de la función SIN el blindaje (nunca se toca
`bot/comandos.py` para fabricar el fallo -- se reconstruye aparte, mismo
patrón que `prueba_estado_corrupto.py::_cargar_viejo_sin_blindar`), y luego
se confirma que la función real, con `_avanza_reloj_max_visto()`, no cae en
la misma trampa."""
import os
import shutil
import sys
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import comandos as C

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def _procesa_comando_sin_blindar(directorio, comando, ejecutor, ahora_iso_str):
    """Reconstrucción fiel de `procesa_comando()` TAL COMO ERA antes de este
    hueco (sin `_avanza_reloj_max_visto`) -- usa `ahora_iso_str` en crudo,
    sin ningún tope. Vive aquí, no en bot/comandos.py, para no tener que
    romper el código real a propósito (R6: no se toca el módulo para
    fabricar el fallo)."""
    ahora = ahora_iso_str
    id_ = comando['id']
    if datetime.fromisoformat(ahora) > datetime.fromisoformat(comando['caduca_en']):
        resultado = dict(id=id_, estado='CADUCADO', ts_resultado=ahora)
        return resultado
    salida = ejecutor(comando)
    return dict(id=id_, estado='EJECUTADO', ts_resultado=ahora, salida=salida)


DIR = os.path.join(AQUI, '_prueba_reloj_comandos')
shutil.rmtree(DIR, ignore_errors=True)

# Guion: el bot ya observó un "ahora" tardío (T_alto) en algún momento --
# p.ej. procesando otro comando, o simplemente el latido regular. Luego el
# reloj de pared del sistema retrocede a T_bajo. Se crea un comando NUEVO
# cuyo caduca_en (T_medio) queda ENTRE los dos -- en tiempo real (T_alto) ya
# caducó, pero con el reloj retrocedido (T_bajo) parecería que todavía no.
T_BAJO   = '2026-08-20T09:00:00+00:00'
T_MEDIO  = '2026-08-20T09:30:00+00:00'   # caduca_en del comando
T_ALTO   = '2026-08-20T10:00:00+00:00'   # ya observado ANTES de que el reloj retroceda

print("=== 1. SIN blindar: el reloj retrocede y un comando caducado en tiempo real SE EJECUTA ===")
C.escribe_comando(DIR, dict(id='c_resucita', ts_pared=T_BAJO, tipo='parada_total',
                             parametros={}, caduca_en=T_MEDIO, quien='op'))
contador_roto = {'n': 0}
def ejecutor_roto(cmd):
    contador_roto['n'] += 1
    return dict(hecho=True)

# El bot ya vio T_ALTO (p.ej. al procesar otro comando/latido) -- eso no se
# modela aquí porque la version SIN blindar no tiene memoria de reloj
# ninguna; se pasa directo T_BAJO, que es justo el escenario de fallo.
r_roto = _procesa_comando_sin_blindar(DIR, C.lee_pendientes(DIR)[0], ejecutor_roto,
                                        ahora_iso_str=T_BAJO)
ok("BUG reproducido: sin blindar, un comando caducado en tiempo real (T_ALTO > caduca_en) "
   "se EJECUTA porque el reloj retrocedido (T_BAJO) lo ve como 'todavía no caducado'",
   r_roto['estado'] == 'EJECUTADO' and contador_roto['n'] == 1, r_roto)

shutil.rmtree(DIR, ignore_errors=True)

print("\n=== 2. CON blindar (bot/comandos.py real): el mismo escenario NO resucita el comando ===")
# Paso A: el bot observa T_ALTO primero -- p.ej. procesando un comando previo
# cualquiera que en ese momento con ese reloj es perfectamente normal.
C.escribe_comando(DIR, dict(id='c_previo', ts_pared=T_BAJO, tipo='parada_total',
                             parametros={}, caduca_en=T_ALTO, quien='op'))
C.procesa_comando(DIR, C.lee_pendientes(DIR)[0], lambda cmd: dict(hecho=True),
                   ahora_iso_str=T_ALTO)
ok("tras el paso A, la marca de reloj máximo visto queda persistida en T_ALTO",
   os.path.exists(C._ruta_reloj_max_visto(DIR)))

# Paso B: el reloj del sistema retrocede a T_BAJO, y llega un comando NUEVO
# cuyo caduca_en (T_MEDIO) ya quedó atrás en tiempo real (T_ALTO > T_MEDIO).
C.escribe_comando(DIR, dict(id='c_resucita', ts_pared=T_BAJO, tipo='parada_total',
                             parametros={}, caduca_en=T_MEDIO, quien='op'))
contador_real = {'n': 0}
def ejecutor_real(cmd):
    contador_real['n'] += 1
    return dict(hecho=True)
pendiente = [c for c in C.lee_pendientes(DIR) if c['id'] == 'c_resucita'][0]
r_real = C.procesa_comando(DIR, pendiente, ejecutor_real, ahora_iso_str=T_BAJO)

ok("blindado: el comando se marca CADUCADO (no resucita) pese al reloj retrocedido",
   r_real['estado'] == 'CADUCADO', r_real)
ok("blindado: el ejecutor NUNCA se llamó", contador_real['n'] == 0)
ok("el resultado persistido en disco también dice CADUCADO",
   __import__('json').load(open(C._ruta_resultado(DIR, 'c_resucita')))['estado'] == 'CADUCADO')

print("\n=== 3. el blindaje SOLO frena retrocesos -- un avance normal del reloj sigue funcionando ===")
shutil.rmtree(DIR, ignore_errors=True)
C.escribe_comando(DIR, dict(id='c_normal', ts_pared=T_BAJO, tipo='parada_total',
                             parametros={}, caduca_en=T_MEDIO, quien='op'))
r_normal_vivo = C.procesa_comando(DIR, C.lee_pendientes(DIR)[0], lambda cmd: dict(hecho=True),
                                   ahora_iso_str=T_BAJO)  # antes de caducar, reloj avanzando normal
ok("un comando procesado ANTES de caducar (reloj avanzando con normalidad) SÍ se ejecuta",
   r_normal_vivo['estado'] == 'EJECUTADO', r_normal_vivo)

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
