# -*- coding: utf-8 -*-
"""D8.4 reestructuración, paso 3/5: `bot.resolucion_en_vivo.MaquinaEnVivo`
(no bloqueante, extraída de `ResuelveDiaEnVivo` para que el futuro bucle
de tiempo compartido -- RESPUESTA_D8_CONCURRENCIA.md §3 -- pueda avanzar
varias sesiones a la vez sin que ninguna posea su propio `while True`)
comparada bit a bit contra el MISMO oráculo (`sesion.resolver_dia`) que ya
verifica `ResuelveDiaEnVivo` en `prueba_resuelve_dia_en_vivo.py` -- mismos
casos explícitos + el mismo barrido aleatorio (semilla igual), reusando
`apoyo_oraculo_en_vivo.py` tal cual. 0 discrepancias exigidas, mismo rigor
que el resto de oráculos de D8."""
import os
import random
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from apoyo_oraculo_en_vivo import AdaptadorOraculoSobreCamino, FuenteConNotificacion, escanea_resolucion

from bot import calendario, config, sesion as SES
from bot.fuente_barras import FuenteDeReplay
from bot.resolucion_en_vivo import MaquinaEnVivo

_, _ = config.cargar()

CUENTA_PROP, CUENTA_HEDGE, MES = "CTA-PROP", "CTA-HEDGE", "MES"
DIR_BASE = "/tmp/prueba_maquina_en_vivo"
CAMPOS = ('dx_puntos', 'hedge_dolares', 'comision', 'muere', 'pausa', 'objetivo', 'barra_evento')
TOL = 1e-6

_contador_dia = [0]


def corre_maquina(adaptador, fuente, direccion, ruta_ordenes, ruta_nivel, b0, plan, m, fric,
                   deslizamiento):
    """Conduce MaquinaEnVivo a mano -- exactamente lo que hará
    bot/bucle_de_tiempo.py, un paso por barra, sin ningún while interno
    propio de la máquina."""
    maquina = MaquinaEnVivo(adaptador, CUENTA_HEDGE, CUENTA_PROP, MES, direccion,
                             ruta_ordenes, ruta_nivel, slot='eval', dia_negociacion=1,
                             intento=0, dormir=lambda s: None)
    estado = maquina.abre(b0, plan, m, fric, deslizamiento)
    while estado == 'VIGILANDO':
        barra = fuente.siguiente_barra()
        estado = maquina.avanza_barra(barra)
    assert estado == 'RESUELTO', f"MaquinaEnVivo se quedó en {estado!r}, nunca resolvió"
    return maquina.resultado


def compara_un_caso(nombre, ph_crudo, pl_crudo, pc_crudo, b0, plan, m, fric, deslizamiento,
                     direccion, discrepancias):
    """Mismo patrón que prueba_resuelve_dia_en_vivo.py::compara_un_caso --
    ver su docstring para el porqué de crudo vs reflejado."""
    _contador_dia[0] += 1
    dir_caso = os.path.join(DIR_BASE, str(_contador_dia[0]))
    shutil.rmtree(dir_caso, ignore_errors=True)
    ruta_ordenes = os.path.join(dir_caso, "ordenes")
    ruta_nivel = os.path.join(dir_caso, "nivel.json")

    ph_ref, pl_ref, pc_ref = calendario.refleja_camino(ph_crudo, pl_crudo, pc_crudo, direccion)
    teorico = SES.resolver_dia(ph_ref, pl_ref, pc_ref, b0, plan, m, fric, deslizamiento)

    adaptador = AdaptadorOraculoSobreCamino()
    NB = len(pc_crudo)
    p0_crudo = pc_crudo[min(b0, NB - 1)]
    adaptador.programa_abrir(CUENTA_PROP, MES, precio_fill=p0_crudo)
    adaptador.programa_abrir(CUENTA_HEDGE, MES, precio_fill=100.0)

    if plan['bloqueo']:
        pierna_o_campana, b_evento = None, None
    else:
        pierna_o_campana, b_evento = escanea_resolucion(ph_ref, pl_ref, pc_ref, b0,
                                                         plan['ndn'], plan['nu'])
        if pierna_o_campana == 'campana':
            adaptador.arma_cierre_campana(CUENTA_PROP, MES, precio_cierre=pc_crudo[NB - 1])
        else:
            adaptador.arma_resolucion(b_evento, pierna_o_campana, precio_fill=None)

    fuente_interna = FuenteDeReplay([{
        "direccion": direccion, "ventana": "22h",
        "barras": {"ph": ph_crudo, "pl": pl_crudo, "pc": pc_crudo}, "eventos": {"resets": 0},
    }])
    fuente_interna.abre_dia()
    fuente = FuenteConNotificacion(fuente_interna, adaptador)

    vivo = corre_maquina(adaptador, fuente, direccion, ruta_ordenes, ruta_nivel, b0, plan, m,
                          fric, deslizamiento)

    for campo in CAMPOS:
        if campo == 'barra_evento' and plan['bloqueo']:
            # DIFERENCIA CONOCIDA Y CORRECTA -- ver prueba_resuelve_dia_en_vivo.py.
            continue
        vt, vv = teorico[campo], vivo[campo]
        igual = abs(vt - vv) < TOL if isinstance(vt, float) else vt == vv
        if not igual:
            discrepancias.append((nombre, campo, vt, vv))
    shutil.rmtree(dir_caso, ignore_errors=True)


def plan(k=10.0, nu=8.0, ndn=8.0, bloqueo=False, comision=1.5, Mm=500.0):
    return dict(k=k, nu=nu, ndn=ndn, bloqueo=bloqueo, comision=comision, Mm=Mm)


discrepancias = []
n_casos = 0

print("=== casos de borde explícitos (dirección larga) ===")
casos_explicitos = [
    ("empate_misma_barra",
     [5000, 5000, 5015, 5015, 5015], [5000, 5000, 4985, 4985, 4985], [5000, 5000, 5000, 5000, 5000],
     1, plan(nu=8, ndn=8), 4, 3.0, 0.0),
    ("rango_cero",
     [5000.0] * 6, [5000.0] * 6, [5000.0] * 6, 1, plan(nu=8, ndn=8), 4, 3.0, 0.0),
    ("muerte_primera_barra",
     [5000, 5001], [5000, 4980], [5000, 4985], 0, plan(nu=8, ndn=8, Mm=5.0), 4, 3.0, 0.0),
    ("muerte_ultima_barra",
     [5000, 5000, 5000, 5000, 5001], [5000, 5000, 5000, 5000, 4980], [5000, 5000, 5000, 5000, 4985],
     0, plan(nu=8, ndn=8, Mm=5.0), 4, 3.0, 0.0),
    ("objetivo_puro",
     [5000, 5012], [5000, 4998], [5000, 5010], 0, plan(nu=8, ndn=8), 4, 3.0, 0.0),
    ("deslizamiento_en_muerte",
     [5000, 5001], [5000, 4980], [5000, 4985], 0, plan(nu=8, ndn=8, Mm=5.0), 4, 3.0, 2.5),
    ("bloqueado_con_evento",
     [5000, 5000, 5015], [5000, 4985, 5010], [5000, 5000, 5012], 0, plan(nu=8, ndn=8, bloqueo=True),
     4, 3.0, 0.0),
]
for nombre, ph, pl, pc, b0, p, m, fric, desliz in casos_explicitos:
    compara_un_caso(nombre, ph, pl, pc, b0, p, m, fric, desliz, direccion=1, discrepancias=discrepancias)
    n_casos += 1

print("=== casos de borde explícitos, dirección CORTA ===")
casos_cortos = [
    ("corto_toca_suelo",
     [5000, 5008], [5000, 4995], [5000, 5000], 0, plan(nu=8, ndn=8), 4, 3.0, 0.0),
    ("corto_toca_objetivo",
     [5000, 5005], [5000, 4990], [5000, 4993], 0, plan(nu=8, ndn=8), 4, 3.0, 0.0),
    ("corto_campana",
     [5000, 5002], [5000, 4998], [5000, 5001], 0, plan(nu=8, ndn=8), 4, 3.0, 0.0),
]
for nombre, ph, pl, pc, b0, p, m, fric, desliz in casos_cortos:
    compara_un_caso(nombre, ph, pl, pc, b0, p, m, fric, desliz, direccion=-1, discrepancias=discrepancias)
    n_casos += 1

print(f"  {n_casos} casos explícitos, {len(discrepancias)} discrepancias hasta aquí")

print("\n=== barrido aleatorio (misma semilla que prueba_resuelve_dia_en_vivo.py) ===")
OBJETIVO = 1500
rng = random.Random(20260820)
while n_casos < OBJETIVO:
    NB = rng.randint(3, 40)
    b0 = rng.randint(0, max(0, NB - 3))
    precio = 5000.0
    ph_r, pl_r, pc_r = [], [], []
    for _ in range(NB):
        paso = rng.uniform(-6.0, 6.0)
        precio += paso
        ph_r.append(round(precio + rng.uniform(0.0, 4.0), 2))
        pl_r.append(round(precio - rng.uniform(0.0, 4.0), 2))
        pc_r.append(round(precio, 2))
    ndn = rng.uniform(3.0, 20.0)
    nu = rng.uniform(3.0, 20.0)
    Mm = rng.choice([5.0, 50.0, 500.0, 5000.0])
    m = rng.choice([2, 4, 6, 10])
    k = rng.choice([1, 5, 10, 20])
    fric = rng.uniform(0.0, 5.0)
    desliz = rng.uniform(0.0, 5.0)
    bloqueo = rng.random() < 0.1
    direccion = rng.choice([1, -1])
    p = plan(k=k, nu=nu, ndn=ndn, bloqueo=bloqueo, comision=rng.uniform(0.5, 3.0), Mm=Mm)
    compara_un_caso(f"aleatorio_{n_casos}", ph_r, pl_r, pc_r, b0, p, m, fric, desliz,
                     direccion=direccion, discrepancias=discrepancias)
    n_casos += 1

shutil.rmtree(DIR_BASE, ignore_errors=True)

print(f"\n  {n_casos} estados comparados, {len(discrepancias)} discrepancias")
if discrepancias:
    print(f"  primeras discrepancias: {discrepancias[:10]}")

print("\n" + "=" * 70)
if discrepancias:
    print(f"FALLO: {len(discrepancias)} discrepancias sobre {n_casos} casos")
    sys.exit(1)
else:
    print(f"RESULTADO: IDENTICOS -- 0/{n_casos} discrepancias MaquinaEnVivo vs resolver_dia")


# === reentrancia: dos instancias DISTINTAS (intento=0, intento=1) sobre el
#     MISMO adaptador/fuente -- verifica que intent_id (D8.5) sigue siendo
#     único con el nuevo diseño (una MaquinaEnVivo nueva por intento, no un
#     contador interno mutable como ResuelveDiaEnVivo._intento) ==========
print("\n=== reentrancia: MaquinaEnVivo(intento=0) y MaquinaEnVivo(intento=1), mismo día ===")
import json as _json

DIR_REENTRANCIA = "/tmp/prueba_maquina_en_vivo_reentrancia"
shutil.rmtree(DIR_REENTRANCIA, ignore_errors=True)
ruta_ordenes_r = os.path.join(DIR_REENTRANCIA, "ordenes")
ruta_nivel_r = os.path.join(DIR_REENTRANCIA, "nivel.json")

direccion_r = 1
ph_r0 = [5000, 5000, 5001, 5000, 5000, 5015, 5015]
pl_r0 = [5000, 5000, 4980, 5000, 5000, 5010, 5010]
pc_r0 = [5000, 5000, 4985, 5000, 5000, 5012, 5012]
ph_ref_r, pl_ref_r, pc_ref_r = calendario.refleja_camino(ph_r0, pl_r0, pc_r0, direccion_r)

plan0_r = plan(k=10.0, nu=8.0, ndn=8.0, Mm=5.0)     # Mm bajo -> muere pronto
plan1_r = plan(k=10.0, nu=8.0, ndn=8.0, Mm=5000.0)  # Mm alto -> sobrevive hasta objetivo

teorico0_r = SES.resolver_dia(ph_ref_r, pl_ref_r, pc_ref_r, 0, plan0_r, m=4, fric=3.0, deslizamiento=0.0)
b0_empalme_r = teorico0_r['barra_evento']
teorico1_r = SES.resolver_dia(ph_ref_r, pl_ref_r, pc_ref_r, b0_empalme_r, plan1_r, m=4, fric=3.0,
                               deslizamiento=0.0)

pierna0_r, bevt0_r = escanea_resolucion(ph_ref_r, pl_ref_r, pc_ref_r, 0, plan0_r['ndn'], plan0_r['nu'])
pierna1_r, bevt1_r = escanea_resolucion(ph_ref_r, pl_ref_r, pc_ref_r, b0_empalme_r, plan1_r['ndn'],
                                         plan1_r['nu'])

adaptador_r = AdaptadorOraculoSobreCamino()
adaptador_r.programa_abrir(CUENTA_PROP, MES, precio_fill=pc_r0[0])
adaptador_r.programa_abrir(CUENTA_HEDGE, MES, precio_fill=100.0)
adaptador_r.arma_resolucion(bevt0_r, pierna0_r, precio_fill=None)

fuente_interna_r = FuenteDeReplay([{
    "direccion": direccion_r, "ventana": "22h",
    "barras": {"ph": ph_r0, "pl": pl_r0, "pc": pc_r0}, "eventos": {"resets": 0},
}])
fuente_interna_r.abre_dia()
fuente_r = FuenteConNotificacion(fuente_interna_r, adaptador_r)

maquina0 = MaquinaEnVivo(adaptador_r, CUENTA_HEDGE, CUENTA_PROP, MES, direccion_r,
                          ruta_ordenes_r, ruta_nivel_r, slot='eval', dia_negociacion=1,
                          intento=0, dormir=lambda s: None)
estado0 = maquina0.abre(0, plan0_r, m=4, fric=3.0, deslizamiento=0.0)
while estado0 == 'VIGILANDO':
    estado0 = maquina0.avanza_barra(fuente_r.siguiente_barra())

ok0 = all(abs(maquina0.resultado[c] - teorico0_r[c]) < 1e-6 if isinstance(teorico0_r[c], float)
          else maquina0.resultado[c] == teorico0_r[c] for c in teorico0_r)
resultados_reentrancia = [("intento 0 coincide con el oráculo", ok0)]

adaptador_r.programa_abrir(CUENTA_PROP, MES, precio_fill=pc_r0[b0_empalme_r])
adaptador_r.programa_abrir(CUENTA_HEDGE, MES, precio_fill=100.0)
adaptador_r.arma_resolucion(bevt1_r, pierna1_r, precio_fill=None)

maquina1 = MaquinaEnVivo(adaptador_r, CUENTA_HEDGE, CUENTA_PROP, MES, direccion_r,
                          ruta_ordenes_r, ruta_nivel_r, slot='eval', dia_negociacion=1,
                          intento=1, dormir=lambda s: None)
estado1 = maquina1.abre(b0_empalme_r, plan1_r, m=4, fric=3.0, deslizamiento=0.0)
while estado1 == 'VIGILANDO':
    estado1 = maquina1.avanza_barra(fuente_r.siguiente_barra())

ok1 = all(abs(maquina1.resultado[c] - teorico1_r[c]) < 1e-6 if isinstance(teorico1_r[c], float)
          else maquina1.resultado[c] == teorico1_r[c] for c in teorico1_r)
resultados_reentrancia.append(("intento 1 (empalme) coincide con el oráculo", ok1))

ids_abre = sorted(f for f in os.listdir(ruta_ordenes_r) if ':abre.' in f and f.endswith('.resultado.json'))
resultados_reentrancia.append(("dos intent_id de apertura distintos (0:eval:0:abre / 0:eval:1:abre... "
                                "en realidad dia_negociacion=1)", len(ids_abre) == 2 and ids_abre[0] != ids_abre[1]))
res_abre_0 = _json.load(open(os.path.join(ruta_ordenes_r, ids_abre[0])))['resultado']
res_abre_1 = _json.load(open(os.path.join(ruta_ordenes_r, ids_abre[1])))['resultado']
resultados_reentrancia.append(("los order_id de las dos aperturas son DISTINTOS (no reciclados)",
                                res_abre_0['order_id_prop'] != res_abre_1['order_id_prop']
                                and res_abre_0['order_id_hedge'] != res_abre_1['order_id_hedge']))

for nombre, cond in resultados_reentrancia:
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}")
shutil.rmtree(DIR_REENTRANCIA, ignore_errors=True)

if not all(c for _, c in resultados_reentrancia):
    print("\nFALLO en la reentrancia de MaquinaEnVivo")
    sys.exit(1)
print(f"\n{len(resultados_reentrancia)}/{len(resultados_reentrancia)} comprobaciones de reentrancia OK")
