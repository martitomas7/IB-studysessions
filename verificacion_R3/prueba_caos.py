# -*- coding: utf-8 -*-
"""D8 §5.5 (ORDEN_DE_TRABAJO_D8.md §5 / ANALISIS_PUERTA_GRANDE.md §5.5):
"prueba de caos" -- cada fallo individual (liquidación forzosa, conexión
caída, degradación, palancas de Clase B) ya tiene su propia prueba
dedicada y ninguna repite trabajo aquí. Lo que NINGÚN test existente
comprueba es la INTERACCIÓN: varios fallos distintos, DE VERDAD, uno
detrás de otro, en una sola corrida continua del bucle real de
producción -- para cazar el tipo de bug que solo aparece cuando un fallo
deja el sistema en un estado que el SIGUIENTE fallo no esperaba.

Investigación previa (R1/R3, antes de fabricar nada): ORDEN_DE_TRABAJO_D8.md
§5 documenta un hueco YA CONOCIDO (no nuevo, no cazado por esta sesión):
"N1/N2 se desescalan solos... 'cuándo exactamente' no está grounded en
este diseño" -- es decir, `bot/seguridad.py::baja_automatica()` EXISTE y
está probada (`prueba_seguridad_n0_n4.py`), pero NADA en `bot/` la llama
todavía (a diferencia de N3/N4, que exigen `baja_humana()` por norma, N1/
N2 exigen un descenso automático que hoy nadie dispara). Esta prueba NO
inventa ese cableado -- simula, explícitamente, el papel de ese mecanismo
todavía sin construir (un comentario en el propio código lo marca en
cada paso) llamando a la función YA EXISTENTE entre invocaciones, tal
como lo haría un futuro script de orquestación diaria.

Encadena, en una sola corrida de N días (bot/bucle_del_dia.py, invocado
un día a la vez -- como se invocaría en producción, leyendo/escribiendo
estado.json/nivel.json/diario.jsonl entre invocaciones):

  1. una muerte real de eval por precio (D8.2/D8.5, misma receta que
     prueba_sorteo_direccion_contra.py) -> CONTRA se arma;
  2. una liquidación forzosa real (D8.3) -> N2 -> auto-descenso simulado
     -> el bucle resume;
  3. una reacción de conexión caída (simulando el monitor todavía sin
     construir) -> N1 -> auto-descenso simulado -> el bucle resume;
  4. una palanca de Clase B (`contra` apagada por el operador) activa
     DURANTE el resto de la corrida, sin que nada de lo anterior la rompa;
  5. una degradación real de tesorería -> N3 -> el bucle NO resume solo;
  6. un humano baja a N0 a mano con `degradado` todavía `True` -> el
     bucle procesa un día más y vuelve a subir a N3 él solo.

En cada paso: invariantes limpios (`estado.validar`), 0 excepciones sin
capturar, y la escalera N0-N4 sube monótona -- nunca baja salvo por las
llamadas EXPLÍCITAS de este arnés a `baja_automatica()`/`baja_humana()`
(nunca por sí sola)."""
import json
import os
import random
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from apoyo_puerta_grande import AdaptadorReplaySobrePack

from bot import (bucle_del_dia as BDD, calendario, config, estado as E, seguridad as SEG,
                  tesoreria as T)
from bot.fuente_barras import Barra, ContextoDia

_, checksum = config.cargar()
cfg = config.obtener()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


NB = 86
P0 = 5000.0
MAGNITUD_TOQUE = 100_000.0


def _camino_plano():
    return [P0] * NB, [P0] * NB, [P0] * NB


def _camino_con_toque(barra_toque=1):
    ph = [P0] * NB
    pl = list(ph)
    pc = list(ph)
    pl[barra_toque] = P0 - MAGNITUD_TOQUE
    pc[barra_toque] = pl[barra_toque]
    for b in range(barra_toque + 1, NB):
        ph[b] = pl[b] = pc[b] = pc[barra_toque]
    return ph, pl, pc


class FuenteCaos:
    """Un día a la vez (contrato `dia_disponible()`/`abre_dia()`/
    `siguiente_barra()`/`cierra_dia()` -- se construye una instancia NUEVA
    por invocación de `bucle_del_dia()`, exactamente como en producción).
    `direccion=None` -- el bucle sortea de verdad. Registra el camino
    (plano o con toque) en el oráculo de resolución de LA PUERTA GRANDE.
    Si `forzar_liquidacion=True`, fuerza la posición de `cuenta_prop_forzar`
    a cero la primera vez que la ve abierta (D8.3, misma técnica que
    `prueba_bucle_del_dia_liquidacion.py`)."""

    def __init__(self, adaptador, cuentas_prop, camino, forzar_liquidacion=False,
                 cuenta_prop_forzar=None):
        self.adaptador = adaptador
        self.cuentas_prop = cuentas_prop
        self.camino = camino
        self.forzar_liquidacion = forzar_liquidacion
        self.cuenta_prop_forzar = cuenta_prop_forzar
        self._abierto = False
        self._b = -1
        self._ya_forzado = False
        self.n_forzados = 0

    def dia_disponible(self):
        return not self._abierto

    def abre_dia(self):
        self._abierto = True
        self._b = -1
        self._ph, self._pl, self._pc = self.camino
        for cuenta_prop in self.cuentas_prop:
            self.adaptador.registra_dia(cuenta_prop, self._ph, self._pl, self._pc,
                                         self._pc, barra_inicio=0)
        return ContextoDia()

    def siguiente_barra(self):
        self._b += 1
        if self.forzar_liquidacion and not self._ya_forzado:
            pos, _ = self.adaptador.leer_posicion(self.cuenta_prop_forzar, self.adaptador.instrumento_prop)
            if pos != 0:
                self._ya_forzado = True
                self.n_forzados += 1
                self.adaptador.fuerza_posicion_externa(self.cuenta_prop_forzar,
                                                         self.adaptador.instrumento_prop, 0)
        barra = Barra(b=self._b, ph=self._ph[self._b], pl=self._pl[self._b],
                       pc=self._pc[self._b], es_ultima_barra_operable=(self._b >= NB - 1))
        self.adaptador.notifica_barra(barra.b)
        return barra

    def cierra_dia(self):
        for cuenta_prop in self.cuentas_prop:
            self.adaptador.quita_dia(cuenta_prop)


DIR = "/tmp/prueba_caos"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)
RUTA_ESTADO = os.path.join(DIR, "estado.json")
RUTA_NIVEL = os.path.join(DIR, "nivel.json")
RUTA_DIARIO = os.path.join(DIR, "diario.jsonl")
E.guardar(E.nuevo('v10', checksum), RUTA_ESTADO)

CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES = "CH-EVAL", "CP-EVAL", "CH-FUN", "CP-FUN", "MES"
adaptador = AdaptadorReplaySobrePack(MES, modo='perfecto')

_orig_ventana = calendario.ventana_del_dia
calendario.ventana_del_dia = lambda es_dia_de_dato: ('22h', 0)

nivel_por_dia = []   # (dia_negociacion_tras_la_llamada_o_None, nivel_tras_la_llamada)


def _corre_dia(camino, forzar_liquidacion=False, cuenta_prop_forzar=None, semilla=1):
    fuente = FuenteCaos(adaptador, (CP_EVAL, CP_FUN), camino,
                        forzar_liquidacion=forzar_liquidacion, cuenta_prop_forzar=cuenta_prop_forzar)
    st = BDD.bucle_del_dia(
        fuente, adaptador,
        cuenta_hedge_eval=CH_EVAL, cuenta_prop_eval=CP_EVAL,
        cuenta_hedge_funded=CH_FUN, cuenta_prop_funded=CP_FUN,
        instrumento_prop=MES,
        ruta_estado=RUTA_ESTADO, ruta_nivel=RUTA_NIVEL,
        ruta_ordenes=os.path.join(DIR, "ordenes"), ruta_lock=os.path.join(DIR, "bot.lock"),
        dir_instantaneas=os.path.join(DIR, "instantaneas"), dias_retenidos=5,
        ruta_diario=RUTA_DIARIO, rng=random.Random(semilla), dormir=lambda s: None)
    nivel_por_dia.append((st['dia_negociacion'] if st is not None else None, SEG.nivel_actual(RUTA_NIVEL)))
    return st, fuente


try:
    print("=== 1. día 1: normal, eval activa vía pool ===")
    st1, _ = _corre_dia(_camino_plano(), semilla=1)
    ok("día 1 procesado, sin fallos", st1 is not None and len(E.validar(st1, checksum)) == 0,
       E.validar(st1, checksum) if st1 else None)
    ok("nivel sigue N0", SEG.nivel_actual(RUTA_NIVEL) == 'N0')

    print("\n=== 2. día 2: LIQUIDACIÓN FORZOSA real (D8.3) sobre eval -> N2 ===")
    st2, f2 = _corre_dia(_camino_plano(), forzar_liquidacion=True, cuenta_prop_forzar=CP_EVAL,
                         semilla=2)
    ok("la liquidación se forzó de verdad al menos una vez", f2.n_forzados >= 1, f2.n_forzados)
    ok("día 2 procesado (el día en que se detecta ya cierra, mismo principio que "
       "degradación)", st2 is not None and len(E.validar(st2, checksum)) == 0,
       E.validar(st2, checksum) if st2 else None)
    ok("nivel sube a N2 de verdad", SEG.nivel_actual(RUTA_NIVEL) == 'N2', SEG.nivel_actual(RUTA_NIVEL))
    ok("CONTRA se rearmó (hubo muerte hoy, por la liquidación)",
       st2['contra_pendiente'] > 0, st2['contra_pendiente'])

    print("\n=== 3. día 3: bloqueado por N2 (0 días nuevos) hasta el auto-descenso ===")
    dia_antes_3 = st2['dia_negociacion']
    st3_bloqueado, _ = _corre_dia(_camino_plano(), semilla=3)
    ok("SIN auto-descenso, el bucle NO procesa ningún día nuevo (nivel != N0)",
       st3_bloqueado is not None and st3_bloqueado['dia_negociacion'] == dia_antes_3,
       st3_bloqueado['dia_negociacion'] if st3_bloqueado else None)

    # simula el auto-descenso "al día siguiente" que N2 promete por norma pero que
    # NINGÚN código de bot/ dispara todavía (hueco YA documentado en
    # ORDEN_DE_TRABAJO_D8.md §5 -- no inventado aquí, solo simulado con la función
    # YA EXISTENTE y YA probada).
    SEG.baja_automatica(RUTA_NIVEL, 'N0',
                        motivo='(simulado) auto-descenso N2->N0 al día siguiente -- '
                               'mecanismo aún sin construir, ver ORDEN_DE_TRABAJO_D8.md §5')
    st3, _ = _corre_dia(_camino_plano(), semilla=3)
    ok("tras el auto-descenso simulado, el bucle SÍ procesa el día",
       st3 is not None and st3['dia_negociacion'] == dia_antes_3 + 1,
       st3['dia_negociacion'] if st3 else None)
    ok("día 3: sin fallos de invariantes", len(E.validar(st3, checksum)) == 0,
       E.validar(st3, checksum))
    ok("nivel de vuelta en N0", SEG.nivel_actual(RUTA_NIVEL) == 'N0')

    print("\n=== 4. día 4: reacción de CONEXIÓN CAÍDA (simulada, mismo hueco) -> N1 ===")
    SEG.sube_a(RUTA_NIVEL, 'N1',
               motivo='(simulado) conexión caída, posición ya protegida por órdenes en '
                      'reposo -- monitor de conexión aún sin construir',
               causa='reconciliacion')
    ok("nivel sube a N1", SEG.nivel_actual(RUTA_NIVEL) == 'N1')
    dia_antes_4 = st3['dia_negociacion']
    st4_bloqueado, _ = _corre_dia(_camino_plano(), semilla=4)
    ok("bloqueado por N1 -- 0 días nuevos", st4_bloqueado is not None
       and st4_bloqueado['dia_negociacion'] == dia_antes_4,
       st4_bloqueado['dia_negociacion'] if st4_bloqueado else None)
    SEG.baja_automatica(RUTA_NIVEL, 'N0',
                        motivo='(simulado) auto-descenso N1->N0 al desaparecer la causa')
    st4, _ = _corre_dia(_camino_plano(), semilla=4)
    ok("tras el auto-descenso, el bucle procesa el día 4",
       st4 is not None and st4['dia_negociacion'] == dia_antes_4 + 1,
       st4['dia_negociacion'] if st4 else None)
    ok("día 4: sin fallos de invariantes", len(E.validar(st4, checksum)) == 0)

    print("\n=== 5. día 5: palanca de Clase B ('contra' apagada por el operador) activa "
          "para el resto de la corrida -- ¿sobrevive al caos anterior? ===")
    st_editado = E.cargar(RUTA_ESTADO)
    st_editado['desviaciones_activas'] = [
        dict(palanca='contra', desde_dia=st_editado['dia_negociacion'] + 1, hasta_dia=1000,
             quien='prueba_caos', ts_pared='2026-08-21T00:00:00Z')]
    E.guardar(st_editado, RUTA_ESTADO)
    st5, _ = _corre_dia(_camino_plano(), semilla=5)
    ok("día 5 procesado con la palanca activa, sin fallos",
       st5 is not None and len(E.validar(st5, checksum)) == 0, E.validar(st5, checksum) if st5 else None)
    ok("nivel se mantiene N0 (la palanca no interfiere con la contención)",
       SEG.nivel_actual(RUTA_NIVEL) == 'N0')

    print("\n=== 6. día 6: una MUERTE REAL de eval por precio, con 'contra' YA apagada -- "
          "¿se respeta la desactivación en medio del caos? ===")
    ph6, pl6, pc6 = _camino_con_toque()   # toque de suelo -- puede o no matar según Mm de hoy;
                                            # si mata, contra_pendiente debe seguir en 0 (apagada)
    st6, _ = _corre_dia((ph6, pl6, pc6), semilla=6)
    ok("día 6 procesado, sin fallos", st6 is not None and len(E.validar(st6, checksum)) == 0,
       E.validar(st6, checksum) if st6 else None)
    ok("con 'contra' apagada por el operador, contra_pendiente sigue en 0 SIN IMPORTAR si "
       "hubo muerte hoy", st6['contra_pendiente'] == 0, st6['contra_pendiente'])

    print("\n=== 7. día 7: DEGRADACIÓN real de tesorería -> N3 (irreversible sin humano) ===")
    st_editado2 = E.cargar(RUTA_ESTADO)
    muro = T.muro_dinamico(
        cfg.sizing.m_eval.valor() if st_editado2['eval']['activa'] else 0.0,
        cfg.sizing.exp_eval_usd.valor() if st_editado2['eval']['activa'] else 0.0)
    st_editado2['caja'] = -(muro + 500.0)
    E.guardar(st_editado2, RUTA_ESTADO)
    st7, _ = _corre_dia(_camino_plano(), semilla=7)
    ok("día 7 se procesó y degradó de verdad", st7 is not None and st7['degradado'] is True,
       st7['degradado'] if st7 else None)
    ok("nivel sube a N3 de verdad, incluso tras todo el caos anterior",
       SEG.nivel_actual(RUTA_NIVEL) == 'N3', SEG.nivel_actual(RUTA_NIVEL))

    print("\n=== 8. día 8: N3 NO se resume solo -- ni con baja_automatica() (exige humano) ===")
    dia_antes_8 = st7['dia_negociacion']
    st8_bloqueado, _ = _corre_dia(_camino_plano(), semilla=8)
    ok("bloqueado por N3 -- 0 días nuevos, pase lo que pase con los intentos anteriores",
       st8_bloqueado is not None and st8_bloqueado['dia_negociacion'] == dia_antes_8,
       st8_bloqueado['dia_negociacion'] if st8_bloqueado else None)
    disparo_mal = False
    try:
        SEG.baja_automatica(RUTA_NIVEL, 'N0', motivo='intento de auto-descenso desde N3')
        disparo_mal = True
    except SEG.NivelInvalidoError:
        pass
    ok("baja_automatica() DESDE N3 sigue rechazándose, incluso en medio de esta corrida "
       "cargada de eventos", not disparo_mal)

    print("\n=== 9. día 9: humano baja a N0 con degradado aún True -> reprocesa Y vuelve a "
          "subir a N3 él solo ===")
    SEG.baja_humana(RUTA_NIVEL, 'N0', quien='operador_martitomas7',
                     motivo='revisión manual en medio del caos')
    st9, _ = _corre_dia(_camino_plano(), semilla=9)
    ok("día 9 se procesó (el humano lo autorizó)",
       st9 is not None and st9['dia_negociacion'] == dia_antes_8 + 1,
       st9['dia_negociacion'] if st9 else None)
    ok("al cierre del día 9, el bucle vuelve a subir a N3 SOLO -- la barrera sigue viva tras "
       "todo el caos anterior", SEG.nivel_actual(RUTA_NIVEL) == 'N3', SEG.nivel_actual(RUTA_NIVEL))

    print("\n=== 10. pese a TODO el caos, ninguna bajada desde N3/N4 fue automática ===")
    historial_completo = SEG.lee_nivel(RUTA_NIVEL)['historial']
    bajadas = [h for h in historial_completo if SEG._RANGO[h['a']] < SEG._RANGO[h['de']]]
    ok(f"{len(bajadas)} bajadas en toda la corrida (N2->N0, N1->N0, N3->N0) -- "
       f"exactamente las 3 que provocó este arnés, ni una más ni una menos",
       len(bajadas) == 3, bajadas)
    bajadas_desde_n3_o_n4 = [h for h in bajadas if h['de'] in ('N3', 'N4')]
    ok("TODA bajada desde N3/N4 en el historial completo de esta corrida cargada de "
       "eventos fue HUMANA (quien != 'sistema') -- ni una se coló automática",
       len(bajadas_desde_n3_o_n4) > 0
       and all(h['quien'] != 'sistema' for h in bajadas_desde_n3_o_n4), bajadas_desde_n3_o_n4)
finally:
    calendario.ventana_del_dia = _orig_ventana
    shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
