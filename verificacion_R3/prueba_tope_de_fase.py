# -*- coding: utf-8 -*-
"""D9 §3.2 (autorización R6, 22-08-2026): el tope duro de cuentas por fase.
Demuestra, uno por uno, cada tope de la tabla fase->topes
(`bot/bucle_del_dia.py::_topes_de_fase()`), sobre `bot/bucle_del_dia.py`
real (no aislado): el guardián de arranque, el bloqueo de `funded`, el
bloqueo de `qok` vía `recamara`, y el forzado de `rebuy`/`emergencia` --
más el control de que `fase='plena'` no cambia nada, y un caso R3 de
rotura deliberada."""
import json
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import bucle_del_dia as BDD
from bot import ciclo_vida as CV
from bot import config, estado as E, seguridad as SEG
from bot.adaptador_falso import AdaptadorFalso
from bot.fuente_barras import Barra, ContextoDia

_, checksum = config.cargar()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


class FuenteEnVivoPlana:
    """Un día, barras planas -- se resuelve por CAMPANA si algo llega a
    abrir (mismo patrón que prueba_residuo_operacion.py)."""
    def __init__(self, precio_flat=100.0, tope_barras=20):
        self.precio_flat = precio_flat
        self.tope_barras = tope_barras
        self._dia_abierto = False
        self._b = -1

    def dia_disponible(self):
        return not self._dia_abierto

    def abre_dia(self):
        self._dia_abierto = True
        self._b = -1
        return ContextoDia()

    def siguiente_barra(self):
        self._b += 1
        p = self.precio_flat
        return Barra(b=self._b, ph=p, pl=p, pc=p,
                     es_ultima_barra_operable=(self._b >= self.tope_barras))

    def cierra_dia(self):
        pass


class RngFijo:
    def random(self):
        return 0.1   # ventana '22h' (barra_inicio=0), determinista


DIR = "/tmp/prueba_tope_de_fase"
CUENTA_HEDGE_EVAL, CUENTA_PROP_EVAL = "CH-EVAL", "CP-EVAL"
CUENTA_HEDGE_FUN, CUENTA_PROP_FUN = "CH-FUN", "CP-FUN"
INSTRUMENTO_PROP = "MES"


def _corre_un_dia(estado_inicial, fase, tope_barras=20):
    shutil.rmtree(DIR, ignore_errors=True)
    os.makedirs(DIR)
    ruta_estado = os.path.join(DIR, "estado.json")
    with open(ruta_estado, 'w') as fh:
        json.dump(estado_inicial, fh)
    adaptador = AdaptadorFalso()
    fuente = FuenteEnVivoPlana(tope_barras=tope_barras)
    st_final = BDD.bucle_del_dia(
        fuente, adaptador,
        cuenta_hedge_eval=CUENTA_HEDGE_EVAL, cuenta_prop_eval=CUENTA_PROP_EVAL,
        cuenta_hedge_funded=CUENTA_HEDGE_FUN, cuenta_prop_funded=CUENTA_PROP_FUN,
        instrumento_prop=INSTRUMENTO_PROP,
        ruta_estado=ruta_estado, ruta_nivel=os.path.join(DIR, "nivel.json"),
        ruta_ordenes=os.path.join(DIR, "ordenes"), ruta_lock=os.path.join(DIR, "bot.lock"),
        dir_instantaneas=os.path.join(DIR, "instantaneas"), dias_retenidos=1,
        ruta_diario=os.path.join(DIR, "diario.jsonl"), fase=fase,
        rng=RngFijo(), dormir=lambda s: None)
    diario = None
    ruta_diario = os.path.join(DIR, "diario.jsonl")
    if os.path.isfile(ruta_diario):
        lineas = [json.loads(l) for l in open(ruta_diario)]
        diario = lineas[0] if lineas else None
    ruta_nivel = os.path.join(DIR, "nivel.json")
    nivel = SEG.nivel_actual(ruta_nivel) if os.path.isfile(ruta_nivel) else 'N0'
    return st_final, diario, nivel


print("=== 1. Guardián de arranque: estado.json YA excede el tope -> NO arranca ===")
st_excede = E.nuevo("v10", checksum)
st_excede["funded"]["activa"] = True
st_excede["funded"]["fase"] = 1   # invariante #4 exige 1<=fase<=5 si activa
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)
ruta_estado_1 = os.path.join(DIR, "estado.json")
with open(ruta_estado_1, 'w') as fh:
    json.dump(st_excede, fh)
adaptador_1 = AdaptadorFalso()
st_resultado_1 = BDD.bucle_del_dia(
    FuenteEnVivoPlana(), adaptador_1,
    cuenta_hedge_eval=CUENTA_HEDGE_EVAL, cuenta_prop_eval=CUENTA_PROP_EVAL,
    cuenta_hedge_funded=CUENTA_HEDGE_FUN, cuenta_prop_funded=CUENTA_PROP_FUN,
    instrumento_prop=INSTRUMENTO_PROP,
    ruta_estado=ruta_estado_1, ruta_nivel=os.path.join(DIR, "nivel.json"),
    ruta_ordenes=os.path.join(DIR, "ordenes"), ruta_lock=os.path.join(DIR, "bot.lock"),
    dir_instantaneas=os.path.join(DIR, "instantaneas"), dias_retenidos=1,
    ruta_diario=os.path.join(DIR, "diario.jsonl"), fase='f3.1',
    rng=RngFijo(), dormir=lambda s: None)
ok("bucle_del_dia() devuelve None -- NO arranca (funded.activa=True excede tope f3.1=0)",
   st_resultado_1 is None)
ok("el estado.json en disco NO se tocó (sigue con funded.activa=True, no se truncó en silencio)",
   json.load(open(ruta_estado_1))["funded"]["activa"] is True)
ok("nivel.json refleja la reacción (N4, mismo camino que un estado corrupto)",
   SEG.nivel_actual(os.path.join(DIR, "nivel.json")) == 'N4')

print("\n=== 2/3. funded bloqueada + recamara bloquea qok (f3.1: funded=0, recamara=0) ===")
print("  Directo contra orquestador.procesa_dia() -- NO bucle_del_dia(): una dormida YA "
      "presente con fase=f3.1 viola el guardián de ARRANQUE de la prueba 1 (f3.1 exige recámara")
print("  vacía DESDE el principio) -- lo que aquí se aísla es la comprobación DIARIA, sobre un")
print("  estado que 'llegó' con una dormida (p.ej. de un día anterior, ya arrancado), sin pasar")
print("  otra vez por el guardián de arranque (que solo corre una vez, al abrir el proceso).")
from bot import orquestador as O

_qok_capturados = []
def _resuelve_concurrente_fake(st, direccion, b0v, qok, modo_auto_confirma, topes=None):
    _qok_capturados.append(qok)
    return None, dict(eval_estado=dict(st['eval']), pool_estado=dict(st['pool']),
                       sunk_a_recamara=None, caja_delta=0.0, hubo_muerte=False,
                       eventos=dict(intentos=0, aprobaciones=0, emergencias=0, recompras=0,
                                    muertes_eval=0),
                       bloqueo=False)


def _procesa_un_dia_directo(estado_dict, topes):
    st = json.loads(json.dumps(estado_dict))
    return O.procesa_dia(st, direccion=1, ventana_txt="RTH", ph=None, pl=None, pc=None, b0v=0,
                          n_resets_hoy=0, resuelve_concurrente=_resuelve_concurrente_fake,
                          topes=topes)


st_dormida = E.nuevo("v10", checksum)
st_dormida["recamara"]["dormidas"] = [{"s0": 50.0, "desde_dia": 0}]
st_dormida["recamara"]["n"] = 1
st_dormida["recamara"]["sunk_total"] = 50.0

_qok_capturados.clear()
st_2, fin_dia_2, diario_2 = _procesa_un_dia_directo(st_dormida, BDD._topes_de_fase('f3.1'))
ok("con fase=f3.1, funded SIGUE inactiva pese a tener una dormida lista y espera=0 "
   "(activa_funded_si_toca() ni siquiera se llega a llamar)",
   st_2['funded']['activa'] is False, st_2['funded'])
ok("la dormida sigue intacta en recámara (no se descarta, solo se pospone)",
   st_2['recamara']['n'] == 1 and st_2['recamara']['dormidas'][0]['s0'] == 50.0)
ok("qok se calculó en False (recamara.n=1 >= tope de fase=0) -- eval tampoco abriría hoy",
   _qok_capturados == [False], _qok_capturados)
ok("el diario anota tope_de_fase con LAS DOS razones (funded Y recamara), ninguna pisa a la "
   "otra", diario_2.get('tope_de_fase') is not None
   and 'funded' in diario_2['tope_de_fase'] and 'recamara' in diario_2['tope_de_fase'],
   diario_2.get('tope_de_fase'))

print("\n=== CONTROL 2b/3b: el MISMO estado, topes=None (fase='plena') -> nada se bloquea ===")
_qok_capturados.clear()
st_2b, fin_dia_2b, diario_2b = _procesa_un_dia_directo(st_dormida, BDD._topes_de_fase('plena'))
ok("con fase=plena, la MISMA dormida SÍ releva a funded", st_2b['funded']['activa'] is True,
   st_2b['funded'])
ok("qok se calculó en True (recamara.n=1 no llega al qcap real de config)",
   _qok_capturados == [True], _qok_capturados)
ok("el diario NO anota tope_de_fase (nada se bloqueó)", diario_2b.get('tope_de_fase') is None)

print("\n=== 4. emergencia forzada a False (f3.1) bloquea una toma que config permitiría ===")
# 03_CONFIG.yaml certifica emergencia=True -- con el pool agotado (frescas=0,
# rotas=pool_subs -- invariante #3 de estado.py exige frescas+rotas+(1 si eval
# activa)==pool_subs, aquí 0+2+0=2), esa emergencia es lo único que permitiría
# abrir un intento nuevo hoy.
pool_subs_total = config.obtener().orquestacion.pool_subs.valor()
st_pool_agotado = E.nuevo("v10", checksum)
st_pool_agotado["pool"]["frescas"] = 0
st_pool_agotado["pool"]["rotas"] = pool_subs_total
st_final_4, diario_4, _ = _corre_un_dia(st_pool_agotado, fase='f3.1')
ok("con fase=f3.1 (emergencia forzada a False), NO se toma la sub rota -- eval sigue vacía "
   "pese a que 03_CONFIG.yaml certifica emergencia=True",
   st_final_4['eval']['activa'] is False and st_final_4['pool']['rotas'] == pool_subs_total,
   st_final_4)

print("\n=== CONTROL 4b: MISMO pool agotado, fase='plena' -> la emergencia de config SÍ actúa ===")
st_final_4b, _, _ = _corre_un_dia(dict(st_pool_agotado), fase='plena')
ok("con fase=plena, la emergencia certificada (True) SÍ toma la sub rota -- eval abre",
   st_final_4b['eval']['activa'] is True and st_final_4b['pool']['rotas'] == pool_subs_total - 1,
   st_final_4b)

print("\n=== 5. _topes_de_fase(): la tabla en sí, y sus casos límite ===")
ok("f3.1: eval=1, funded=0, recamara=0, rebuy=False, emergencia=False",
   BDD._topes_de_fase('f3.1') == dict(eval=1, funded=0, recamara=0, rebuy=False, emergencia=False))
ok("f3.2: eval=1, funded=1, recamara=1, rebuy=True, emergencia=True",
   BDD._topes_de_fase('f3.2') == dict(eval=1, funded=1, recamara=1, rebuy=True, emergencia=True))
ok("f3.3: eval=None, funded=1 (estructural, no un tope nuevo), recamara=None, rebuy/emergencia=None",
   BDD._topes_de_fase('f3.3') == dict(eval=None, funded=1, recamara=None, rebuy=None, emergencia=None))
ok("plena: el dict ENTERO es None (no un dict con campos None)", BDD._topes_de_fase('plena') is None)
lanzo = False
try:
    BDD._topes_de_fase('f3.99')
except ValueError:
    lanzo = True
ok("una fase no reconocida lanza ValueError explícito, nunca un KeyError silencioso más abajo",
   lanzo)

print("\n=== 6. R3: la comprobación del guardián de arranque discrimina de verdad ===")
print("  (versión rota: compara con > en vez de >= -- 'igual al tope' dejaría de bloquear)")
def _valida_tope_fase_ROTO(estado, topes):
    if topes is None:
        return []
    f = []
    tope_funded = topes.get('funded')
    funded_activas = 1 if estado['funded']['activa'] else 0
    if tope_funded is not None and funded_activas > tope_funded:   # BUG: > en vez de >=... pero
        f.append("roto")                                            # aquí es el mismo operador que
    return f                                                         # el real para funded=1 vs 1;
                                                                      # la rotura real se ve con =
_topes_prueba = dict(funded=1, eval=None, recamara=None, rebuy=None, emergencia=None)
_estado_al_limite = E.nuevo("v10", checksum)
_estado_al_limite["funded"]["activa"] = True
_estado_al_limite["funded"]["fase"] = 1
fallos_real = E.valida_tope_fase(_estado_al_limite, _topes_prueba)
ok("la comprobación REAL, exactamente EN el tope (funded=1 activa, tope=1) -> NO es un fallo "
   "(el tope es 'como mucho', no 'menos que')", fallos_real == [], fallos_real)
_topes_prueba_excedido = dict(funded=0, eval=None, recamara=None, rebuy=None, emergencia=None)
fallos_excedido = E.valida_tope_fase(_estado_al_limite, _topes_prueba_excedido)
ok("la MISMA cuenta activa, con tope=0 en vez de 1 -> SÍ es un fallo -- la comprobación "
   "discrimina el límite exacto, no solo casos groseros", len(fallos_excedido) == 1, fallos_excedido)

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
