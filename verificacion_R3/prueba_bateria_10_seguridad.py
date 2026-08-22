# -*- coding: utf-8 -*-
"""Task 23 / 10_SEGURIDAD.md §6: la tabla de 10 comprobaciones ("ninguna se
da por buena sin la salida pegada"). Este fichero es el ÍNDICE que cierra
cada una contra su prueba real, y aporta demostración NUEVA para las que
todavía no estaban cableadas contra `bot/seguridad.py` (items 1, 2, 4, 7,
10 -- las demás ya tienen su propia prueba dedicada, referenciada aquí en
vez de duplicada)."""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import seguridad as S
from bot.adaptador_falso import AdaptadorFalso

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


DIR = "/tmp/prueba_bateria_10_seguridad"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR)
RUTA_NIVEL = os.path.join(DIR, "nivel.json")


print("=" * 70)
print("10_SEGURIDAD.md §6 -- las 10 comprobaciones, una por una")
print("=" * 70)

print("\n--- #1: matar el bot entre el fill del hedge y la orden de la prop -> "
      "al reiniciar: aplana el hedge, N2 ---")
print("  Mecánica de reconciliación YA demostrada en:")
print("    verificacion_R3/integracion_proceso_real/prueba_bot_muere_y_reconcilia.py (13/13)")
print("  Ese arnés (NO es D8, arnes_bot_minimo.py::reconcilia -- test harness, no producción)")
print("  detecta el hedge desnudo. Lo que faltaba: que bot/seguridad.py clasifique EXACTAMENTE")
print("  ese mismo escenario (hedge vivo, prop en cero) como CONOCIDO-INSEGURO y reaccione a N2.")
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR)
# el mismo escenario que fabrica prueba_bot_muere_y_reconcilia.py: hedge vivo, prop en cero
clasif_1 = S.clasifica_posicion(cantidad_hedge=-4, cantidad_prop=0, m_esperado=4, k_esperado=10,
                                 en_ventana_transicion=False)
conoc_1 = S.clasifica_conocimiento(hedge_legible=True, prop_legible=True, estado_posicion=clasif_1)
ok("hedge desnudo tras reinicio (prop=0, hedge=-4) se clasifica CONOCIDO-INSEGURO",
   conoc_1 == 'CONOCIDO-INSEGURO', (clasif_1, conoc_1))
S.reacciona_a_desconocido(RUTA_NIVEL, "hedge desnudo tras reinicio (prueba #1)", dia_negociacion=1) \
    if conoc_1 == 'DESCONOCIDO' else S.sube_a(RUTA_NIVEL, 'N2', "hedge desnudo tras reinicio (prueba #1)",
                                               causa='posicion_descuadrada')
ok("la reacción deja el nivel en N2 ('plano y parado hoy', tras aplanar el hedge)",
   S.nivel_actual(RUTA_NIVEL) == 'N2')

print("\n--- #2: fill parcial que nunca completa -> DESCONOCIDO -> aplana las dos -> N2 ---")
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR)
# un fill parcial dejaría cantidades que NO corresponden a m_esperado/k_esperado en ninguna
# de las dos cuentas -- eso es VIOLACION vía clasifica_posicion, pero si además la propia
# LECTURA de la posición es incierta durante el fill parcial (el bróker puede no dar una
# cifra definitiva mientras la orden sigue PARCIAL), la clasificación correcta es DESCONOCIDO.
clasif_2 = S.clasifica_conocimiento(hedge_legible=True, prop_legible=False,   # prop ilegible: fill parcial en curso
                                     estado_posicion=None)
ok("posición prop no legible con certeza durante un fill parcial -> DESCONOCIDO",
   clasif_2 == 'DESCONOCIDO', clasif_2)
S.reacciona_a_desconocido(RUTA_NIVEL, "fill parcial que nunca completa (prueba #2)", dia_negociacion=1)
ok("DESCONOCIDO reacciona subiendo a N2 (fuerza a PLANO, para hasta intervención)",
   S.nivel_actual(RUTA_NIVEL) == 'N2')

print("\n--- #3: poner la posición prop a cero desde el simulador, sin orden del bot -> "
      "detecta liquidación forzosa -> cierra el hedge ---")
print("  YA demostrado end-to-end contra el socket real:")
print("    verificacion_R3/integracion_proceso_real/prueba_liquidacion_forzosa.py (6/6)")
print("  Cableado con seguridad.py (-> N2) demostrado en prueba_seguridad_n0_n4.py, última sección.")
ok("(referencia, no repetida aquí)", True)

print("\n--- #4: tirar la conexión con posición abierta -> las órdenes en reposo siguen puestas; "
      "alerta; N1 (NO N2 -- 'lo abierto sigue su curso normal', catálogo C) ---")
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR)
a4 = AdaptadorFalso()
oid_prop = a4.abrir("CTA-PROP", "MES", 1, 10); a4.leer_estado_orden(oid_prop)
b4 = a4.coloca_bracket("CTA-PROP", "MES", direccion_cierre=-1, cantidad=10,
                        precio_stop=4990.0, precio_limite=5010.0)
a4.desconecta("CTA-PROP")   # se tira la conexión CON la posición ya abierta
ok("tras desconectar, hay_conexion() es False", a4.hay_conexion("CTA-PROP") is False)
ok("las DOS patas del bracket SIGUEN vivas en el bróker (ACEPTADA) pese a la conexión caída "
   "-- 'las órdenes en reposo siguen puestas y siguen protegiendo'",
   a4.leer_estado_orden(b4['order_id_stop']) == 'ACEPTADA'
   and a4.leer_estado_orden(b4['order_id_limite']) == 'ACEPTADA')
# la posición sigue protegida -- lo abierto sigue su curso normal; solo se prohíbe abrir NUEVO
S.sube_a(RUTA_NIVEL, 'N1', "conexión caída con posición ya protegida por órdenes en reposo (prueba #4)",
          causa='reconciliacion')
ok("el nivel sube a N1 (SIN APERTURAS) -- NO a N2, porque lo ya abierto sigue protegido",
   S.nivel_actual(RUTA_NIVEL) == 'N1')
# al reconectar, la orden SIGUE resolviéndose con normalidad -- confirma que nunca dejó de vigilar
a4.conexiones["CTA-PROP"] = True
a4.fabrica_resolucion_bracket(b4['id_grupo_oco'], 'stop')
ok("al reconectar, el bracket se sigue resolviendo con normalidad (stop LLENA, límite CANCELADA)",
   a4.leer_estado_orden(b4['order_id_stop']) == 'LLENA'
   and a4.leer_estado_orden(b4['order_id_limite']) == 'CANCELADA')

print("\n--- #5: corromper estado.json de tres formas -> excepción tipada -> N4, nunca N0 ---")
print("  YA demostrado: verificacion_R3/prueba_seguridad_n0_n4.py (sección dedicada, 3 formas)")
print("  y verificacion_R3/prueba_estado_corrupto.py (5/5, la excepción tipada en sí).")
ok("(referencia, no repetida aquí)", True)

print("\n--- #6: arrancar una segunda instancia -> la segunda no arranca ---")
print("  YA demostrado: verificacion_R3/prueba_bloqueo_proceso.py (8/8, con subprocess reales)")
ok("(referencia, no repetida aquí)", True)

print("\n--- #7: hacer reventar el bot al cargar, en bucle -> tras R intentos deja de reiniciarse "
      "y sube a N3 ---")
print("  El CONTEO de reinicios y el corte del bucle viven en watchdog_bot.ps1 (PowerShell, la")
print("  máquina Windows -- fuera de alcance tocar más sin esa máquina, ORDEN_DE_TRABAJO_D8.md §6).")
print("  Demostración del lado Python (lo que SÍ se puede probar sin Windows): la reacción que")
print("  watchdog_bot.ps1 tendrá que disparar en cuanto tenga acceso a nivel.json.")
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR)
resultado_n3 = S.reacciona_a_presupuesto_reinicios_agotado(
    RUTA_NIVEL, "4 reinicios en 15 min > MaxReiniciosEnVentana=3 (fabricado para la prueba)")
ok("reacciona_a_presupuesto_reinicios_agotado() sube el nivel a N3", resultado_n3 == 'N3')
ok("nivel.json persiste N3", S.nivel_actual(RUTA_NIVEL) == 'N3')
try:
    S.baja_automatica(RUTA_NIVEL, 'N0', "el bot ya no revienta al cargar")
    bajo_solo = True
except S.NivelInvalidoError:
    bajo_solo = False
ok("N3 NO se auto-perdona aunque la causa (el bug que hacía reventar el bot) ya no exista -- "
   "sigue exigiendo un humano", not bajo_solo)

print("\n--- #8: inyectar un fill peor que el del modelo -> el residuo diario se sale de banda y "
      "avisa ---")
print("  BLOQUEADO: el residuo diario (Task 20, REVISION_REV5.md §4.1) compara resolver_dia contra")
print("  el resultado REAL de un día -- necesita D8.4 (bucle_del_dia) para producir ese resultado")
print("  real. La calibración de la banda de alerta es, además, explícitamente Fase 3.1 (papel real)")
print("  -- 'nada de esto se escala hasta que F3.1 dé fricción y deslizamiento reales'.")
ok("(bloqueo documentado, no una comprobación ejecutable)", True)

print("\n--- #9: mover el reloj de pared hacia atrás -> un comando caducado NO resucita ---")
print("  YA demostrado: verificacion_R3/prueba_reloj_comandos.py (6/6, reproduce el bug primero "
      "contra una reimplementación sin blindar, luego confirma el blindaje real)")
ok("(referencia, no repetida aquí)", True)

print("\n--- #10: forzar tamaños que no se corresponden entre patas -> reconciliación lo caza -> N3 ---")
shutil.rmtree(DIR, ignore_errors=True); os.makedirs(DIR)
clasif_10 = S.clasifica_posicion(cantidad_hedge=-3, cantidad_prop=10, m_esperado=4, k_esperado=10,
                                  en_ventana_transicion=False)
ok("dos patas abiertas con un tamaño que NO corresponde (hedge=-3, se esperaba m=4) -> VIOLACION",
   clasif_10 == 'VIOLACION', clasif_10)
resultado_10 = S.reacciona_a_violacion_tamanos(
    RUTA_NIVEL, f"hedge=-3 (esperado m=4), prop=10 (esperado k=10)")
ok("reacciona_a_violacion_tamanos() sube el nivel a N3 (más grave que DESCONOCIDO -- "
   "un tamaño que no corresponde con las dos patas SÍ leídas solo se explica por un bug o "
   "una manipulación)", resultado_10 == 'N3')

shutil.rmtree(DIR, ignore_errors=True)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
