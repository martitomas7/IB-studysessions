# -*- coding: utf-8 -*-
"""demuestra_defectos_operador_20260820.py · R3 (04_GUARDARRAILES): "nada se
acepta como correcto sin verse fallar antes".

Los tres defectos que el operador encontró en `REVISION_ENTREGA_20260820.md`
YA están cubiertos por `prueba_protocolo_dos_patas.py` §§8-10 (40/40 verde) --
ese fichero demuestra que el código ACTUAL (ya corregido) se comporta bien.
Lo que este fichero añade es la otra mitad de R3: reconstruye, literalmente,
el comportamiento de ANTES de la revisión 4 (tal como lo describe el propio
`07_ADAPTADOR_NT8.md` §5.3 revisión 4 y `bot/protocolo_dos_patas.py` en sus
docstrings de "REGLA GENERAL 1/2/3"), lo corre de verdad contra el mismo
escenario, y pega la salida real de que SÍ falla -- para que quede en el
mismo sitio, con la misma disciplina, que `romper_mi_orquestador.py` (D2-D7)
y `verificacion_R3/prueba_dashboard.py` (D-C): nunca "confía en que estaba
roto", lo vuelve a romper y lo ve.

Mismo método que `romper_mi_orquestador.py::_fabrica`: para el Defecto 2 (el
guardián de conexión que falta) se parchea el CÓDIGO FUENTE real de
`bot/protocolo_dos_patas.py` quitando el guardián, vía string-replace + exec
-- no se toca el fichero en disco, solo una copia en memoria de esa corrida.
Para los Defectos 1 y 3 basta con reconstruir la función entera "de antes"
como una función local, porque el cambio es más profundo que un bloque
aislado (el propio conjunto de estados que se sondea).

NO forma parte de la puerta D-C (no lo corre `prueba_protocolo_dos_patas.py`
ni ningún runner de CI) -- es la demostración R3 en sí, pensada para leerse,
no para automatizarse."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot.adaptador_falso import AdaptadorFalso
from bot import protocolo_dos_patas as P

MES = "MES (Micro E-mini S&P 500)"
PROP = "instrumento prop de ejemplo"


class RelojFalso:
    def __init__(self):
        self.t = 0.0
    def ahora(self):
        return self.t
    def avanza(self, dt):
        self.t += dt


def nuevo(**kwargs):
    rf = RelojFalso()
    def dormir(s): rf.avanza(s)
    ad = AdaptadorFalso(reloj=rf.ahora, **kwargs)
    return rf, dormir, ad


def linea():
    print("-" * 78)


# =====================================================================
# DEFECTO 1 · rechazo/cancelación instantáneos tratados como "sigue viva"
# =====================================================================
print("=" * 78)
print("DEFECTO 1 · rechazo limpio del hedge ANTES de N_hedge (30 s)")
print("=" * 78)


def _viejo_fase_hedge(adaptador, cuenta_hedge, direccion, m, N_hedge, reloj, dormir):
    """Reconstrucción LITERAL de la fase hedge de `abre_las_dos_patas` tal
    como estaba ANTES de la revisión 4 (07_ADAPTADOR_NT8.md §5.3, revisión
    2/3): la única diferencia real es el conjunto de estados que se sondea
    en el PRIMER `_poll_hasta` -- `{'LLENA'}`, no `P.ESTADOS_TERMINALES`."""
    oid_hedge = adaptador.abrir(cuenta_hedge, MES, -direccion, m)
    t0 = reloj()
    estado, agoto = P._poll_hasta(adaptador, oid_hedge, {'LLENA'}, N_hedge, reloj, dormir)
    tiempo_consumido = reloj() - t0
    if agoto:
        adaptador.cancelar(oid_hedge)
        estado_final, _ = P._poll_hasta(adaptador, oid_hedge, P.ESTADOS_TERMINALES, None, reloj, dormir)
        return dict(abierto=False, motivo=f'N_hedge_expirado_{estado_final.lower()}'), tiempo_consumido
    return dict(abierto=True), tiempo_consumido


print("\n-- ANTES (reconstrucción literal de la revisión 3) --")
rf, dormir, ad = nuevo()
ad.programa_abrir('CUENTA_HEDGE', MES, rechazar=True)   # el bróker rechaza de inmediato
resultado_viejo, tiempo_viejo = _viejo_fase_hedge(ad, 'CUENTA_HEDGE', direccion=1, m=4,
                                                   N_hedge=30.0, reloj=rf.ahora, dormir=dormir)
print(f"  resultado: {resultado_viejo}")
print(f"  tiempo lógico consumido: {tiempo_viejo:.1f} s  (N_hedge = 30.0 s)")
falla_como_se_esperaba = (tiempo_viejo >= 30.0)
print(f"  FALLA COMO SE ESPERABA (consume N_hedge entero pese al rechazo instantáneo): "
      f"{'SI' if falla_como_se_esperaba else 'NO -- la reconstrucción no reprodujo el defecto'}")
assert falla_como_se_esperaba, "la reconstrucción de 'antes' no reprodujo el Defecto 1 -- revisar"

print("\n-- DESPUÉS (bot/protocolo_dos_patas.py real, revisión 4) --")
rf2, dormir2, ad2 = nuevo()
ad2.programa_abrir('CUENTA_HEDGE', MES, rechazar=True)
eventos2 = []
t0 = rf2.ahora()
resultado_nuevo = P.abre_las_dos_patas(ad2, 'CUENTA_HEDGE', 'CUENTA_PROP', PROP,
                                        direccion=1, m=4, k=10, eventos=eventos2,
                                        reloj=rf2.ahora, dormir=dormir2)
tiempo_nuevo = rf2.ahora() - t0
print(f"  resultado: {resultado_nuevo}")
print(f"  tiempo lógico consumido: {tiempo_nuevo:.1f} s")
print(f"  eventos: {eventos2}")
corregido = (tiempo_nuevo == 0.0 and resultado_nuevo['abierto'] is False
             and not any('alerta' in e for e in eventos2))
print(f"  CORREGIDO (cero tiempo, sin alerta máxima -- información limpia): "
      f"{'SI' if corregido else 'NO'}")
assert corregido, "el codigo real no corrigio el Defecto 1"


# =====================================================================
# DEFECTO 2 · hay_conexion() nunca se llamaba antes de abrir
# =====================================================================
print()
print("=" * 78)
print("DEFECTO 2 · hay_conexion() ausente del guardián de apertura")
print("=" * 78)

_ANCLA_GUARDIAN = '''    # ---- GUARDIÁN DE CONEXIÓN (DEFECTO 2) -- antes de la PRIMERA orden -----
    hedge_ok = adaptador.hay_conexion(cuenta_hedge)
    prop_ok = adaptador.hay_conexion(cuenta_prop)
    if not (hedge_ok and prop_ok):
        eventos.append(dict(tipo='conexion_caida', hedge_conectado=hedge_ok,
                             prop_conectado=prop_ok, alerta='MAXIMA'))
        return dict(abierto=False, order_id_hedge=None, order_id_prop=None,
                    motivo='conexion_caida_no_se_abre_nada')

    # ---- FASE HEDGE --------------------------------------------------'''
_PARCHE_SIN_GUARDIAN = '''    # BUG RECONSTRUIDO (demuestra_defectos_operador_20260820.py, Defecto 2):
    # el guardián de conexión de la revisión 4 se QUITA a propósito -- así
    # estaba el módulo en la revisión 3, que nunca llamaba hay_conexion().

    # ---- FASE HEDGE --------------------------------------------------'''

src = open(P.__file__).read()
assert _ANCLA_GUARDIAN in src, "ancla del guardián no encontrada -- protocolo_dos_patas.py cambió de forma inesperada"
src_roto = src.replace(_ANCLA_GUARDIAN, _PARCHE_SIN_GUARDIAN, 1)
ns = {'__name__': 'protocolo_dos_patas_SIN_GUARDIAN'}
exec(compile(src_roto, 'protocolo_dos_patas_SIN_GUARDIAN', 'exec'), ns)
abre_sin_guardian = ns['abre_las_dos_patas']

print("\n-- ANTES (mismo módulo, guardián de conexión quitado por string-replace) --")
rf3, dormir3, ad3 = nuevo()
ad3.desconecta('CUENTA_PROP')
eventos3 = []
resultado_viejo2 = abre_sin_guardian(ad3, 'CUENTA_HEDGE', 'CUENTA_PROP', PROP,
                                      direccion=1, m=4, k=10, eventos=eventos3,
                                      reloj=rf3.ahora, dormir=dormir3)
print(f"  resultado: {resultado_viejo2}")
print(f"  posiciones tras la corrida: {dict(ad3.posiciones)}")
abre_pese_a_desconexion = resultado_viejo2['abierto'] is True and len(ad3.posiciones) == 2
print(f"  FALLA COMO SE ESPERABA (abre las dos patas con la prop desconectada): "
      f"{'SI' if abre_pese_a_desconexion else 'NO -- la reconstrucción no reprodujo el defecto'}")
assert abre_pese_a_desconexion, "la reconstruccion de 'antes' no reprodujo el Defecto 2 -- revisar"

print("\n-- DESPUÉS (bot/protocolo_dos_patas.py real, revisión 4) --")
rf4, dormir4, ad4 = nuevo()
ad4.desconecta('CUENTA_PROP')
eventos4 = []
resultado_nuevo2 = P.abre_las_dos_patas(ad4, 'CUENTA_HEDGE', 'CUENTA_PROP', PROP,
                                         direccion=1, m=4, k=10, eventos=eventos4,
                                         reloj=rf4.ahora, dormir=dormir4)
print(f"  resultado: {resultado_nuevo2}")
print(f"  posiciones tras la corrida: {dict(ad4.posiciones)}")
print(f"  eventos: {eventos4}")
corregido2 = (resultado_nuevo2['abierto'] is False and len(ad4.posiciones) == 0
              and any(e.get('alerta') == 'MAXIMA' for e in eventos4))
print(f"  CORREGIDO (no abre nada, alerta máxima registrada): {'SI' if corregido2 else 'NO'}")
assert corregido2, "el codigo real no corrigio el Defecto 2"


# =====================================================================
# DEFECTO 3 · el reintento de cierre miraba el estado de la orden, no la
# posición real -- no converge si el bróker rechaza cantidad cero
# =====================================================================
print()
print("=" * 78)
print("DEFECTO 3 · aplanar() sale por estado de orden, no por posición")
print("=" * 78)


def _viejo_aplana_hasta_confirmar(adaptador, cuenta, instrumento, reloj, dormir, eventos,
                                   etiqueta, max_reintentos, intervalo_reintento_s=0.01):
    """Reconstrucción literal de `_aplana_hasta_confirmar` tal como estaba
    ANTES de la revisión 4: SIN la comprobación de `leer_posicion()` de
    entrada, y con la condición de salida en `estado_final == 'LLENA'` en
    vez de la posición real."""
    intentos = 0
    while True:
        intentos += 1
        oid = adaptador.aplanar(cuenta, instrumento)
        estado_final, _ = P._poll_hasta(adaptador, oid, P.ESTADOS_TERMINALES, None, reloj, dormir)
        if estado_final == 'LLENA':
            return True, intentos
        eventos.append(dict(tipo='ALERTA_MAXIMA', motivo=f'aplanar_no_confirma_{etiqueta}',
                             intento=intentos, estado=estado_final))
        if intentos >= max_reintentos:
            return False, intentos
        dormir(intervalo_reintento_s)


print("\n-- ANTES (reconstrucción literal de la revisión 3, tope bajo de "
      "reintentos=5 solo para que la demostración no tarde) --")
rf5, dormir5, ad5 = nuevo(rechaza_aplanar_cantidad_cero=True)
# la cuenta YA está plana -- ninguna posición abierta, exactamente el caso
# de un reintento de cierre que llega tras un cierre anterior ya confirmado
eventos5 = []
confirmado_viejo, intentos_viejo = _viejo_aplana_hasta_confirmar(
    ad5, 'CUENTA_PROP', PROP, rf5.ahora, dormir5, eventos5, 'demo_viejo', max_reintentos=5)
print(f"  posición de partida: {ad5.leer_posicion('CUENTA_PROP', PROP)}  (ya plana)")
print(f"  confirmado={confirmado_viejo}, intentos={intentos_viejo}")
print(f"  eventos generados: {len(eventos5)} alerta(s) máxima(s)")
nunca_converge = (confirmado_viejo is False and intentos_viejo == 5 and len(eventos5) == 5)
print(f"  FALLA COMO SE ESPERABA (nunca converge, 5 alertas máximas sobre una cuenta "
      f"YA plana): {'SI' if nunca_converge else 'NO -- la reconstrucción no reprodujo el defecto'}")
assert nunca_converge, "la reconstruccion de 'antes' no reprodujo el Defecto 3 -- revisar"

print("\n-- DESPUÉS (bot/protocolo_dos_patas.py real, revisión 4) --")
rf6, dormir6, ad6 = nuevo(rechaza_aplanar_cantidad_cero=True)
eventos6 = []
confirmado_nuevo, intentos_nuevo = P._aplana_hasta_confirmar(
    ad6, 'CUENTA_PROP', PROP, rf6.ahora, dormir6, eventos6, 'demo_nuevo', max_reintentos=5)
print(f"  posición de partida: {ad6.leer_posicion('CUENTA_PROP', PROP)}  (ya plana)")
print(f"  confirmado={confirmado_nuevo}, intentos={intentos_nuevo}")
print(f"  eventos generados: {len(eventos6)} alerta(s) máxima(s)")
corregido3 = (confirmado_nuevo is True and intentos_nuevo == 0 and len(eventos6) == 0)
print(f"  CORREGIDO (confirmado sin mandar NINGUNA orden, cero alertas): "
      f"{'SI' if corregido3 else 'NO'}")
assert corregido3, "el codigo real no corrigio el Defecto 3"

print()
linea()
print("LOS TRES DEFECTOS: vistos fallar con el código de antes (reconstruido literal),")
print("y vistos corregidos con el código real de bot/protocolo_dos_patas.py (revisión 4).")
linea()
