# -*- coding: utf-8 -*-
"""D8.4, paso 8b (prueba 8 de la síntesis D8.4 §4): `fuerza_posicion_externa`
a mitad de la vigilancia, DENTRO de un `bot/bucle_del_dia.py` real en marcha
(modo EN VIVO -- `fuente_barras.abre_dia()` devuelve `direccion=None`, así
que el bucle sortea de verdad y construye `ResuelveDiaEnVivo` por slot,
exactamente como en producción).

Exige lo que pide la síntesis: `muere=True`, el hedge cerrado, y
`nivel.json` en N2 -- sin tocar `bot/deteccion_liquidacion.py` ni
`bot/seguridad.py` (D8.3/N0-N4, ya verificados por separado), solo
comprobando que `bot/bucle_del_dia.py`/`ResuelveDiaEnVivo` los enganchan de
verdad en el camino real."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import bucle_del_dia as BDD
from bot import config, estado as E, seguridad as SEG
from bot.adaptador_falso import AdaptadorFalso
from bot.fuente_barras import Barra, ContextoDia

_, checksum = config.cargar()
MES_HEDGE = config.obtener().hedge_broker.instrumento

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


class FuenteEnVivoDePrueba:
    """Fuente EN VIVO de prueba (contrato de `FuenteEnVivo`: `abre_dia()`
    devuelve `direccion=None` -- el bucle sortea de verdad) que sirve UN
    solo día de barras COMPLETAMENTE PLANAS (ph=pl=pc=precio_flat, el mismo
    precio del fill de apertura por defecto de `AdaptadorFalso`, 100.0) --
    así el bracket de D8.2 nunca se resuelve solo, y la vigilancia solo
    termina por la liquidación forzosa (o por el tope de barras, red de
    seguridad de la propia prueba, si -- tras la liquidación -- toca
    empalme y ese intento nuevo sigue sin resolverse él solo).

    Fabrica la liquidación externa UNA SOLA VEZ
    (`adaptador.fuerza_posicion_externa(..., 0)`) -- un evento real de
    liquidación no es algo que ocurra en CADA tick para siempre; es un
    suceso puntual, y eso es justo lo que D8.3 tiene que cazar. Forzar en
    cada tick (probado y descartado -- ver el commit de la reestructuración
    D8.4 concurrente) no converge nunca con el bucle de tiempo compartido:
    cada empalme reabre y se liquida en el MISMO tick antes de que
    `barra_evento` avance ni una barra, así que la ventana de empalme
    (`empalme_barra_limite`) nunca llega a cerrarse -- un patrón que ni
    siquiera corresponde a nada real (una liquidación externa perpetua,
    tick tras tick, no existe en ningún bróker)."""

    def __init__(self, adaptador, cuenta_prop, instrumento_prop, precio_flat, tope_barras=200):
        self.adaptador = adaptador
        self.cuenta_prop = cuenta_prop
        self.instrumento_prop = instrumento_prop
        self.precio_flat = precio_flat
        self.tope_barras = tope_barras   # red de seguridad de la prueba, ver docstring
        self._dia_abierto = False
        self._b = -1
        self.n_forzados = 0
        self._ya_forzado = False

    def dia_disponible(self):
        return not self._dia_abierto

    def abre_dia(self):
        self._dia_abierto = True
        self._b = -1
        return ContextoDia()   # direccion=None -> bucle_del_dia sortea de verdad

    def siguiente_barra(self):
        self._b += 1
        if not self._ya_forzado:
            pos, _ = self.adaptador.leer_posicion(self.cuenta_prop, self.instrumento_prop)
            if pos != 0:
                self.n_forzados += 1
                self._ya_forzado = True
                self.adaptador.fuerza_posicion_externa(self.cuenta_prop, self.instrumento_prop, 0)
        p = self.precio_flat
        return Barra(b=self._b, ph=p, pl=p, pc=p,
                     es_ultima_barra_operable=(self._b >= self.tope_barras))

    def cierra_dia(self):
        pass


class RngFijo:
    """`random.Random` de prueba: SIEMPRE devuelve 0.9 -- con
    `frac_dias_dato=0.18` (03_CONFIG.yaml), fuerza ventana '22h'
    (`barra_inicio=0`, determinista) sin importar cuántas veces se llame;
    la dirección sorteada (0.9 >= 0.5 -> corta) no importa para esta
    prueba, solo que sea determinista."""
    def random(self):
        return 0.9


DIR = "/tmp/prueba_bucle_del_dia_liquidacion"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)

CUENTA_HEDGE_EVAL, CUENTA_PROP_EVAL = "CH-EVAL", "CP-EVAL"
CUENTA_HEDGE_FUN, CUENTA_PROP_FUN = "CH-FUN", "CP-FUN"
INSTRUMENTO_PROP = "MES"

ruta_estado = os.path.join(DIR, "estado.json")
ruta_nivel = os.path.join(DIR, "nivel.json")
E.guardar(E.nuevo("v10", checksum), ruta_estado)

adaptador = AdaptadorFalso()
# fill de apertura por defecto de AdaptadorFalso: 100.0 (bot/adaptador_falso.py::_llena) --
# las barras planas de la fuente usan el MISMO precio, así el bracket (colocado a
# p0_real ± ndn/nu) nunca lo cruza ninguna barra.
fuente = FuenteEnVivoDePrueba(adaptador, CUENTA_PROP_EVAL, INSTRUMENTO_PROP, precio_flat=100.0)

print("=== bucle_del_dia() EN VIVO, 1 día, liquidación forzosa a mitad de la vigilancia ===")
st_final = BDD.bucle_del_dia(
    fuente, adaptador,
    cuenta_hedge_eval=CUENTA_HEDGE_EVAL, cuenta_prop_eval=CUENTA_PROP_EVAL,
    cuenta_hedge_funded=CUENTA_HEDGE_FUN, cuenta_prop_funded=CUENTA_PROP_FUN,
    instrumento_prop=INSTRUMENTO_PROP,
    ruta_estado=ruta_estado, ruta_nivel=ruta_nivel,
    ruta_ordenes=os.path.join(DIR, "ordenes"), ruta_lock=os.path.join(DIR, "bot.lock"),
    dir_instantaneas=os.path.join(DIR, "instantaneas"), dias_retenidos=5,
    ruta_diario=os.path.join(DIR, "diario.jsonl"),
    rng=RngFijo(), dormir=lambda s: None)

ok("bucle_del_dia() no devolvió None (estado.json cargó y validó bien)", st_final is not None)
ok("se procesó exactamente 1 día (la fuente solo ofrecía uno)",
   st_final is not None and st_final['dia_negociacion'] == 1,
   st_final['dia_negociacion'] if st_final is not None else None)

print("\n=== la liquidación forzosa se detectó y se reaccionó de verdad ===")
ok("la fuente forzó al menos una liquidación externa de verdad (la prop SÍ llegó a abrir)",
   fuente.n_forzados >= 1, fuente.n_forzados)
ok("nivel.json subió a N2 (\"plano y parado hoy\", 10_SEGURIDAD.md §3)",
   SEG.nivel_actual(ruta_nivel) == 'N2', SEG.nivel_actual(ruta_nivel))
registro_nivel = SEG.lee_nivel(ruta_nivel)
historial = registro_nivel.get('historial', [])
ok("el historial de nivel.json documenta el motivo (liquidación forzosa)",
   any('liquidaci' in h.get('motivo', '').lower() for h in historial), historial)

print("\n=== el hedge quedó cerrado de verdad (nunca se queda huérfano) ===")
cant_hedge, _ = adaptador.leer_posicion(CUENTA_HEDGE_EVAL, MES_HEDGE)
ok("posición del hedge EVAL en CERO tras la liquidación forzosa de la prop",
   cant_hedge == 0, cant_hedge)
cant_prop, _ = adaptador.leer_posicion(CUENTA_PROP_EVAL, INSTRUMENTO_PROP)
ok("posición de la prop EVAL en CERO (la fuente la fuerza en cuanto ve algo abierto)",
   cant_prop == 0, cant_prop)

print("\n=== el diario refleja la(s) muerte(s) de la sesión eval de hoy ===")
import json
diario_leido = [json.loads(l) for l in open(os.path.join(DIR, "diario.jsonl"))]
ok("1 línea de diario escrita", len(diario_leido) == 1, len(diario_leido))
ok("eventos.muertes_eval == nº de liquidaciones forzadas (cada una cuenta como muerte del día)",
   diario_leido[0]['eventos']['muertes_eval'] == fuente.n_forzados,
   (diario_leido[0]['eventos'], fuente.n_forzados))

print("\n=== la regla CONTRA se rearma para mañana (hubo muerte hoy) ===")
ok("contra_pendiente > 0 tras la muerte de hoy",
   st_final['contra_pendiente'] > 0, st_final['contra_pendiente'])

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
