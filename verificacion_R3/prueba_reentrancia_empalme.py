# -*- coding: utf-8 -*-
"""D8.4, paso 5: reentrancia de ResuelveDiaEnVivo -- la MISMA instancia se
reutiliza para el intento 0 y el empalme de ciclo_vida.procesa_dia_eval
(mismo objeto, dos llamadas). Exige order_id distintos y CERO estado
cruzado entre las dos -- exactamente el tipo de bug que un objeto con
estado puede esconder."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from apoyo_oraculo_en_vivo import AdaptadorOraculoSobreCamino, FuenteConNotificacion, escanea_resolucion

from bot import calendario, config, sesion as SES
from bot.fuente_barras import FuenteDeReplay
from bot.resolucion_en_vivo import CAMINO_NO_USADO_EN_VIVO, ResuelveDiaEnVivo

_, _ = config.cargar()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


DIR = "/tmp/prueba_reentrancia_empalme"
shutil.rmtree(DIR, ignore_errors=True)
CUENTA_PROP, CUENTA_HEDGE, MES = "CTA-PROP", "CTA-HEDGE", "MES"

# Intento 0: muere pronto (barra 2). Empalme (intento 1): sobrevive, toca objetivo.
ph_crudo = [5000, 5000, 5001, 5000, 5000, 5015, 5015]
pl_crudo = [5000, 5000, 4980, 5000, 5000, 5010, 5010]
pc_crudo = [5000, 5000, 4985, 5000, 5000, 5012, 5012]
direccion = 1
ph_ref, pl_ref, pc_ref = calendario.refleja_camino(ph_crudo, pl_crudo, pc_crudo, direccion)

plan0 = dict(k=10.0, nu=8.0, ndn=8.0, bloqueo=False, comision=1.5, Mm=5.0)   # Mm bajo -> muere
plan1 = dict(k=10.0, nu=8.0, ndn=8.0, bloqueo=False, comision=1.5, Mm=5000.0)  # Mm alto -> sobrevive

teorico0 = SES.resolver_dia(ph_ref, pl_ref, pc_ref, 0, plan0, m=4, fric=3.0, deslizamiento=0.0)
print(f"=== oráculo intento 0: {teorico0} ===")
b0_empalme = teorico0['barra_evento']
teorico1 = SES.resolver_dia(ph_ref, pl_ref, pc_ref, b0_empalme, plan1, m=4, fric=3.0, deslizamiento=0.0)
print(f"=== oráculo empalme (desde barra {b0_empalme}): {teorico1} ===")

pierna0, b_evento0 = escanea_resolucion(ph_ref, pl_ref, pc_ref, 0, plan0['ndn'], plan0['nu'])
pierna1, b_evento1 = escanea_resolucion(ph_ref, pl_ref, pc_ref, b0_empalme, plan1['ndn'], plan1['nu'])
print(f"  pierna0={pierna0}@{b_evento0}  pierna1={pierna1}@{b_evento1}")

adaptador = AdaptadorOraculoSobreCamino()
adaptador.programa_abrir(CUENTA_PROP, MES, precio_fill=pc_crudo[0])
adaptador.programa_abrir(CUENTA_HEDGE, MES, precio_fill=100.0)
adaptador.arma_resolucion(b_evento0, pierna0, precio_fill=None)

fuente_interna = FuenteDeReplay([{
    "direccion": direccion, "ventana": "22h",
    "barras": {"ph": ph_crudo, "pl": pl_crudo, "pc": pc_crudo}, "eventos": {"resets": 0},
}])
fuente_interna.abre_dia()
fuente = FuenteConNotificacion(fuente_interna, adaptador)

ruta_ordenes = os.path.join(DIR, "ordenes")
ruta_nivel = os.path.join(DIR, "nivel.json")
resolvedor = ResuelveDiaEnVivo(adaptador, CUENTA_HEDGE, CUENTA_PROP, MES, direccion, fuente,
                                ruta_ordenes, ruta_nivel, slot='eval', dia_negociacion=1,
                                dormir=lambda s: None)

print("\n=== llamada 1 (intento 0) ===")
ok("_intento arranca en 0", resolvedor._intento == 0)
r0 = resolvedor(CAMINO_NO_USADO_EN_VIVO, CAMINO_NO_USADO_EN_VIVO, CAMINO_NO_USADO_EN_VIVO,
                0, plan0, m=4, fric=3.0, deslizamiento=0.0)
ok("resultado de la llamada 1 coincide con el oráculo del intento 0",
   all(abs(r0[c] - teorico0[c]) < 1e-6 if isinstance(teorico0[c], float) else r0[c] == teorico0[c]
       for c in teorico0), (r0, teorico0))
ok("_intento avanzó a 1 tras la primera llamada", resolvedor._intento == 1)

# reprograma la apertura de la SEGUNDA sub del empalme (nueva orden, mismo mecanismo)
adaptador.programa_abrir(CUENTA_PROP, MES, precio_fill=pc_crudo[b0_empalme])
adaptador.programa_abrir(CUENTA_HEDGE, MES, precio_fill=100.0)
adaptador.arma_resolucion(b_evento1, pierna1, precio_fill=None)

print("\n=== llamada 2 (empalme, MISMA instancia) ===")
r1 = resolvedor(CAMINO_NO_USADO_EN_VIVO, CAMINO_NO_USADO_EN_VIVO, CAMINO_NO_USADO_EN_VIVO,
                b0_empalme, plan1, m=4, fric=3.0, deslizamiento=0.0)
ok("resultado de la llamada 2 coincide con el oráculo del empalme",
   all(abs(r1[c] - teorico1[c]) < 1e-6 if isinstance(teorico1[c], float) else r1[c] == teorico1[c]
       for c in teorico1), (r1, teorico1))
ok("_intento avanzó a 2 tras la segunda llamada", resolvedor._intento == 2)

print("\n=== reentrancia: order_id DISTINTOS entre las dos llamadas, sin estado cruzado ===")
intents = sorted(os.listdir(ruta_ordenes))
ids_abre = [f for f in intents if ':abre.' in f and f.endswith('.resultado.json')]
ids_bracket = [f for f in intents if ':bracket.' in f and f.endswith('.resultado.json')]
ok("dos intent_id de apertura distintos (uno por intento -- 0:eval:0:abre y 0:eval:1:abre)",
   len(ids_abre) == 2 and ids_abre[0] != ids_abre[1], ids_abre)
ok("dos intent_id de bracket distintos", len(ids_bracket) == 2 and ids_bracket[0] != ids_bracket[1],
   ids_bracket)

import json
res_abre_0 = json.load(open(os.path.join(ruta_ordenes, "1:eval:0:abre.resultado.json")))['resultado']
res_abre_1 = json.load(open(os.path.join(ruta_ordenes, "1:eval:1:abre.resultado.json")))['resultado']
ok("los order_id de la apertura del intento 0 y el empalme son DISTINTOS de verdad (no reciclados)",
   res_abre_0['order_id_prop'] != res_abre_1['order_id_prop']
   and res_abre_0['order_id_hedge'] != res_abre_1['order_id_hedge'],
   (res_abre_0, res_abre_1))

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
