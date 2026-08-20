# -*- coding: utf-8 -*-
"""R3 (Task 22, ORDEN_DE_TRABAJO_D8.md §3.3): lector de las corrientes
JSONL del laboratorio. `bot/contexto_dashboard.py::construye()` solo
aceptaba listas ya cargadas en memoria -- este lector las produce a
partir de los ficheros reales que 08_LABORATORIO.md §2 especifica, y el
cierre del círculo (última comprobación) es end-to-end: leer de disco ->
contexto_dashboard.construye() -> dashboard.genera_html() sin reventar."""
import json
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import config, contexto_dashboard as CD, dashboard as D, lector_laboratorio as L

_, _ = config.cargar()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


DIR = "/tmp/prueba_lector_laboratorio"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)


def escribe_jsonl(ruta, lineas):
    with open(ruta, 'w', encoding='utf-8') as fh:
        for obj in lineas:
            fh.write(json.dumps(obj) + "\n")


CABECERA_TIPICA = dict(version_config="v10", checksum_config="abc123",
                        dia_negociacion=1, hora_arranque_pared="2026-08-20T22:00:00+00:00",
                        hora_arranque_monotona=0.0)

print("=== 1. lee_jsonl(): fichero ausente -> lista vacía, nunca una excepción ===")
ok("fichero que no existe -> []", L.lee_jsonl(os.path.join(DIR, "no_existe.jsonl")) == [])

print("\n=== 2. lee_jsonl(): tolera la ÚLTIMA línea truncada, pero NO una rota en medio ===")
ruta_ok = os.path.join(DIR, "truncado_al_final.jsonl")
with open(ruta_ok, 'w') as fh:
    fh.write('{"a": 1}\n{"a": 2}\n{"a": 3, "b": tru')   # última línea truncada a media escritura
objetos = L.lee_jsonl(ruta_ok)
ok("las dos líneas completas se leen, la truncada al final se descarta silenciosamente",
   objetos == [{"a": 1}, {"a": 2}], objetos)

ruta_rota_en_medio = os.path.join(DIR, "rota_en_medio.jsonl")
with open(ruta_rota_en_medio, 'w') as fh:
    fh.write('{"a": 1}\n{esto no es json valido}\n{"a": 3}\n')
try:
    L.lee_jsonl(ruta_rota_en_medio)
    propago = False
except json.JSONDecodeError:
    propago = True
ok("una línea rota que NO es la última SÍ propaga el error (fichero corrupto de verdad, "
   "no un corte a media escritura)", propago)

print("\n=== 3. lee_corriente_con_cabecera(): separa cabecera de registros ===")
ruta_merc = os.path.join(DIR, "mercado_1.jsonl")
snap1 = dict(ts_pared="2026-08-20T22:00:01+00:00", ts_monotono=1.0, instrumento="MESZ26",
             bid=5000.0, ask=5000.5, last=5000.25, estado_feed="TIEMPO_REAL")
snap2 = dict(ts_pared="2026-08-20T22:00:02+00:00", ts_monotono=2.0, instrumento="MESZ26",
             bid=5000.5, ask=5001.0, last=5000.75, estado_feed="TIEMPO_REAL")
escribe_jsonl(ruta_merc, [CABECERA_TIPICA, snap1, snap2])
cab, regs = L.lee_corriente_con_cabecera(ruta_merc)
ok("la cabecera es la primera línea, tal cual", cab == CABECERA_TIPICA, cab)
ok("los registros son las líneas siguientes, en orden", regs == [snap1, snap2], regs)

print("\n=== 4. lee_mercado_snapshots()/lee_eventos_orden()/lee_incidencias(): "
      "agregan varios días EN ORDEN cronológico ===")
# día 1 ya escrito arriba (mercado_1.jsonl); añade día 2 y día 10 (para probar
# que el orden es NUMÉRICO, no alfabético -- '10' antes que '2' alfabéticamente
# sería un bug real)
snap3 = dict(ts_pared="2026-08-21T22:00:01+00:00", ts_monotono=1.0, instrumento="MESZ26",
             bid=5010.0, ask=5010.5, last=5010.25, estado_feed="TIEMPO_REAL")
escribe_jsonl(os.path.join(DIR, "mercado_2.jsonl"), [dict(CABECERA_TIPICA, dia_negociacion=2), snap3])
snap4 = dict(ts_pared="2026-08-30T22:00:01+00:00", ts_monotono=1.0, instrumento="MESZ26",
             bid=5099.0, ask=5099.5, last=5099.25, estado_feed="RETRASADO")
escribe_jsonl(os.path.join(DIR, "mercado_10.jsonl"), [dict(CABECERA_TIPICA, dia_negociacion=10), snap4])

todos = L.lee_mercado_snapshots(DIR)
ok("orden NUMÉRICO por día (1, 2, 10 -- no alfabético '1,10,2')",
   [s['bid'] for s in todos] == [5000.0, 5000.5, 5010.0, 5099.0], [s['bid'] for s in todos])

acotado = L.lee_mercado_snapshots(DIR, dia_desde=2, dia_hasta=2)
ok("dia_desde/dia_hasta acotan correctamente (solo el día 2)",
   len(acotado) == 1 and acotado[0]['bid'] == 5010.0, acotado)

print("\n=== 5. lee_incidencias() + cuenta_incidencias_por_tipo() ===")
inc1 = dict(ts_pared="2026-08-20T22:05:00+00:00", ts_monotono=5.0, tipo="rechazo_orden",
            cuenta="CTA-PROP", detalle="RECHAZADA instantánea")
inc2 = dict(ts_pared="2026-08-20T22:10:00+00:00", ts_monotono=10.0, tipo="desconexion",
            cuenta="CTA-HEDGE", detalle="Connected()=falso a media sesión")
inc3 = dict(ts_pared="2026-08-20T22:12:00+00:00", ts_monotono=12.0, tipo="rechazo_orden",
            cuenta="CTA-PROP", detalle="otro rechazo")
escribe_jsonl(os.path.join(DIR, "incidencias_1.jsonl"), [CABECERA_TIPICA, inc1, inc2, inc3])
incidencias = L.lee_incidencias(DIR)
ok("las tres incidencias se leen en orden", incidencias == [inc1, inc2, inc3])
contadores = L.cuenta_incidencias_por_tipo(incidencias)
ok("cuenta_incidencias_por_tipo agrega correctamente por tipo",
   contadores == {"rechazo_orden": 2, "desconexion": 1}, contadores)

print("\n=== 6. lee_eventos_orden() ===")
ord1 = dict(ts_pared="2026-08-20T22:00:05+00:00", ts_monotono=5.0, order_id="FAKE-1",
            cuenta="CTA-HEDGE", instrumento="MESZ26", estado="LLENA", precio=5000.0, cantidad=4)
escribe_jsonl(os.path.join(DIR, "ordenes_1.jsonl"), [CABECERA_TIPICA, ord1])
eventos_orden = L.lee_eventos_orden(DIR)
ok("evento de orden leído tal cual", eventos_orden == [ord1], eventos_orden)

print("\n=== 7. lee_diario(): el diario del orquestador (SIN cabecera, un fichero acumulativo) ===")
from bot import orquestador as O
RUTA_PACK = os.path.join(ING, "tests", "replay_v10.json")
RUTA_DIARIO = os.path.join(DIR, "diario.jsonl")
import json as _json
pack_completo = _json.load(open(RUTA_PACK))
pack_recortado = os.path.join(DIR, "pack_3_dias.json")
_json.dump(dict(pack_completo, dias=pack_completo["dias"][:3]), open(pack_recortado, 'w'))
fines, diarios, st_final = O.corre_replay(pack_recortado, ruta_salida_diario=RUTA_DIARIO)
diario_leido = L.lee_diario(RUTA_DIARIO)
ok("lee_diario() recupera exactamente los 3 días escritos por corre_replay()",
   len(diario_leido) == 3 and [d['dia'] for d in diario_leido] == [1, 2, 3], diario_leido)
ok("el contenido round-trip es idéntico al que corre_replay() ya tenía en memoria",
   diario_leido == diarios, "coincide" if diario_leido == diarios else "DIFIERE")

print("\n=== 8. cierre del círculo end-to-end: disco -> contexto_dashboard -> dashboard.genera_html() ===")
from bot import estado as E
_, checksum = config.cargar()
estado_hoy = E.nuevo("v10", checksum)
estado_hoy["caja"] = st_final["caja"]
estado_hoy["retirado"] = st_final["retirado"]
estado_hoy["degradado"] = st_final["degradado"]

ctx = CD.construye(
    estado=estado_hoy, diario_hoy=diario_leido[-1] if diario_leido else None,
    historial_diario=L.lee_diario(RUTA_DIARIO),
    mercado_snapshots=L.lee_mercado_snapshots(DIR),
    incidencias_recientes=L.lee_incidencias(DIR),
    incidencias_contadores=L.cuenta_incidencias_por_tipo(L.lee_incidencias(DIR)),
)
ok("contexto_dashboard.construye() no revienta con datos leídos de disco de verdad",
   isinstance(ctx, dict) and 'ahora' in ctx)
ok("el bloque de mercado refleja el último snapshot leído del disco (feed RETRASADO, día 10)",
   ctx['mercado_friccion']['disponible'] is False
   and 'RETRASADO' in ctx['mercado_friccion']['motivo_no_disponible'], ctx['mercado_friccion'])

html = D.genera_html(ctx)
ok("dashboard.genera_html() produce HTML completo a partir de datos leídos de disco",
   isinstance(html, str) and '<html' in html.lower() and len(html) > 500, len(html))

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
