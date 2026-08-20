# -*- coding: utf-8 -*-
"""D8.4 reestructuración, paso 4/5: `bot.bucle_de_tiempo.resuelve_dia_concurrente`
-- funded y eval corriendo el MISMO día, DE VERDAD a la vez (compartiendo
una sola fuente de barras, un solo adaptador), comparados contra llamar a
`ciclo_vida.procesa_dia_funded`/`procesa_dia_eval` POR SEPARADO con el
oráculo (`sesion.resolver_dia`) sobre el mismo array -- si la concurrencia
no corrompe nada, el resultado de cada cuenta tiene que ser IDÉNTICO al
que le habría dado en solitario (cada máquina solo mira su propio
`barra_inicio`, nunca lo que le pase a la otra).

Incluye el caso que de verdad motivó la reestructuración
(RESPUESTA_D8_CONCURRENCIA.md): funded Y eval activas el mismo día, con
eval además empalmando (R-4.3) -- para probar que armar la máquina nueva
del empalme A MITAD del bucle compartido no descarrila la vigilancia de
funded, que sigue corriendo en paralelo mientras tanto."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from apoyo_oraculo_en_vivo import AdaptadorOraculoSobreCamino, FuenteConNotificacion, escanea_resolucion

from bot import calendario, config, ciclo_vida as CV, sesion as SES
from bot.bucle_de_tiempo import resuelve_dia_concurrente
from bot.fuente_barras import FuenteDeReplay

_, checksum = config.cargar()
cfg = config.obtener()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


CH_EVAL, CP_EVAL, CH_FUN, CP_FUN, MES = "CH-EVAL", "CP-EVAL", "CH-FUN", "CP-FUN", "MES"
DIR = "/tmp/prueba_bucle_de_tiempo"
NB = 86

print("=== armando el día: funded activa + eval con erosión de un día previo (empalma de verdad) ===")

# --- funded: activa, fase 1, con algo de historia -- trading sobre el
#     MISMO día que eval, con un patrón de precio DISTINTO al de eval
#     (ver más abajo) para poder verificar que cada máquina resuelve SOLO
#     con lo que le corresponde. ------------------------------------------------
funded_estado0 = dict(activa=True, fase=1, bal=0.0, pico=0.0, H=0.0, s0=1000.0, dias=5)

# --- eval: ya activa desde un "día anterior" (misma receta que
#     prueba_extraccion_eval_empalme.py -- un toque de suelo fresco nunca
#     muere solo, R-3.4; con el bal ya erosionado por ESE toque, sizing.plan
#     encoge Mm lo bastante como para que HOY un segundo toque SÍ muera,
#     bien dentro de la ventana de empalme). El estado de partida (bal=-1057)
#     es el golden ya verificado en prueba_extraccion_eval_empalme.py.
eval_estado0 = dict(activa=True, bal=-1057.0, pico=0.0, H=60.66666666666667, s0=77.0,
                     k=30, m=2, aprobada_provisional=False, aprobada_confirmada=False)
pool_estado0 = dict(frescas=4, rotas=0, subs=[])

direccion = 1
# el MISMO patrón de precio de prueba_extraccion_eval_empalme.py (día 2,
# el que hace que eval muera en barra 1 y el empalme suba a tocar objetivo
# en la barra 5) -- funded, con SU PROPIO plan (ndn/nu/Mm distintos, m_fun
# en vez de m_eval), reacciona al MISMO camino con SU propio desenlace.
p0 = 5000.0
ph = [p0] * NB
pl = [p0] * NB
pc = [p0] * NB
pl[1] = p0 - 20.0
pc[1] = pl[1]
p0_empalme = pl[1]
ph[5] = p0_empalme + 50.0
pc[5] = ph[5]
for b in range(6, NB):
    ph[b] = pl[b] = pc[b] = pc[5]
for b in range(2, 5):
    ph[b] = pl[b] = pc[b] = p0_empalme

ph_ref, pl_ref, pc_ref = calendario.refleja_camino(ph, pl, pc, direccion)

print("\n=== oráculo secuencial: procesa_dia_funded()/procesa_dia_eval() por separado, mismo día ===")
r_funded_oraculo = CV.procesa_dia_funded(dict(funded_estado0), direccion, ph_ref, pl_ref, pc_ref,
                                          b0v=0, es_dia_nuevo=False)
st_para_qcap = dict(pool=dict(pool_estado0), caja=0.0, retirado=0.0)
qok = CV.qcap_abierto(0) or CV.qcap_abierto_por_tesoreria(0.0, 0.0)   # recamara=0, sin tope de tesoreria
r_eval_oraculo = CV.procesa_dia_eval(dict(eval_estado0), dict(pool_estado0), [], direccion,
                                      ph_ref, pl_ref, pc_ref, b0v=0, qok=qok, modo_auto_confirma=True,
                                      estado=st_para_qcap, dia_actual=2)
print("  r_funded_oraculo:", r_funded_oraculo)
print("  r_eval_oraculo:", r_eval_oraculo)
ok("receta: funded SOBREVIVE en el oráculo (para que de verdad corra concurrente todo el día)",
   r_funded_oraculo['hubo_muerte'] is False, r_funded_oraculo)
ok("receta: eval MUERE Y EMPALMA en el oráculo (2 intentos totales -- 1 el empalme)",
   r_eval_oraculo['hubo_muerte'] is True and r_eval_oraculo['eventos']['muertes_eval'] == 1
   and r_eval_oraculo['eventos']['intentos'] == 1, r_eval_oraculo['eventos'])

print("\n=== bucle_de_tiempo.resuelve_dia_concurrente(): funded Y eval a la vez, un solo fuente_barras ===")
shutil.rmtree(DIR, ignore_errors=True)
ruta_ordenes = os.path.join(DIR, "ordenes")
ruta_nivel = os.path.join(DIR, "nivel.json")

adaptador = AdaptadorOraculoSobreCamino()
adaptador.programa_abrir(CP_FUN, MES, precio_fill=pc[0])
adaptador.programa_abrir(CH_FUN, MES, precio_fill=100.0)
adaptador.programa_abrir(CP_EVAL, MES, precio_fill=pc[1])   # eval YA estaba activa -- entra en b0v=0 igual
adaptador.programa_abrir(CH_EVAL, MES, precio_fill=100.0)

# el oráculo YA nos dijo qué pierna/barra resuelve cada uno -- se arma el
# fabricante de fills con la MISMA lógica de escaneo que usan las demás
# pruebas de este paquete (apoyo_oraculo_en_vivo.py), independientemente
# para cada cuenta (funded y eval piden brackets DISTINTOS, en grupos OCO
# DISTINTOS -- el adaptador captura 'ultimo_grupo_oco' por cada llamada a
# coloca_bracket(), así que hay que armar la resolución de CADA UNO justo
# antes/despues de que su propio bracket exista). Como los dos entran en
# la MISMA barra (b0v=0), coloca_bracket() se llamará en un orden que no
# controlamos aquí (depende de qué máquina se construye primero dentro de
# resuelve_dia_concurrente) -- se resuelve armando la notificación DESPUÉS
# de que cada coloca_bracket() ya haya ocurrido, vía un fuente que avisa
# tras cada barra Y permite re-armar el disparador cuantas veces haga
# falta (los grupos OCO son todos distintos, así que no hay colisión).

# funded: con SU plan real (hay que conocerlo para escanear su resolución).
plan_funded = CV.arma_intento_funded(funded_estado0)['plan']
pierna_fun, bevt_fun = escanea_resolucion(ph_ref, pl_ref, pc_ref, 0, plan_funded['ndn'], plan_funded['nu'])
print(f"  funded: plan={plan_funded}  pierna={pierna_fun}@{bevt_fun}")

# eval intento 0: con el plan que arma_intento_eval calcularía sobre bal=-1057.
plan_eval0 = CV.arma_intento_eval(eval_estado0, pool_estado0, 0.0,
                                   dict(intentos=0, aprobaciones=0, emergencias=0, recompras=0,
                                        muertes_eval=0), qok, True, st_para_qcap, 2)['plan']
pierna_eval0, bevt_eval0 = escanea_resolucion(ph_ref, pl_ref, pc_ref, 0, plan_eval0['ndn'], plan_eval0['nu'])
print(f"  eval intento 0: plan={plan_eval0}  pierna={pierna_eval0}@{bevt_eval0}")

# eval empalme: mismo plan2 que ya verificamos en prueba_extraccion_eval_empalme.py
# (bal=0/pico=0/H=0 con friccion_empalme) -- b0=bevt_eval0 (donde murió el intento 0).
cuota = cfg.proveedor.cuota_sub_usd.valor()
b_eval = cfg.sizing.b_eval_usd.valor()
factor = cfg.orquestacion.empalme_friccion_factor.valor()
spr = cfg.hedge_broker.spr_usd.valor()
slip_micro = cfg.hedge_broker.slip_usd_micro.valor()
m_eval = cfg.sizing.m_eval.valor()
from bot import sizing as SIZ
friccion_empalme = spr * m_eval * factor
plan_empalme = SIZ.plan(bal=0.0, pico=0.0, G=max(cuota, 0.0) + b_eval, H=0.0, fric=friccion_empalme,
                         m=m_eval, EXP=cfg.sizing.exp_eval_usd.valor(),
                         T=cfg.proveedor.objetivo_eval_usd.valor(), dcap=1e18,
                         kcap=cfg.sizing.kcap.valor())
pierna_emp, bevt_emp = escanea_resolucion(ph_ref, pl_ref, pc_ref, bevt_eval0,
                                           plan_empalme['ndn'], plan_empalme['nu'])
print(f"  eval empalme: plan={plan_empalme}  pierna={pierna_emp}@{bevt_emp}")

# arma las TRES resoluciones (funded, eval intento0, eval empalme) -- el
# adaptador dispara cada una por su propio id_grupo_oco, capturado en el
# momento en que coloca_bracket() de esa cuenta se llame de verdad. Como
# arma_resolucion()/notifica_barra() son de UN solo disparador a la vez en
# AdaptadorOraculoSobreCamino, y aquí hacen falta varios simultáneos
# (funded Y eval intento0 viven la MISMA franja de barras 0..1), se arma
# un pequeño enrutador que sustituye notifica_barra por una versión que
# reparte a una lista de disparadores pendientes.
disparadores_pendientes = []   # lista de (cuenta_prop, b_disparo, pierna, precio_fill)

class _AdaptadorMultiDisparo(AdaptadorOraculoSobreCamino):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._grupo_por_cuenta = {}

    def coloca_bracket(self, cuenta, *a, **kw):
        r = super().coloca_bracket(cuenta, *a, **kw)
        self._grupo_por_cuenta[cuenta] = r['id_grupo_oco']
        return r

    def notifica_barra(self, b):
        restantes = []
        for cuenta, b_disp, pierna, precio_fill in disparadores_pendientes:
            grupo = self._grupo_por_cuenta.get(cuenta)
            if grupo is not None and b == b_disp:
                self.fabrica_resolucion_bracket(grupo, pierna, precio_fill=precio_fill)
            else:
                restantes.append((cuenta, b_disp, pierna, precio_fill))
        disparadores_pendientes[:] = restantes

adaptador = _AdaptadorMultiDisparo()
adaptador.programa_abrir(CP_FUN, MES, precio_fill=pc[0])
adaptador.programa_abrir(CH_FUN, MES, precio_fill=100.0)
adaptador.programa_abrir(CP_EVAL, MES, precio_fill=pc[1])
adaptador.programa_abrir(CH_EVAL, MES, precio_fill=100.0)

if pierna_fun == 'campana':
    adaptador.arma_cierre_campana(CP_FUN, MES, precio_cierre=pc[NB - 1])
else:
    disparadores_pendientes.append((CP_FUN, bevt_fun, pierna_fun, None))
disparadores_pendientes.append((CP_EVAL, bevt_eval0, pierna_eval0, None))
# el disparador del EMPALME se arma más tarde (tras reprogramar el fill de
# apertura de CP_EVAL, igual que hace prueba_reentrancia_empalme.py) --
# ver el gancho de abajo.

fuente_interna = FuenteDeReplay([{
    "direccion": direccion, "ventana": "22h",
    "barras": {"ph": ph, "pl": pl, "pc": pc}, "eventos": {"resets": 0},
}])
fuente_interna.abre_dia()


class _FuenteArmaEmpalme:
    """Envuelve FuenteConNotificacion -- en cuanto se sirve la barra del
    empalme (bevt_eval0), reprograma el fill de apertura de CP_EVAL para
    la SEGUNDA orden (el empalme abre una posición NUEVA) y arma su
    disparador -- mismo principio que prueba_reentrancia_empalme.py, pero
    disparado por barra servida en vez de por llamada manual."""
    def __init__(self, fuente, adaptador):
        self._fuente = FuenteConNotificacion(fuente, adaptador)
        self._adaptador = adaptador
        self._armado = False

    def dia_disponible(self):
        return self._fuente.dia_disponible()

    def abre_dia(self):
        return self._fuente.abre_dia()

    def cierra_dia(self):
        return self._fuente.cierra_dia()

    def siguiente_barra(self):
        barra = self._fuente.siguiente_barra()
        if barra is not None and barra.b == bevt_eval0 and not self._armado:
            self._armado = True
            self._adaptador.programa_abrir(CP_EVAL, MES, precio_fill=pc[bevt_eval0])
            self._adaptador.programa_abrir(CH_EVAL, MES, precio_fill=100.0)
            if pierna_emp == 'campana':
                self._adaptador.arma_cierre_campana(CP_EVAL, MES, precio_cierre=pc[NB - 1])
            else:
                disparadores_pendientes.append((CP_EVAL, bevt_emp, pierna_emp, None))
        return barra


fuente = _FuenteArmaEmpalme(fuente_interna, adaptador)

r_funded_concurrente, r_eval_concurrente = resuelve_dia_concurrente(
    dict(funded=dict(funded_estado0), eval=dict(eval_estado0), pool=dict(pool_estado0),
         caja=0.0, retirado=0.0),
    direccion, b0v=0, qok=qok, modo_auto_confirma=True,
    adaptador=adaptador, fuente_barras=fuente,
    cuenta_hedge_eval=CH_EVAL, cuenta_prop_eval=CP_EVAL,
    cuenta_hedge_funded=CH_FUN, cuenta_prop_funded=CP_FUN, instrumento_prop=MES,
    ruta_ordenes=ruta_ordenes, ruta_nivel=ruta_nivel, dia_negociacion=2,
    dormir=lambda s: None)

print("  r_funded_concurrente:", r_funded_concurrente)
print("  r_eval_concurrente:", r_eval_concurrente)

print("\n=== comparación bit a bit contra el oráculo secuencial ===")
CAMPOS_FUNDED = ('caja_delta', 'hubo_muerte', 'toco_ciclo', 'cerro_linaje', 'eventos', 'bloqueo')
for campo in CAMPOS_FUNDED:
    a, b = r_funded_oraculo[campo], r_funded_concurrente[campo]
    igual = abs(a - b) < 1e-6 if isinstance(a, float) else a == b
    ok(f"funded.{campo} coincide", igual, (a, b))
for k in ('bal', 'pico', 'H', 'dias', 'k', 'm', 'fase', 'activa', 's0'):
    a, b = r_funded_oraculo['funded_estado'][k], r_funded_concurrente['funded_estado'][k]
    igual = abs(a - b) < 1e-6 if isinstance(a, float) else a == b
    ok(f"funded_estado.{k} coincide", igual, (a, b))

CAMPOS_EVAL = ('caja_delta', 'hubo_muerte', 'eventos', 'bloqueo', 'sunk_a_recamara')
for campo in CAMPOS_EVAL:
    a, b = r_eval_oraculo[campo], r_eval_concurrente[campo]
    igual = (abs(a - b) < 1e-6 if isinstance(a, (int, float)) and not isinstance(a, bool)
              else a == b) if a is not None or b is not None else True
    if a is None or b is None:
        igual = (a is None) == (b is None) or (a is not None and b is not None and abs(a - b) < 1e-6)
    ok(f"eval.{campo} coincide", igual, (a, b))
for k in ('bal', 'pico', 'H', 'k', 'm', 'activa', 's0', 'aprobada_confirmada'):
    a, b = r_eval_oraculo['eval_estado'][k], r_eval_concurrente['eval_estado'][k]
    igual = abs(a - b) < 1e-6 if isinstance(a, float) else a == b
    ok(f"eval_estado.{k} coincide", igual, (a, b))

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
