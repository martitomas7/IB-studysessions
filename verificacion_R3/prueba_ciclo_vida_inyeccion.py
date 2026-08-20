# -*- coding: utf-8 -*-
"""R3 (D8.4, ORDEN_DE_TRABAJO_D8.md §0): `ciclo_vida.procesa_dia_eval`/
`procesa_dia_funded` ganan un parámetro `resuelve_dia=sesion.resolver_dia`
-- inyección ADITIVA PURA. Dos cosas que probar: (1) sin pasar el kwarg,
el comportamiento es EXACTAMENTE el de antes (bit a bit); (2) pasando un
`resuelve_dia` distinto, se usa de verdad -- ninguna rama sigue llamando a
`sesion.resolver_dia` por su cuenta."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import calendario, ciclo_vida as CV, config, sesion

_, _ = config.cargar()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


# camino sintético simple, determinista -- no hace falta el pack real para esto
ph_crudo = [5000.0] * 90
pl_crudo = [5000.0] * 90
pc_crudo = [5000.0] * 90
pl_crudo[5] = 4970.0   # toca suelo en la barra 5 -> genera muerte/pausa real, no un día vacío
ph, pl, pc = calendario.refleja_camino(ph_crudo, pl_crudo, pc_crudo, direccion=1)

ev0 = dict(activa=True, bal=0.0, pico=0.0, H=0.0, s0=100.0, k=0.0, m=0.0,
           aprobada_provisional=False, aprobada_confirmada=False)
pool0 = dict(frescas=2, rotas=0, subs=[])
estado_min = dict(desviaciones_activas=[])

print("=== 1. SIN pasar resuelve_dia: comportamiento bit a bit idéntico al de antes ===")
r_a = CV.procesa_dia_eval(dict(ev0), dict(pool0), [], direccion=1, ph=ph, pl=pl, pc=pc, b0v=0,
                           qok=True, modo_auto_confirma=True, estado=estado_min, dia_actual=1)
r_b = CV.procesa_dia_eval(dict(ev0), dict(pool0), [], direccion=1, ph=ph, pl=pl, pc=pc, b0v=0,
                           qok=True, modo_auto_confirma=True, estado=estado_min, dia_actual=1)
ok("dos llamadas idénticas sin resuelve_dia dan resultados idénticos (determinismo)", r_a == r_b, r_a)
ok("el resultado tiene la forma esperada (bal/H se movieron de verdad -- sesion.resolver_dia "
   "por defecto SÍ se ejecutó, no fue un no-op)",
   r_a['eval_estado']['bal'] != 0.0 and r_a['eval_estado']['H'] != 0.0, r_a)

print("\n=== 2. CON un resuelve_dia inyectado: se usa de verdad, en las dos posibles llamadas "
      "(intento 0 y empalme) ===")
llamadas = []
def resuelve_dia_espia(ph, pl, pc, barra_inicio, plan_resultado, m, fric, deslizamiento=0.0):
    llamadas.append(barra_inicio)
    return sesion.resolver_dia(ph, pl, pc, barra_inicio, plan_resultado, m, fric, deslizamiento)

r_c = CV.procesa_dia_eval(dict(ev0), dict(pool0), [], direccion=1, ph=ph, pl=pl, pc=pc, b0v=0,
                           qok=True, modo_auto_confirma=True, estado=estado_min, dia_actual=1,
                           resuelve_dia=resuelve_dia_espia)
ok("el resuelve_dia inyectado SÍ se llamó (al menos una vez, intento 0)", len(llamadas) >= 1, llamadas)
ok("el resultado con el espía (que delega en el resolver real) es idéntico al de la llamada normal",
   r_c == r_a, (r_c, r_a))

print("\n=== 3. procesa_dia_funded(): misma inyección, mismo default ===")
fu0 = dict(activa=True, fase=1, bal=0.0, pico=0.0, H=0.0, s0=100.0, dias=0, espera=0, k=0.0, m=0.0)
r_f1 = CV.procesa_dia_funded(dict(fu0), direccion=1, ph=ph, pl=pl, pc=pc, b0v=0, es_dia_nuevo=False)
llamadas_f = []
def resuelve_dia_espia_f(ph, pl, pc, barra_inicio, plan_resultado, m, fric, deslizamiento=0.0):
    llamadas_f.append(barra_inicio)
    return sesion.resolver_dia(ph, pl, pc, barra_inicio, plan_resultado, m, fric, deslizamiento)
r_f2 = CV.procesa_dia_funded(dict(fu0), direccion=1, ph=ph, pl=pl, pc=pc, b0v=0, es_dia_nuevo=False,
                              resuelve_dia=resuelve_dia_espia_f)
ok("procesa_dia_funded sin kwarg y con espía (delegando en el real) dan el mismo resultado",
   r_f1 == r_f2, (r_f1, r_f2))
ok("el espía de funded se llamó de verdad", len(llamadas_f) == 1, llamadas_f)

print("\n=== 4. ligado TARDÍO del default (bug real cazado en R3 vía romper_mi_orquestador.py: "
      "un default =sesion.resolver_dia se ligaría PRONTO, al importar el módulo, y quedaría "
      "ciego a un monkeypatch posterior de sesion.resolver_dia) ===")
_original = sesion.resolver_dia
llamadas_parcheado = []
def resolver_dia_falso(ph, pl, pc, barra_inicio, plan_resultado, m, fric, deslizamiento=0.0,
                        redondea=False):
    llamadas_parcheado.append(True)
    return dict(dx_puntos=999.0, hedge_dolares=0.0, comision=0.0, muere=False,
                pausa=False, objetivo=False, barra_evento=0)
try:
    sesion.resolver_dia = resolver_dia_falso   # monkeypatch DESPUÉS de que ciclo_vida.py ya se importó
    r_parcheado = CV.procesa_dia_eval(dict(ev0), dict(pool0), [], direccion=1, ph=ph, pl=pl, pc=pc,
                                       b0v=0, qok=True, modo_auto_confirma=True,
                                       estado=estado_min, dia_actual=1)
finally:
    sesion.resolver_dia = _original
ok("SIN pasar resuelve_dia explícito, el monkeypatch de sesion.resolver_dia SÍ se refleja "
   "(dx_puntos=999.0 del falso, no el resultado real) -- ligado tardío confirmado",
   llamadas_parcheado == [True] and r_parcheado['eval_estado']['bal'] != r_a['eval_estado']['bal'],
   r_parcheado)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
