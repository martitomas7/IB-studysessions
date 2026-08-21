# -*- coding: utf-8 -*-
"""D8 §5.2 (ANALISIS_PUERTA_GRANDE.md §5): bloqueo de funded (R-2.4) y
bloqueo SOSTENIDO -- cobertura 1 en la Puerta Grande (se tocó una sola
vez, el día 269 -- ver `verificacion_R3/CENSO_COBERTURA.md`). El pedido:
"Días adversarios fabricados: bloqueo 1 día, 3 días, y 7+ días seguidos
(el caso absorbente en que el proveedor mata la cuenta con el hedge sin
abrir). Que la escalada N0→N4 suba sola y que NO baje sin humano."

Investigación previa a escribir nada (R1/R3 -- entender antes de fabricar
un escenario):

- `bloqueo` (R-2.4, `bot/sizing.py::plan()`, `k<1`) se decide ANTES de
  mirar mercado, sobre el bal/pico de INICIO de día. `cierra_resolucion_funded`
  (`bot/ciclo_vida.py:551-558`) reacciona desactivando el slot (`activa=False`)
  -- SIN fijar `espera` (a diferencia de la muerte real, R-3.4): el relevo
  puede reintentarlo el día SIGUIENTE sin esperar. Y `activa_funded_si_toca`
  arranca la dormida siguiente con estado COMPLETAMENTE FRESCO (bal=pico=H=0,
  dias=0) -- con eso, `Mm` vuelve a ser holgado y el bloqueo NO se repite
  solo. Verificado abajo con las funciones reales, un día suelto: el
  bloqueo es TRANSITORIO por linaje, no un bucle que se retroalimente él
  solo.
- La ÚNICA forma real de que funded se quede "con el hedge sin abrir"
  durante muchos días seguidos no es que bloquee una y otra vez -- es que,
  tras desactivarse (por bloqueo o por muerte real), la RECÁMARA esté
  VACÍA (`recamara.dormidas == []`): sin una dormida que lo releve,
  `activa_funded_si_toca` no hace nada, y funded se queda esperando,
  indefinidamente, sin abrir ninguna posición -- el caso "absorbente" que
  describe el pedido.
- Grep exhaustivo ANTES de escribir el test (para no fabricar un escenario
  y suponer que algo reacciona cuando no es así): `alertas.bloqueada_escalada_dias`
  y `alertas.proveedor_mata_cuenta_dias` (03_CONFIG.yaml) SOLO los lee
  `bot/contexto_dashboard.py` -- y solo para pintar un contador que depende
  de una clave `dias_esperando` en `estado['pendientes_humano']`. NADA en
  `bot/ciclo_vida.py`, `bot/orquestador.py` ni `bot/seguridad.py` escribe
  jamás esa clave, así que ese contador del dashboard es, hoy, código
  inalcanzable. Y `bot/seguridad.py` (la escalera N0-N4) está, por su
  propio docstring, "SOLO" para clasificar posiciones YA leídas del
  bróker (PLANO/CUBIERTO/violaciones de tamaño, estado corrupto,
  liquidación forzosa, presupuesto de reinicios) -- nunca para estados de
  negocio normales como "esperando una dormida". No hay, HOY, ningún
  camino de código que suba el nivel N0-N4 ni que cree un
  `pendientes_humano` por un bloqueo sostenido de funded, por muchos días
  que pasen.

Este test NO inventa esa lógica (sería una decisión de negocio -- qué
nivel, a los cuántos días, con qué criterio -- que le corresponde al
operador, R2/R6, no a esta sesión). Lo que hace es EXACTAMENTE lo que
pide R3: fabricar el escenario adversario y comprobar, de verdad, qué
pasa hoy -- fijando el resultado (incluida la ausencia de escalada) como
un pin de regresión NOMBRADO y EXPLÍCITO, igual que
`prueba_censo_cobertura.py` hace con los caminos de cobertura 0: para que
el día que alguien cablee la escalada, este test falle a propósito y haya
que revisarlo, en vez de que el cambio pase desapercibido."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import ciclo_vida as CV, config, estado as E, orquestador as O, seguridad as SEG, sizing

_, checksum = config.cargar()
cfg = config.obtener()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


NB = 86
P0 = 5000.0


def _camino_plano():
    return [P0] * NB, [P0] * NB, [P0] * NB


# =============================================================================
# 1. Bloqueo (R-2.4) en aislamiento -- construido MATEMÁTICAMENTE, no a
#    fuerza de días de erosión: sizing.plan() es puro (R6), así que basta
#    elegir bal/pico que le den Mm pequeño y confirmar bloqueo=True ANTES
#    de correr nada, para no fabricar un escenario a ciegas.
# =============================================================================
print("=== 1. R-2.4 bloqueo, en aislamiento (matemática confirmada antes de usarla) ===")

m_fun = cfg.sizing.m_fun.valor()
exp_fun = cfg.sizing.exp_fun_usd.valor()
kcap = cfg.sizing.kcap.valor()
spr = cfg.hedge_broker.spr_usd.valor()
b_fun = cfg.sizing.b_fun_usd.valor()
esc = cfg['proveedor']['escalera_retiro']
T_c1, D_c1 = esc['ciclo_1']['umbral_bruto_usd'], esc['ciclo_1']['tope_dia_usd']
friccion = spr * m_fun

# pico >= MLL+LOCK congela el suelo vivo en LOCK (R-2.1); bal justo por
# encima de ese suelo deja Mm minúsculo -> k<1 -> bloqueo, SIN necesitar
# ninguna muerte real.
MLL = cfg.proveedor.mll_usd.valor()
LOCK = cfg.proveedor.lock_usd.valor()
PICO_BLOQUEO = MLL + LOCK + 100.0
BAL_BLOQUEO = LOCK + 1.0
S0_BLOQUEO = 500.0

plan_directo = sizing.plan(bal=BAL_BLOQUEO, pico=PICO_BLOQUEO, G=max(S0_BLOQUEO, 0.0) + b_fun,
                            H=0.0, fric=friccion, m=m_fun, EXP=exp_fun, T=T_c1, dcap=D_c1, kcap=kcap)
ok(f"sizing.plan() puro (R6, sin tocar) da bloqueo=True para estos bal/pico "
   f"(Mm={plan_directo['Mm']})", plan_directo['bloqueo'] is True, plan_directo)

fu_bloqueada = dict(activa=True, fase=1, bal=BAL_BLOQUEO, pico=PICO_BLOQUEO, H=0.0,
                     s0=S0_BLOQUEO, dias=5, espera=0, k=0.0, m=0.0)
ph0, pl0, pc0 = _camino_plano()   # día PLANO -- ni toca suelo ni objetivo, para
                                   # aislar el bloqueo de R-3.4/R-2.2 (que se
                                   # deciden ANTES, en el if/elif de
                                   # cierra_resolucion_funded)
r1 = CV.procesa_dia_funded(fu_bloqueada, direccion=1, ph=ph0, pl=pl0, pc=pc0, b0v=0,
                            es_dia_nuevo=False)
ok("día plano + bloqueo: bloqueo=True", r1['bloqueo'] is True, r1['bloqueo'])
ok("bloqueo NUNCA es la misma cosa que una muerte real (R-3.4): hubo_muerte=False, "
   "eventos.muertes_funded=0", r1['hubo_muerte'] is False and r1['eventos']['muertes_funded'] == 0,
   (r1['hubo_muerte'], r1['eventos']))
ok("el bloqueo desactiva el slot (activa=False)", r1['funded_estado']['activa'] is False,
   r1['funded_estado']['activa'])
ok("el bloqueo NO fija espera (a diferencia de la muerte real) -- el relevo puede "
   "reintentar MAÑANA MISMO, sin esperar", r1['funded_estado']['espera'] == 0,
   r1['funded_estado']['espera'])

# =============================================================================
# 2. El relevo tras un bloqueo arranca FRESCO -- por eso el bloqueo NO se
#    retroalimenta él solo día tras día (si hay una dormida disponible).
# =============================================================================
print("\n=== 2. tras el bloqueo, el relevo arranca fresco -- el bloqueo NO se repite solo ===")

dormida_disponible = [dict(s0=S0_BLOQUEO, desde_dia=1)]
fresco, dormidas_tras, activada = CV.activa_funded_si_toca(r1['funded_estado'], dormida_disponible)
ok("con una dormida disponible, el relevo activa AL DÍA SIGUIENTE (relevo_dias=0, "
   "sin esperar)", activada is True, activada)
ok("el relevo arranca con estado COMPLETAMENTE FRESCO (bal=pico=H=0, dias=0) -- el "
   "linaje bloqueado se descarta, no se hereda su erosión",
   fresco['bal'] == 0.0 and fresco['pico'] == 0.0 and fresco['H'] == 0.0 and fresco['dias'] == 0,
   fresco)

ph1, pl1, pc1 = _camino_plano()
r2 = CV.procesa_dia_funded(fresco, direccion=1, ph=ph1, pl=pl1, pc=pc1, b0v=0, es_dia_nuevo=True)
ok("el relevo fresco, el MISMO día plano que antes bloqueaba, NO vuelve a bloquear "
   "(Mm fresco es holgado) -- el bloqueo es TRANSITORIO por linaje, no un bucle que "
   "se retroalimente solo mientras haya dormidas",
   r2['bloqueo'] is False and r2['funded_estado']['activa'] is True,
   (r2['bloqueo'], r2['funded_estado']['activa']))

# =============================================================================
# 3. El caso REAL "absorbente" del pedido: recámara VACÍA -- funded se
#    queda esperando, sin ninguna dormida que lo releve, sin abrir NUNCA
#    ninguna posición ("el hedge sin abrir") -- 1, 3, 7 y 10 días seguidos,
#    por el bucle real (orquestador.procesa_dia(), camino replay -- la
#    misma función que usa el bot en producción, D8.4).
# =============================================================================
print("\n=== 3. caso absorbente: recámara vacía, funded espera N días seguidos "
      "sin abrir nada ===")

DIR = "/tmp/prueba_bloqueo_funded_sostenido"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)
ruta_nivel = os.path.join(DIR, "nivel.json")

st = E.nuevo('v10', checksum)
ph_dia, pl_dia, pc_dia = _camino_plano()

N_DIAS = 10
DIAS_A_COMPROBAR = (1, 3, 7, 10)
trayectoria = []
for dia in range(1, N_DIAS + 1):
    st, fin_de_dia, diario = O.procesa_dia(st, direccion=1, ventana_txt='22h',
                                            ph=ph_dia, pl=pl_dia, pc=pc_dia, b0v=0,
                                            n_resets_hoy=0)
    fallos = E.validar(st, checksum)
    trayectoria.append(dict(
        dia=dia, funded_activa=st['funded']['activa'], recamara_n=st['recamara']['n'],
        pendientes_humano=list(st['pendientes_humano']), fallos=fallos,
        nivel=SEG.nivel_actual(ruta_nivel)))

for snap in trayectoria:
    if snap['dia'] in DIAS_A_COMPROBAR:
        ok(f"día {snap['dia']}: 0 invariantes rotos (estado.validar limpio, sin "
           f"crash)", len(snap['fallos']) == 0, snap['fallos'])
        ok(f"día {snap['dia']}: recámara sigue vacía (nunca llegó una dormida a "
           f"relevar a funded)", snap['recamara_n'] == 0, snap['recamara_n'])
        ok(f"día {snap['dia']}: funded sigue INACTIVA -- {snap['dia']} días seguidos "
           f"con el hedge SIN ABRIR (el caso absorbente del pedido)",
           snap['funded_activa'] is False, snap['funded_activa'])
        # --- el hallazgo, fijado como pin de regresión nombrado --------------
        ok(f"día {snap['dia']}: nivel.json sigue en N0 -- HOY no existe ningún "
           f"camino de código que escale N0->N4 por un bloqueo/espera sostenido de "
           f"funded (bot/seguridad.py está scopeado a posiciones/reconciliación, "
           f"nunca a estados de negocio -- ver docstring del módulo). CONFIRMADO, "
           f"no es un bug de cálculo: es un hueco de wiring, pendiente de decisión "
           f"del operador (R2/R6) sobre CUÁNDO escalar y a qué nivel.",
           snap['nivel'] == 'N0', snap['nivel'])
        ok(f"día {snap['dia']}: pendientes_humano sigue VACÍO -- el contador que "
           f"pinta bot/contexto_dashboard.py ('reloj del proveedor', "
           f"'reloj del bot' vía alertas.bloqueada_escalada_dias/"
           f"proveedor_mata_cuenta_dias) depende de una clave dias_esperando que "
           f"HOY nadie escribe -- código del dashboard hoy inalcanzable. "
           f"CONFIRMADO, mismo hueco de wiring, misma decisión pendiente.",
           snap['pendientes_humano'] == [], snap['pendientes_humano'])

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
