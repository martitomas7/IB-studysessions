# -*- coding: utf-8 -*-
"""D9 §5.1 (residuo diario), REVISION_REV5.md §4.2 -- el contrafactual de
dirección: "correr la dirección OPUESTA por resolver_dia/refleja_camino
también, para un muestreo pareado del mismo día, y probar si la moneda
50/50 (R-6.1) es neutral sobre datos reales." Medición pura, fuera de
`bot/` -- no hace falta autorización R6 (AUTORIZACION_3_6_CERRADA.md §6:
"Sí, en verificacion_R3/. Es medición, no producción. Bien clasificado.").

Diseño: para CADA uno de los 504 días del pack (`tests/replay_v10.json`),
se calcula `sesion.resolver_dia()` DOS VECES sobre el MISMO camino crudo
real -- una vez reflejado como LARGO, otra como CORTO
(`calendario.refleja_camino`, la MISMA función que usa el replay, sin
reimplementar nada) -- con el MISMO `plan_resultado`/`m`/`fric`/
`deslizamiento` FIJO en las dos (una cuenta eval recién abierta, día 1,
`bal=pico=H=0`) para las dos, en vez del que de verdad tuvo cada cuenta
ese día del replay real. Esto es DELIBERADO: aislar la dirección como la
ÚNICA variable -- si se usara el `plan` real de cada cuenta (que ya
arrastra el historial de días anteriores, que a su vez depende de qué
dirección salió), el efecto de "la dirección de HOY" y el de "el estado
acumulado de ayer" quedarían mezclados, y no se podría aislar cuál de
los dos produce una diferencia si aparece.

Es un muestreo PAREADO por construcción (mismo día, dos direcciones) --
más fuerte que el "~250 días" que pedía la nota original: al recalcular
las DOS direcciones sobre CADA uno de los 504 días (no solo la mitad que
ya salió con una dirección concreta), el tamaño de muestra efectivo es el
pack ENTERO, no una submuestra.

Esto es MEDICIÓN, no una puerta: no aplana nada, no decide nada, no
cambia ningún comportamiento de `bot/`. Si aparece una asimetría real,
se informa tal cual -- ni se descarta ni se "corrige" aquí."""
import json
import math
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import calendario, config, sesion, sizing

RUTA_PACK = os.path.join(ING, "tests", "replay_v10.json")

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


pack = json.load(open(RUTA_PACK))
dias = pack["dias"]
N = len(dias)

cfg = config.obtener()
b0_rth = int(cfg.sesion.cal_rth.b0_rth.valor())
m_eval = cfg.sizing.m_eval.valor()
exp_eval = cfg.sizing.exp_eval_usd.valor()
kcap = cfg.sizing.kcap.valor()
T_eval = cfg.proveedor.objetivo_eval_usd.valor()
spr = cfg.hedge_broker.spr_usd.valor()
slip_micro = cfg.hedge_broker.slip_usd_micro.valor()
b_eval = cfg.sizing.b_eval_usd.valor()
cuota = cfg.proveedor.cuota_sub_usd.valor()

friccion = spr * m_eval
deslizamiento = slip_micro * m_eval
G_fijo = max(cuota, 0.0) + b_eval
# plan_resultado FIJO -- una cuenta eval recién abierta (bal=pico=H=0), la
# MISMA para los 504 días y las dos direcciones -- ver docstring: aísla la
# dirección como única variable.
plan_fijo = sizing.plan(bal=0.0, pico=0.0, G=G_fijo, H=0.0, fric=friccion, m=m_eval,
                         EXP=exp_eval, T=T_eval, dcap=1e18, kcap=kcap)

print(f"=== contrafactual de dirección: {N} días, plan FIJO (k={plan_fijo['k']}), "
      f"largo vs corto sobre el MISMO camino real ===")

filas = []
for d in dias:
    ventana_txt = d["ventana"]
    b0v = b0_rth if ventana_txt == "RTH" else 0
    ph_crudo, pl_crudo, pc_crudo = d["barras"]["ph"], d["barras"]["pl"], d["barras"]["pc"]

    ph_l, pl_l, pc_l = calendario.refleja_camino(ph_crudo, pl_crudo, pc_crudo, 1)
    dia_largo = sesion.resolver_dia(ph=ph_l, pl=pl_l, pc=pc_l, barra_inicio=b0v,
                                     plan_resultado=plan_fijo, m=m_eval, fric=friccion,
                                     deslizamiento=deslizamiento)

    ph_c, pl_c, pc_c = calendario.refleja_camino(ph_crudo, pl_crudo, pc_crudo, -1)
    dia_corto = sesion.resolver_dia(ph=ph_c, pl=pl_c, pc=pc_c, barra_inicio=b0v,
                                     plan_resultado=plan_fijo, m=m_eval, fric=friccion,
                                     deslizamiento=deslizamiento)
    filas.append((dia_largo, dia_corto))

ok(f"los {N} días de las dos direcciones se calcularon sin excepción", len(filas) == N, len(filas))

n_muere_largo = sum(1 for l, c in filas if l['muere'])
n_muere_corto = sum(1 for l, c in filas if c['muere'])
n_objetivo_largo = sum(1 for l, c in filas if l['objetivo'])
n_objetivo_corto = sum(1 for l, c in filas if c['objetivo'])
n_pausa_largo = sum(1 for l, c in filas if l['pausa'])
n_pausa_corto = sum(1 for l, c in filas if c['pausa'])

# discordancia PAREADA (McNemar): día a día, cuántas veces el desenlace
# fue distinto SEGÚN la dirección -- es la comparación correcta para un
# muestreo pareado (no dos muestras independientes).
b_muere = sum(1 for l, c in filas if l['muere'] and not c['muere'])   # largo muere, corto no
c_muere = sum(1 for l, c in filas if c['muere'] and not l['muere'])   # corto muere, largo no
b_obj = sum(1 for l, c in filas if l['objetivo'] and not c['objetivo'])
c_obj = sum(1 for l, c in filas if c['objetivo'] and not l['objetivo'])

diffs_dx = [l['dx_puntos'] - c['dx_puntos'] for l, c in filas]
media_diff_dx = sum(diffs_dx) / N
var_diff_dx = sum((x - media_diff_dx) ** 2 for x in diffs_dx) / (N - 1)
se_diff_dx = math.sqrt(var_diff_dx / N)

print(f"\n  muertes  largo={n_muere_largo}/{N} ({100*n_muere_largo/N:.1f}%)   "
      f"corto={n_muere_corto}/{N} ({100*n_muere_corto/N:.1f}%)   "
      f"discordantes: largo-solo={b_muere}  corto-solo={c_muere}")
print(f"  objetivo largo={n_objetivo_largo}/{N} ({100*n_objetivo_largo/N:.1f}%)   "
      f"corto={n_objetivo_corto}/{N} ({100*n_objetivo_corto/N:.1f}%)   "
      f"discordantes: largo-solo={b_obj}  corto-solo={c_obj}")
print(f"  pausa    largo={n_pausa_largo}/{N} ({100*n_pausa_largo/N:.1f}%)   "
      f"corto={n_pausa_corto}/{N} ({100*n_pausa_corto/N:.1f}%)")
print(f"  dx_puntos (largo-corto), pareado: media={media_diff_dx:.4f}  "
      f"error_estandar={se_diff_dx:.4f}  (media/SE = {media_diff_dx/se_diff_dx if se_diff_dx else float('nan'):.2f})")

# McNemar exacto (aproximación normal, N grande): bajo H0 (la moneda es
# neutral), b y c deberían ser aproximadamente iguales -- estadístico
# estándar (b-c)^2/(b+c), sin ningún umbral de negocio inventado (R2: esto
# es matemática de libro de texto, no una cifra del proyecto).
def _mcnemar(b, c):
    if b + c == 0:
        return 0.0
    return (abs(b - c) - 1) ** 2 / (b + c)   # con corrección de continuidad

chi2_muere = _mcnemar(b_muere, c_muere)
chi2_obj = _mcnemar(b_obj, c_obj)
print(f"\n  McNemar (corrección de continuidad) muerte:   chi2={chi2_muere:.3f}  "
      f"(>3.84 -> discrepancia al 95% de dos colas, referencia de libro de texto, "
      f"NO un umbral del proyecto)")
print(f"  McNemar (corrección de continuidad) objetivo:  chi2={chi2_obj:.3f}")

# NOTA (auto-corrección durante esta misma sesión): la primera versión de
# este fichero comprobaba "diferencia de tasas < 2 puntos porcentuales" a
# secas -- un umbral inventado sin relación con el tamaño de muestra, que
# SÍ saltó en objetivo (21,8% vs 25,0%, 3,2pp) mientras que McNemar (el
# estadístico correcto para un muestreo PAREADO, que sí tiene en cuenta N
# y la estructura de discordancia) no encuentra nada al 95% (chi2=0,953).
# Un umbral fijo en puntos porcentuales, sin más, es precisamente el tipo
# de cifra que R2 prohíbe inventar -- se retira, McNemar es el que manda.
ok("McNemar de muerte NO cruza el umbral de libro de texto de discrepancia al 95% (chi2 < 3.84)",
   chi2_muere < 3.84, chi2_muere)
ok("McNemar de objetivo NO cruza el umbral de libro de texto de discrepancia al 95% (chi2 < 3.84)",
   chi2_obj < 3.84, chi2_obj)
ok("la diferencia media pareada de dx_puntos es pequeña frente a su propio error estándar "
   "(|media/SE| < 2 -- ninguna asimetría direccional dominante en el camino real de HG22)",
   abs(media_diff_dx / se_diff_dx) < 2.0 if se_diff_dx else True, media_diff_dx / se_diff_dx)

print("\n=== R3: el propio McNemar discrimina -- fabricar una asimetría a mano y verla saltar ===")
# se fabrica una discordancia deliberadamente desequilibrada (60 vs 5, en
# vez de las reales, casi siempre parejas) para confirmar que el
# estadístico SÍ reacciona cuando hay una asimetría de verdad.
chi2_fabricado = _mcnemar(60, 5)
ok("con una discordancia fabricada muy desequilibrada (60 vs 5), McNemar SÍ cruza 3.84 -- "
   "confirma que el estadístico detecta una asimetría real cuando la hay, no es un no-op",
   chi2_fabricado > 3.84, chi2_fabricado)

# --- informe ---
ruta_informe = os.path.join(AQUI, "CONTRAFACTUAL_DIRECCION.md")
with open(ruta_informe, "w", encoding="utf-8") as fh:
    fh.write(f"""# Contrafactual de dirección -- REVISION_REV5.md §4.2

Medición, no una puerta (AUTORIZACION_3_6_CERRADA.md §6: "es medición, no producción").
`{N}` días del pack (`tests/replay_v10.json`), cada uno resuelto DOS VECES sobre el MISMO
camino crudo real -- reflejado LARGO y reflejado CORTO (`calendario.refleja_camino`, sin
reimplementar) -- con un `plan_resultado` FIJO (cuenta eval recién abierta, día 1) igual en
las dos direcciones, para aislar la dirección como única variable.

## Resultado

| desenlace | largo | corto | discordantes (largo-solo / corto-solo) | McNemar (chi2, corrección continuidad) |
|---|---|---|---|---|
| muere | {n_muere_largo}/{N} ({100*n_muere_largo/N:.1f}%) | {n_muere_corto}/{N} ({100*n_muere_corto/N:.1f}%) | {b_muere} / {c_muere} | {chi2_muere:.3f} |
| objetivo | {n_objetivo_largo}/{N} ({100*n_objetivo_largo/N:.1f}%) | {n_objetivo_corto}/{N} ({100*n_objetivo_corto/N:.1f}%) | {b_obj} / {c_obj} | {chi2_obj:.3f} |
| pausa | {n_pausa_largo}/{N} ({100*n_pausa_largo/N:.1f}%) | {n_pausa_corto}/{N} ({100*n_pausa_corto/N:.1f}%) | -- | -- |

`dx_puntos` pareado (largo − corto): media = {media_diff_dx:.4f}, error estándar = {se_diff_dx:.4f}
(media/SE = {media_diff_dx/se_diff_dx if se_diff_dx else float('nan'):.2f}).

**Umbral de referencia (McNemar, 1 grado de libertad, 95%): chi2 = 3.84 -- valor de libro de
texto, no una cifra del proyecto.**

## Lectura

{"Ninguno de los dos McNemar (muerte, objetivo) cruza el umbral de 3.84, y la diferencia media pareada de dx_puntos es pequeña frente a su propio error estándar -- la moneda 50/50 de R-6.1 se comporta como neutral sobre el camino real de HG22 con esta cuenta de referencia. No hay evidencia, en esta medición, de que la dirección por sí sola sesgue el desenlace." if chi2_muere < 3.84 and chi2_obj < 3.84 and (se_diff_dx == 0 or abs(media_diff_dx/se_diff_dx) < 2.0) else "AL MENOS UNA de las comprobaciones anteriores SÍ cruza el umbral de referencia -- hay indicios de una asimetría direccional real en el camino de HG22 que esta medición no puede explicar por azar. Esto NO invalida el modelo (la reflexión de calendario.refleja_camino sigue siendo matemáticamente correcta, R-6.1 sigue describiendo el SORTEO, no el desenlace), pero es un hallazgo que el operador debe conocer antes de asumir neutralidad direccional en la interpretación de resultados futuros."}

**Limitación reconocida:** se usó un `plan_resultado` FIJO (cuenta día 1) igual en las dos
direcciones, en vez del `plan` real que cada cuenta tuvo cada día del replay -- deliberado,
para aislar la dirección del efecto acumulado del estado de cuenta (que a su vez depende de
qué dirección salió en días anteriores). Esto mide "¿la dirección importa, dado un punto de
partida idéntico?", no "¿el histórico real de 504 días habría sido distinto con la moneda al
revés?" -- son preguntas relacionadas pero no idénticas.
""")
ok(f"informe escrito: {ruta_informe}", os.path.isfile(ruta_informe))

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
