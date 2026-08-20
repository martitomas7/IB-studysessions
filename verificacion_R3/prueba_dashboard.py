# -*- coding: utf-8 -*-
"""Verificación R3 de bot/dashboard.py + bot/contexto_dashboard.py:
comprobaciones 6, 7 y 8 de 08_LABORATORIO.md §8 (dashboard como instrumento)."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)  # ing/ es el padre de verificacion_R3/ en el paquete entregado
sys.path.insert(0, ING)

from bot import config, estado as E
from bot import contexto_dashboard as CD
from bot import dashboard as D

cfg, checksum = config.cargar()
RANCIO_SEG = cfg.dashboard.rancio_seg.valor()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


def estado_base():
    st = E.nuevo(cfg.meta.version, checksum)
    st['eval']['activa'] = False
    return st


print(f"=== COMPROBACIÓN 6: un dato rancio pintado como si estuviera vivo (umbral={RANCIO_SEG}s) ===")
st = estado_base()
diario = dict(dia=1, direccion=1, ventana='RTH', eventos={}, fin_de_dia={})
# snapshot VIVO: hace 1 segundo
snap_vivo = dict(estado_feed='TIEMPO_REAL', bid=6000.0, ask=6000.25, ts_monotono=99.0)
ctx = CD.construye(st, diario, [diario], ahora_iso='x', ahora_monotono=100.0,
                    mercado_snapshots=[snap_vivo])
html_vivo = D.genera_html(ctx)
ok("con un snapshot de hace 1s, E1 SI se publica (disponible)",
   ctx['mercado_friccion']['disponible'] is True)

# snapshot RANCIO: hace mucho mas que el umbral, pero SIGUE marcado TIEMPO_REAL
# -- la implementacion ROTA seria una que solo mira estado_feed y nunca compara
# ts_monotono contra "ahora": pintaria el numero igual de "fresco".
ahora_lejos = 99.0 + RANCIO_SEG + 500.0
snap_rancio = dict(estado_feed='TIEMPO_REAL', bid=6000.0, ask=6000.25, ts_monotono=99.0)
ctx_rancio = CD.construye(st, diario, [diario], ahora_iso='x', ahora_monotono=ahora_lejos,
                           mercado_snapshots=[snap_rancio])
# la funcion de ayuda que SI implementa la regla de frescura (usada por dashboard.py):
from bot.dashboard import _frescura
clase, texto = _frescura(snap_rancio['ts_monotono'], ahora_lejos, RANCIO_SEG)
ok("un snapshot de hace horas se marca 'rancio', no 'vivo'", clase == 'rancio', texto)
clase_v, texto_v = _frescura(snap_vivo['ts_monotono'], 100.0, RANCIO_SEG)
ok("un snapshot de hace 1s se marca 'vivo'", clase_v == 'vivo', texto_v)
html_dia_rancio = D.genera_html(ctx_rancio)
ok("el snapshot rancio SI se le APLICA la clase 'frescura-rancio' al elemento pintado (no solo definida en CSS)",
   'class="frescura frescura-rancio"' in html_dia_rancio and 'rancio · hace' in html_dia_rancio)
html_dia_vivo = D.genera_html(ctx)
ok("el snapshot vivo se le aplica 'frescura-vivo', NO 'frescura-rancio', al elemento pintado",
   'class="frescura frescura-vivo"' in html_dia_vivo
   and 'class="frescura frescura-rancio"' not in html_dia_vivo)

print("=== COMPROBACIÓN 7: un n insuficiente presentado como conclusión ===")
st2 = estado_base()
diarios_pocos = [dict(dia=i+1, direccion=1, ventana='RTH',
                       eventos=dict(intentos=1, aprobaciones=0, muertes_funded=0, resets=0,
                                    emergencias=0, recompras=0), fin_de_dia={})
                  for i in range(2)]   # solo 2 dias -> n=2, muy por debajo de 25
ctx7 = CD.construye(st2, diarios_pocos[-1], diarios_pocos, ahora_iso='x')
fila_intentos = next(f for f in ctx7['modelo_vs_realidad'] if f['evento'] == 'intentos de eval')
ok("con n=2 (<<25 de la tabla de 08_LABORATORIO.md §5), concluye=False",
   fila_intentos['n'] == 2 and fila_intentos['concluye'] is False, fila_intentos)
html7 = D.genera_html(ctx7)
ok("el HTML dice 'todavía no concluye', no pinta un veredicto con n insuficiente",
   'todavía no concluye' in html7)

diarios_muchos = diarios_pocos * 20   # emula 40 dias con eventos -> n=40 >= 25
ctx7b = CD.construye(st2, diarios_muchos[-1], diarios_muchos, ahora_iso='x')
fila_intentos_b = next(f for f in ctx7b['modelo_vs_realidad'] if f['evento'] == 'intentos de eval')
ok("con n>=25, SI concluye (deja de decir 'todavia no')",
   fila_intentos_b['n'] >= 25 and fila_intentos_b['concluye'] is True, fila_intentos_b)

print("=== COMPROBACIÓN 8: E1 publicando un número con el feed en RETRASADO ===")
st3 = estado_base()
diario3 = dict(dia=1, direccion=1, ventana='RTH', eventos={}, fin_de_dia={})
for feed in ('RETRASADO', 'DESCONOCIDO'):
    snap = dict(estado_feed=feed, bid=6000.0, ask=6000.25, ts_monotono=0.0)
    ctx8 = CD.construye(st3, diario3, [diario3], ahora_iso='x', ahora_monotono=0.5,
                         mercado_snapshots=[snap])
    ok(f"feed={feed}: E1 NO disponible (friccion_optimista/realista = None)",
       ctx8['mercado_friccion']['disponible'] is False
       and ctx8['mercado_friccion']['friccion_optimista'] is None)
    html8 = D.genera_html(ctx8)
    ok(f"feed={feed}: el HTML dice 'E1 no disponible', nunca un número",
       'E1 no disponible' in html8)

snap_ok = dict(estado_feed='TIEMPO_REAL', bid=6000.0, ask=6000.25, ts_monotono=0.0)
ctx8ok = CD.construye(st3, diario3, [diario3], ahora_iso='x', ahora_monotono=0.5,
                       mercado_snapshots=[snap_ok])
ok("feed=TIEMPO_REAL: E1 SI publica un numero",
   ctx8ok['mercado_friccion']['disponible'] is True
   and ctx8ok['mercado_friccion']['friccion_optimista'] is not None)

print("=== Validador de paleta (script, no a ojo) ===")
from bot import paleta as P
ok_paleta, informe_paleta = P.valida()
ok("la paleta del dashboard pasa el validador (contraste WCAG + separación daltonismo)", ok_paleta)

print("\n" + "="*70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
sys.exit(0 if n_ok == len(resultados) else 1)
