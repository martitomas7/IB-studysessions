# -*- coding: utf-8 -*-
"""D8.4, paso 4 (el análogo de prueba_detector_en_vivo.py para esta
pieza): `bot.resolucion_en_vivo.ResuelveDiaEnVivo`, ejecutado de verdad
contra `AdaptadorFalso` (con fills perfectos, fabricados en la barra
exacta que el camino ya conocido dicta -- ver apoyo_oraculo_en_vivo.py),
comparado bit a bit contra `sesion.resolver_dia` como oráculo. 0
discrepancias exigidas, mismo rigor que `detector_en_vivo.py` (0/902 +
0/1500)."""
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
from bot.resolucion_en_vivo import CAMINO_NO_USADO_EN_VIVO, ResuelveDiaEnVivo

_, _ = config.cargar()

CUENTA_PROP, CUENTA_HEDGE, MES = "CTA-PROP", "CTA-HEDGE", "MES"
DIR_BASE = "/tmp/prueba_resuelve_dia_en_vivo"
CAMPOS = ('dx_puntos', 'hedge_dolares', 'comision', 'muere', 'pausa', 'objetivo', 'barra_evento')
TOL = 1e-6

_contador_dia = [0]


def compara_un_caso(nombre, ph_crudo, pl_crudo, pc_crudo, b0, plan, m, fric, deslizamiento,
                     direccion, discrepancias):
    """`ph_crudo`/`pl_crudo`/`pc_crudo`: precios REALES, tal como los reportaría
    el bróker -- NUNCA reflejados. `sesion.resolver_dia` (el oráculo) SIEMPRE
    recibe el camino YA REFLEJADO (`calendario.refleja_camino`), exactamente
    como hace `orquestador.py::procesa_dia_replay` antes de llamar a
    `ciclo_vida.py` -- resolver_dia no sabe nada de "dirección", así que
    pasarle el crudo directamente (para una dirección corta) sería
    comparar peras con manzanas: el bug real que este comentario documenta
    se cazó exactamente así, al ejecutar por primera vez esta prueba con
    dirección corta (3 discrepancias explícitas + más de 80 en el barrido
    aleatorio, todas con dx_puntos con el signo exactamente invertido)."""
    _contador_dia[0] += 1
    dir_caso = os.path.join(DIR_BASE, str(_contador_dia[0]))
    shutil.rmtree(dir_caso, ignore_errors=True)
    ruta_ordenes = os.path.join(dir_caso, "ordenes")
    ruta_nivel = os.path.join(dir_caso, "nivel.json")

    ph_ref, pl_ref, pc_ref = calendario.refleja_camino(ph_crudo, pl_crudo, pc_crudo, direccion)
    teorico = SES.resolver_dia(ph_ref, pl_ref, pc_ref, b0, plan, m, fric, deslizamiento)

    adaptador = AdaptadorOraculoSobreCamino()
    NB = len(pc_crudo)
    p0_crudo = pc_crudo[min(b0, NB - 1)]   # el fill REAL de entrada -- precio crudo, nunca reflejado
    adaptador.programa_abrir(CUENTA_PROP, MES, precio_fill=p0_crudo)
    adaptador.programa_abrir(CUENTA_HEDGE, MES, precio_fill=100.0)   # irrelevante para dx/negocio

    if plan['bloqueo']:
        pierna_o_campana, b_evento = None, None
    else:
        # escanea_resolucion() replica el barrido de resolver_dia -- opera
        # sobre el camino REFLEJADO, igual que resolver_dia mismo.
        pierna_o_campana, b_evento = escanea_resolucion(ph_ref, pl_ref, pc_ref, b0,
                                                         plan['ndn'], plan['nu'])
        if pierna_o_campana == 'campana':
            adaptador.arma_cierre_campana(CUENTA_PROP, MES, precio_cierre=pc_crudo[NB - 1])
        else:
            # precio_fill=None dispara "llena EXACTAMENTE al nivel pedido" --
            # ese nivel lo calcula ResuelveDiaEnVivo internamente
            # (precio_stop_real/precio_limite_real, ya en crudo) con su propia
            # aritmética de reflexión -- no hace falta reconstruirlo aquí.
            adaptador.arma_resolucion(b_evento, pierna_o_campana, precio_fill=None)

    fuente_interna = FuenteDeReplay([{
        "direccion": direccion, "ventana": "22h",
        # crudo: exactamente lo que reportaría el bróker/feed real
        "barras": {"ph": ph_crudo, "pl": pl_crudo, "pc": pc_crudo}, "eventos": {"resets": 0},
    }])
    fuente_interna.abre_dia()
    fuente = FuenteConNotificacion(fuente_interna, adaptador)

    resolvedor = ResuelveDiaEnVivo(
        adaptador, CUENTA_HEDGE, CUENTA_PROP, MES, direccion, fuente,
        ruta_ordenes, ruta_nivel, slot='eval', dia_negociacion=1,
        dormir=lambda s: None)
    vivo = resolvedor(CAMINO_NO_USADO_EN_VIVO, CAMINO_NO_USADO_EN_VIVO, CAMINO_NO_USADO_EN_VIVO,
                       b0, plan, m, fric, deslizamiento)

    for campo in CAMPOS:
        if campo == 'barra_evento' and plan['bloqueo']:
            # DIFERENCIA CONOCIDA Y CORRECTA, no un bug: para una cuenta
            # bloqueada resolver_dia SIGUE barriendo el camino entero (el
            # bloqueo se aplica AL FINAL, dejando barra_evento tal como salió
            # del barrido -- mismo comportamiento ya documentado y verificado
            # en bot/detector_en_vivo.py). En vivo, "bloqueada" significa "ni
            # siquiera se llama al bróker" (ORDEN_DE_TRABAJO_D8.md §5.1) -- no
            # hay ningún barrido que hacer, así que ResuelveDiaEnVivo no puede
            # tener ese dato sin violar esa regla. Los campos de NEGOCIO
            # (dx/comision/hedge/muere/pausa/objetivo) sí tienen que coincidir
            # -- y coinciden, todos en cero.
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

print("=== casos de borde explícitos, dirección CORTA (ejercita _refleja_escalar/_refleja_bar "
      "de verdad, no solo en aislamiento) ===")
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

print("\n=== barrido aleatorio (semilla fija) ===")
OBJETIVO = 1500   # mismo rigor que prueba_detector_en_vivo_sintetico.py -- cada caso crea
                   # ficheros reales y corre el bucle de ResuelveDiaEnVivo entero (~3ms/caso medido)
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
    print(f"RESULTADO: IDENTICOS -- 0/{n_casos} discrepancias ResuelveDiaEnVivo vs resolver_dia")
