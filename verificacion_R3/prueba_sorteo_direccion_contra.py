# -*- coding: utf-8 -*-
"""D8 §5.1 (ANALISIS_PUERTA_GRANDE.md §5): el sorteo de dirección + el veto
CONTRA -- cobertura CERO en la Puerta Grande (la dirección la fuerza el
pack en replay; el `candidata` es relleno sin efecto, `orquestador.py`
líneas 160-163). Es el código que corre TODOS los días en producción y
nunca se había ejercitado de verdad.

Dos piezas:

1. Propiedad exhaustiva sobre `calendario.sortea_direccion` en aislamiento
   (función pura, barata de repetir miles de veces) -- (i) la marginal del
   sorteo es 50/50 dentro de banda, (ii) tras cada muerte la dirección se
   mantiene EXACTAMENTE `contra_dias` días, (iii) el comando `contra=0` del
   operador la desactiva del todo.
2. Integración real, corta: `bot/bucle_del_dia.py` en vivo de verdad (sin
   pack), con una muerte real fabricada, para confirmar que el bucle
   ENVUELVE la pieza (1) correctamente -- lee/escribe
   `st['contra_pendiente']`/`st['direccion']` tal como
   `orquestador.procesa_dia()` los deja.

   `AdaptadorFalso` puro NUNCA resuelve un bracket contra un precio --
   sus dos patas se quedan en reposo hasta que una prueba llama
   explícitamente `fabrica_resolucion_bracket()` (así lo dice su propio
   docstring: "este simulador no modela una trayectoria de precio real").
   Para fabricar una muerte real "por precio" en el bucle en vivo hace
   falta el MISMO oráculo que usa LA PUERTA GRANDE --
   `apoyo_puerta_grande.py::AdaptadorReplaySobrePack` (que sí escanea un
   camino conocido y dispara el bracket solo) -- reutilizado aquí tal
   cual, nunca reimplementado."""
import os
import random
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from apoyo_puerta_grande import AdaptadorReplaySobrePack

from bot import bucle_del_dia as BDD
from bot import calendario, config, estado as E, orquestador as O
from bot.fuente_barras import Barra, ContextoDia

_, checksum = config.cargar()
cfg = config.obtener()
CONTRA_DIAS = int(cfg.sesion.direccion.contra_dias.valor())

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


print(f"=== contra_dias certificado en 03_CONFIG.yaml: {CONTRA_DIAS} ===")

# =============================================================================
# 1. Propiedad exhaustiva sobre calendario.sortea_direccion en aislamiento
# =============================================================================
print("\n=== propiedad exhaustiva: 200.000 días simulados, muerte al 5% diario ===")

rng = random.Random(20260821)
N = 200_000
P_MUERTE = 0.05

direccion = 1
contra_pendiente = 0
secuencia = []   # (candidata, hubo_muerte_ayer, contra_pendiente_antes, direccion, contra_pendiente_despues)
for _ in range(N):
    candidata = 1 if rng.random() < 0.5 else -1
    hubo_muerte_ayer = rng.random() < P_MUERTE
    contra_antes = contra_pendiente
    direccion, contra_pendiente = calendario.sortea_direccion(
        candidata=candidata, direccion_anterior=direccion,
        contra_pendiente_anterior=contra_antes, hubo_muerte_ayer=hubo_muerte_ayer)
    secuencia.append((candidata, hubo_muerte_ayer, contra_antes, direccion, contra_pendiente))

# --- (i) la marginal es 50/50 dentro de banda -------------------------------
n_largos = sum(1 for _, _, _, d, _ in secuencia if d == 1)
frac_largos = n_largos / N
# banda: 3 desviaciones tipicas de una binomial(N, 0.5) -- ni de lejos ajustada
# a mano, es la banda estadistica estandar de un sorteo justo.
margen = 3 * (0.5 * 0.5 / N) ** 0.5
ok(f"(i) marginal de dirección 50/50 dentro de banda estadística (±{margen:.4f})",
   abs(frac_largos - 0.5) < margen, frac_largos)

# --- (ii) tras cada muerte, la dirección se mantiene EXACTAMENTE contra_dias días
fallos_ii = []
i = 0
n_muertes_probadas = 0
while i < len(secuencia) - CONTRA_DIAS - 1:
    _, hubo_muerte_ayer, _, direccion_dia_muerte, contra_tras_muerte = secuencia[i]
    if hubo_muerte_ayer:
        n_muertes_probadas += 1
        if contra_tras_muerte != CONTRA_DIAS:
            fallos_ii.append((i, 'contra_pendiente no rearmó a contra_dias', contra_tras_muerte))
        # los siguientes CONTRA_DIAS-1 dias (mientras el contador siga > 0 y no
        # haya OTRA muerte que lo rearme) deben repetir la MISMA direccion.
        for k in range(1, CONTRA_DIAS):
            if i + k >= len(secuencia):
                break
            _, otra_muerte, contra_antes_k, direccion_k, _ = secuencia[i + k]
            if otra_muerte:
                break   # rearmado por otra muerte -- deja de aplicar esta cadena
            if contra_antes_k <= 0:
                fallos_ii.append((i, f'contra_pendiente llegó a 0 antes de {CONTRA_DIAS} días',
                                   k, contra_antes_k))
                break
            if direccion_k != direccion_dia_muerte:
                fallos_ii.append((i, f'dirección cambió dentro de la ventana CONTRA (día +{k})',
                                   direccion_dia_muerte, direccion_k))
                break
    i += 1
ok(f"(ii) tras cada muerte ({n_muertes_probadas} casos probados), la dirección se "
   f"mantiene EXACTAMENTE {CONTRA_DIAS} días",
   len(fallos_ii) == 0, fallos_ii[:5])

# --- (iii) el comando contra=0 (comandos.valor_efectivo) la desactiva --------
print("\n=== (iii) el comando del operador 'contra' (valor_apagado=0) desactiva CONTRA ===")
estado_con_contra_apagado = dict(desviaciones_activas=[
    dict(palanca='contra', desde_dia=1, hasta_dia=N + 1)])

direccion = 1
contra_pendiente = 0
fallos_iii = []
for dia in range(1, 2000):
    candidata = 1 if rng.random() < 0.5 else -1
    hubo_muerte_ayer = rng.random() < 0.3   # muerte MUY frecuente a propósito -- si CONTRA
                                              # estuviera vivo, esto encadenaría rachas largas
    direccion, contra_pendiente = calendario.sortea_direccion(
        candidata=candidata, direccion_anterior=direccion,
        contra_pendiente_anterior=contra_pendiente, hubo_muerte_ayer=hubo_muerte_ayer,
        estado=estado_con_contra_apagado, dia_actual=dia)
    if contra_pendiente != 0:
        fallos_iii.append((dia, contra_pendiente))
ok("(iii) con 'contra' apagado por el operador, contra_pendiente NUNCA es > 0 "
   "(ni con muerte al 30% diario)", len(fallos_iii) == 0, fallos_iii[:5])

# =============================================================================
# 2. Integración real: bot/bucle_del_dia.py en vivo, sin pack, con UNA muerte
#    real fabricada -- confirma que el bucle ENVUELVE bien la pieza (1)
# =============================================================================
print("\n=== integración: bucle_del_dia() en vivo, muerte real, CONTRA se rearma y expira ===")


NB = 86
P0 = 5000.0
# muy por encima de cualquier ndn plausible -- garantiza que el toque
# SIEMPRE gane la pata STOP (nunca la de campana ni la de límite: el
# precio nunca sube, solo baja y se queda abajo), sin tener que conocer
# el ndn exacto del día (que depende de bal/pico, ya erosionados).
MAGNITUD_TOQUE = 100_000.0


def _camino_plano():
    return [P0] * NB, [P0] * NB, [P0] * NB


def _camino_con_toque(barra_toque=1):
    """Mismo patrón que `prueba_extraccion_eval_empalme.py::dia_toque_de_suelo`
    (toque en `barra_toque`, precio se queda ahí el resto del día) -- SIN
    reflejar (`calendario.refleja_camino` solo se aplica en el camino
    REPLAY con dirección forzada; aquí la dirección la sortea el bucle de
    verdad). Válido porque `RngControlado` de más abajo GARANTIZA
    dirección LARGA (+1) en todos los días en que se usa este camino --
    con LARGO, "reflejado" es la identidad, así que un camino crudo que
    baja es, sin más vueltas, un toque de SUELO real."""
    ph = [P0] * NB
    pl = list(ph)
    pc = list(ph)
    pl[barra_toque] = P0 - MAGNITUD_TOQUE
    pc[barra_toque] = pl[barra_toque]
    for b in range(barra_toque + 1, NB):
        ph[b] = pl[b] = pc[b] = pc[barra_toque]
    return ph, pl, pc


class FuenteEnVivoConMuerteReal:
    """`ContextoDia.direccion=None` -- el sorteo/CONTRA de
    `bucle_del_dia.py` corre DE VERDAD, sin nada forzado desde un pack.
    Registra, cada día, el camino (plano o con toque) en el MISMO oráculo
    de resolución que usa LA PUERTA GRANDE (`AdaptadorReplaySobrePack`),
    para las dos cuentas prop -- así un bracket colocado por
    `bot/resolucion_en_vivo.py::MaquinaEnVivo` se resuelve solo, por
    precio real, exactamente como en producción (nunca una
    `fabrica_resolucion_bracket()` manual, día a día, a mano)."""

    def __init__(self, n_dias, dia_erosion, dia_muerte, adaptador, cuentas_prop, contador_dia):
        self.n_dias = n_dias
        self.dia_erosion = dia_erosion
        self.dia_muerte = dia_muerte
        self.adaptador = adaptador
        self.cuentas_prop = cuentas_prop
        self.contador_dia = contador_dia
        self._dia_actual = 0
        self._b = -1
        self._ph = self._pl = self._pc = None

    def dia_disponible(self):
        return self._dia_actual < self.n_dias

    def abre_dia(self):
        self._dia_actual += 1
        self.contador_dia.dia = self._dia_actual
        self._b = -1
        if self._dia_actual in (self.dia_erosion, self.dia_muerte):
            self._ph, self._pl, self._pc = _camino_con_toque()
        else:
            self._ph, self._pl, self._pc = _camino_plano()
        for cuenta_prop in self.cuentas_prop:
            self.adaptador.registra_dia(cuenta_prop, self._ph, self._pl, self._pc,
                                         self._pc, barra_inicio=0)
        return ContextoDia()

    def siguiente_barra(self):
        self._b += 1
        barra = Barra(b=self._b, ph=self._ph[self._b], pl=self._pl[self._b],
                       pc=self._pc[self._b], es_ultima_barra_operable=(self._b >= NB - 1))
        self.adaptador.notifica_barra(barra.b)
        return barra

    def cierra_dia(self):
        for cuenta_prop in self.cuentas_prop:
            self.adaptador.quita_dia(cuenta_prop)


class Contador:
    def __init__(self):
        self.dia = 0


class RngControlado:
    """Cualquier llamada a `.random()` (dirección/es_dia_de_dato/resets)
    puede recibir este valor -- `es_dia_de_dato` queda neutralizado por
    `ventana_del_dia` forzada más abajo, y `resets` no se dispara nunca en
    este arnés (pool.rotas se queda en 0, ninguna sub rota) -- así que
    SOLO el sorteo de dirección (cuando `contra_pendiente==0`) depende de
    verdad de este valor. Antes de `dia_cambio`, LARGO (+1) siempre --
    necesario para que el toque de suelo crudo sea un toque de suelo de
    verdad (ver `_camino_con_toque`). A partir de `dia_cambio` (el primer
    día tras expirar CONTRA), CORTO (-1) -- si CONTRA fallara y dejase
    colarse un sorteo libre DENTRO de la ventana, este cambio de signo lo
    delataría (la dirección observada dejaría de coincidir con la del día
    de la muerte)."""

    def __init__(self, contador, dia_cambio):
        self.contador = contador
        self.dia_cambio = dia_cambio

    def random(self):
        return 0.1 if self.contador.dia < self.dia_cambio else 0.9


N_DIAS = 15
DIA_EROSION = 5
DIA_MUERTE = 6   # bal ya erosionado por el dia 5 -> el dia 6 SI muere (R-3.4)
DIA_CAMBIO = DIA_MUERTE + CONTRA_DIAS + 1   # primer día con CONTRA ya expirado

DIR = "/tmp/prueba_sorteo_direccion_contra"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)
ruta_estado = os.path.join(DIR, "estado.json")
E.guardar(E.nuevo("v10", checksum), ruta_estado)

CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES = "CH-EVAL", "CP-EVAL", "CH-FUN", "CP-FUN", "MES"
adaptador = AdaptadorReplaySobrePack(MES, modo='perfecto')
contador_dia = Contador()
fuente = FuenteEnVivoConMuerteReal(N_DIAS, DIA_EROSION, DIA_MUERTE, adaptador,
                                    (CP_EVAL, CP_FUN), contador_dia)

# --- instrumentación: SOLO observa, nunca cambia el cálculo ------------------
# (a) sortea_direccion -- traza (dia_actual, hubo_muerte_ayer, contra_pendiente)
#     tal como los deja orquestador.procesa_dia() al final de CADA día (nota:
#     `dia_actual` ahí ya es `dia_negociacion` DESPUÉS de incrementar -- pero
#     ese incremento ocurre DENTRO de la llamada que procesa el día D, así
#     que el valor que se pasa a sortea_direccion es D, el mismo día que
#     acaba de cerrar, no D+1 -- verificado empíricamente con una traza
#     directa antes de fijar este número, R3).
# (b) orquestador.procesa_dia -- traza la DIRECCIÓN DE VERDAD que usó ese día
#     (el 2º argumento posicional), la que de verdad se tradea -- el valor de
#     retorno de sortea_direccion se DESCARTA en producción (orquestador.py:205,
#     "_, st['contra_pendiente'] = ..."), así que la única forma honesta de
#     verificar "la dirección se mantuvo constante" es mirar lo que
#     bucle_del_dia.py de verdad decidió y pasó a procesa_dia(), no el
#     retorno tirado de sortea_direccion.
# (c) calendario.ventana_del_dia -- forzada a devolver SIEMPRE ('22h', 0), para
#     que la barra b=1 (donde vive la receta de erosión/muerte) esté dentro de
#     la ventana operable pase lo que pase con el sorteo real de es_dia_de_dato
#     -- el rng de dirección queda intacto (vía `RngControlado`, real en el
#     sentido de que el bucle lo consulta de verdad, sin atajos).
# (d) fuente_barras.abre_dia() -- avisa a `contador_dia` de qué día se abre,
#     ANTES de que bucle_del_dia.py sortee la dirección -- así RngControlado
#     sabe en qué día está sin tener que contar llamadas a random().
traza_sortea = []
_orig_sortea = calendario.sortea_direccion
def _traza_sortea(*a, **kw):
    r = _orig_sortea(*a, **kw)
    traza_sortea.append((kw.get('dia_actual'), kw.get('hubo_muerte_ayer'), r[1]))
    return r
calendario.sortea_direccion = _traza_sortea

traza_direccion_real = []   # (dia_negociacion_antes_de_procesar, direccion_usada_de_verdad)
_orig_procesa_dia = O.procesa_dia
def _traza_procesa_dia(st, direccion, *a, **kw):
    traza_direccion_real.append((st['dia_negociacion'] + 1, direccion))
    return _orig_procesa_dia(st, direccion, *a, **kw)
O.procesa_dia = _traza_procesa_dia

_orig_ventana = calendario.ventana_del_dia
def _ventana_forzada_22h(es_dia_de_dato):
    return '22h', 0
calendario.ventana_del_dia = _ventana_forzada_22h

try:
    st_final = BDD.bucle_del_dia(
        fuente, adaptador,
        cuenta_hedge_eval=CH_EVAL, cuenta_prop_eval=CP_EVAL,
        cuenta_hedge_funded=CH_FUN, cuenta_prop_funded=CP_FUN,
        instrumento_prop=MES,
        ruta_estado=ruta_estado, ruta_nivel=os.path.join(DIR, "nivel.json"),
        ruta_ordenes=os.path.join(DIR, "ordenes"), ruta_lock=os.path.join(DIR, "bot.lock"),
        dir_instantaneas=os.path.join(DIR, "instantaneas"), dias_retenidos=5,
        ruta_diario=os.path.join(DIR, "diario.jsonl"),
        rng=RngControlado(contador_dia, DIA_CAMBIO), dormir=lambda s: None)
finally:
    calendario.sortea_direccion = _orig_sortea
    O.procesa_dia = _orig_procesa_dia
    calendario.ventana_del_dia = _orig_ventana

ok(f"integración: los {N_DIAS} días se procesaron de verdad",
   st_final is not None and st_final['dia_negociacion'] == N_DIAS,
   st_final['dia_negociacion'] if st_final is not None else None)

# orquestador.py incrementa st["dia_negociacion"] Y LUEGO llama a
# sortea_direccion con dia_actual=st["dia_negociacion"] -- para la llamada
# que procesa el día D, eso ya vale D (el día que ACABA de cerrar, no
# D+1): la muerte real ocurrida durante DIA_MUERTE se registra con
# hubo_muerte_ayer=True en la entrada de dia_actual == DIA_MUERTE mismo
# (verificado empíricamente contra una traza directa de
# orquestador.procesa_dia antes de fijar este número -- R3: nada se acepta
# sin verse).
entrada_muerte = next((e for e in traza_sortea if e[0] == DIA_MUERTE), None)
ok(f"día {DIA_MUERTE}: hubo_muerte_ayer=True registrado de verdad (la muerte real ocurrió)",
   entrada_muerte is not None and entrada_muerte[1] is True, entrada_muerte)

if entrada_muerte is not None:
    ok(f"día {DIA_MUERTE}: contra_pendiente rearmó a {CONTRA_DIAS}",
       entrada_muerte[2] == CONTRA_DIAS, entrada_muerte[2])

    # dirección de verdad que tradeó el bucle el día DIA_MUERTE (el día de
    # la muerte, antes de que se resolviera) y la que tradeó cada día de la
    # ventana CONTRA (DIA_MUERTE+1 .. DIA_MUERTE+CONTRA_DIAS) -- deben
    # coincidir, leídas de lo que bucle_del_dia.py REALMENTE decidió, no
    # del retorno descartado de sortea_direccion.
    dir_dia_muerte = next((d for dia, d in traza_direccion_real if dia == DIA_MUERTE), None)
    ventana_dias = list(range(DIA_MUERTE + 1, DIA_MUERTE + CONTRA_DIAS + 1))
    dirs_ventana = [(dia, d) for dia, d in traza_direccion_real if dia in ventana_dias]
    ok(f"días {ventana_dias}: la dirección real tradeada por el bucle en vivo se mantuvo "
       f"constante (={dir_dia_muerte}, regla CONTRA de verdad, no solo en aislamiento)",
       len(dirs_ventana) == len(ventana_dias) and all(d == dir_dia_muerte for _, d in dirs_ventana),
       dirs_ventana)

    dia_liberacion = DIA_MUERTE + CONTRA_DIAS
    entrada_liberacion = next((e for e in traza_sortea if e[0] == dia_liberacion), None)
    ok(f"día {dia_liberacion}: contra_pendiente ya en 0 (CONTRA expiró solo, sin intervención)",
       entrada_liberacion is not None and entrada_liberacion[2] == 0, entrada_liberacion)

    dia_libre_tras_expirar = dia_liberacion + 1
    dir_libre = next((d for dia, d in traza_direccion_real if dia == dia_libre_tras_expirar), None)
    ok(f"día {dia_libre_tras_expirar}: el primer sorteo libre tras expirar CONTRA da una "
       f"dirección DISTINTA (={dir_libre}, no {dir_dia_muerte}) -- prueba que la constancia "
       f"de la ventana era CONTRA de verdad, no una coincidencia del propio RNG de la prueba",
       dir_libre is not None and dir_libre != dir_dia_muerte, dir_libre)

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
