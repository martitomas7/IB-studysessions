# -*- coding: utf-8 -*-
"""Verificación R3 de bot/protocolo_dos_patas.py contra bot/adaptador_falso.py.
Cubre las ramas de 07_ADAPTADOR_NT8.md §5.3 (apertura) y §5.4 (cierre) con
reloj falso (nada de esperar segundos reales)."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)  # ing/ es el padre de verificacion_R3/ en el paquete entregado
sys.path.insert(0, ING)

from bot.adaptador_falso import AdaptadorFalso
from bot import protocolo_dos_patas as P

MES = "MES (Micro E-mini S&P 500)"


class RelojFalso:
    def __init__(self):
        self.t = 0.0
    def ahora(self):
        return self.t
    def avanza(self, dt):
        self.t += dt


def nuevo():
    rf = RelojFalso()
    def dormir(s): rf.avanza(s)
    ad = AdaptadorFalso(reloj=rf.ahora)
    return rf, dormir, ad


resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond, detalle))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


print("=== 1. camino feliz: apertura + cierre ===")
rf, dormir, ad = nuevo()
ev = []
r = P.abre_las_dos_patas(ad, 'H', 'PR', 'MES 12-26', 1, 2, 15, eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("apertura abre las dos patas", r['abierto'] is True, r)
ok("posicion hedge = -m (contra)", ad.posiciones.get(('H', MES)) == -2)
ok("posicion prop = +k", ad.posiciones.get(('PR', 'MES 12-26')) == 15)
r2 = P.cierra_las_dos_patas(ad, 'PR', 'MES 12-26', 'H', eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("cierre cierra las dos patas", r2['cerrado'] is True, r2)
ok("posicion hedge tras cierre = 0", ad.posiciones.get(('H', MES)) == 0)
ok("posicion prop tras cierre = 0", ad.posiciones.get(('PR', 'MES 12-26')) == 0)

print("=== 2. N_hedge expira, cancelacion limpia (2b -> CANCELADA): no se opera hoy ===")
rf, dormir, ad = nuevo()
ad.programa_abrir('H', MES, fill_en_s=None)   # el hedge NUNCA llena
ev = []
r = P.abre_las_dos_patas(ad, 'H', 'PR', 'MES 12-26', 1, 2, 15, eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("no se abre nada", r['abierto'] is False and r['motivo'] == 'N_hedge_expirado_cancelado', r)
ok("no hay posicion prop (nunca se intento)", ('PR', 'MES 12-26') not in ad.posiciones or ad.posiciones[('PR','MES 12-26')] == 0)
ok("posicion hedge = 0 (cancelado limpio)", ad.posiciones.get(('H', MES), 0) == 0)
ok("evento timeout_hedge registrado", any(e['tipo'] == 'timeout_hedge' for e in ev), ev)

print("=== 3. N_hedge expira PERO la cancelacion llega tarde (2b-LLENA): sigue a FASE PROP ===")
rf, dormir, ad = nuevo()
def hook_llena_hedge(adapt, orden):
    adapt.fuerza_fill(orden['order_id'])
ad.programa_abrir('H', MES, fill_en_s=None, en_cancelar=hook_llena_hedge)
ev = []
r = P.abre_las_dos_patas(ad, 'H', 'PR', 'MES 12-26', 1, 2, 15, eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("se abren las dos patas pese a la carrera", r['abierto'] is True, r)
ok("posicion hedge = -m (el fill tardio SI cuenta)", ad.posiciones.get(('H', MES)) == -2)
ok("evento timeout_hedge con resultado LLENA y precio_fill_hedge",
   any(e['tipo']=='timeout_hedge' and e['resultado']=='LLENA' and 'precio_fill_hedge' in e for e in ev), ev)

print("=== 4. N expira, prop cancelada limpia (4b -> CANCELADA): SOLO ENTONCES se aplana el hedge ===")
rf, dormir, ad = nuevo()
ad.programa_abrir('PR', 'MES 12-26', fill_en_s=None)   # la prop NUNCA llena
ev = []
r = P.abre_las_dos_patas(ad, 'H', 'PR', 'MES 12-26', 1, 2, 15, eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("no se abre nada", r['abierto'] is False and r['motivo'] == 'N_expirado_prop_cancelada_hedge_aplanado', r)
ok("hedge SI se abrio primero y LUEGO se aplano -> posicion final 0", ad.posiciones.get(('H', MES), 0) == 0)
ok("prop nunca quedo con posicion", ad.posiciones.get(('PR', 'MES 12-26'), 0) == 0)

print("=== 5. N expira PERO la prop llena tarde (4b-LLENA): NO se toca el hedge, las dos patas quedan puestas ===")
rf, dormir, ad = nuevo()
def hook_llena_prop(adapt, orden):
    adapt.fuerza_fill(orden['order_id'])
ad.programa_abrir('PR', 'MES 12-26', fill_en_s=None, en_cancelar=hook_llena_prop)
ev = []
r = P.abre_las_dos_patas(ad, 'H', 'PR', 'MES 12-26', 1, 2, 15, eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("se consideran abiertas las dos patas", r['abierto'] is True, r)
ok("hedge SIGUE abierto, no se toco", ad.posiciones.get(('H', MES)) == -2)
ok("prop SI quedo abierta (el fill tardio gano)", ad.posiciones.get(('PR', 'MES 12-26')) == 15)
ok("evento divergencia_fill registrado", any(e['tipo']=='divergencia_fill' for e in ev), ev)

print("=== 6. cierre: la prop no confirma a la primera, se reintenta -- el hedge NUNCA se toca hasta que confirma ===")
rf, dormir, ad = nuevo()
# abrir primero (camino feliz)
P.abre_las_dos_patas(ad, 'H', 'PR', 'MES 12-26', 1, 2, 15, eventos=[], reloj=rf.ahora, dormir=dormir)
ad.programa_aplanar('PR', 'MES 12-26', ['CANCELADA', 'RECHAZADA', 'LLENA'])
ev = []
r2 = P.cierra_las_dos_patas(ad, 'PR', 'MES 12-26', 'H', eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("cierra correctamente tras 3 intentos", r2['cerrado'] is True and r2['intentos_prop'] == 3, r2)
ok("2 eventos de reintento de la prop", sum(1 for e in ev if e['tipo']=='ALERTA_MAXIMA' and e['motivo']=='aplanar_no_confirma_cierre_prop') == 2, ev)
ok("hedge cerrado limpio despues", ad.posiciones.get(('H', MES), 0) == 0)

print("=== 7. COMPROBACION 11 (08_LABORATORIO.md §8): el boton de panico no produce pata sola ===")
print("    7a. version CORRECTA (cierra_las_dos_patas): la prop no confirma a la primera")
rf, dormir, ad = nuevo()
P.abre_las_dos_patas(ad, 'H', 'PR', 'MES 12-26', 1, 2, 15, eventos=[], reloj=rf.ahora, dormir=dormir)
ad.programa_aplanar('PR', 'MES 12-26', ['CANCELADA'])   # falla la primera vuelta, luego LLENA (plan agotado)
ev = []
r = P.cierra_las_dos_patas(ad, 'PR', 'MES 12-26', 'H', eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("la version CORRECTA SI cierra las dos, nunca deja una pata sola",
   r['cerrado'] is True and ad.posiciones.get(('H', MES), 0) == 0
   and ad.posiciones.get(('PR', 'MES 12-26'), 0) == 0, r)

print("    7b. version INGENUA/ROTA (cierra_las_dos_patas_INGENUO_ROTO): MISMO escenario")
rf, dormir, ad = nuevo()
P.abre_las_dos_patas(ad, 'H', 'PR', 'MES 12-26', 1, 2, 15, eventos=[], reloj=rf.ahora, dormir=dormir)
ad.programa_aplanar('PR', 'MES 12-26', ['CANCELADA'])   # la prop NO confirma a la primera vuelta
ev = []
r = P.cierra_las_dos_patas_INGENUO_ROTO(ad, 'PR', 'MES 12-26', 'H', eventos=ev, reloj=rf.ahora, dormir=dormir)
pata_prop_abierta = ad.posiciones.get(('PR', 'MES 12-26'), 0) != 0
pata_hedge_abierta = ad.posiciones.get(('H', MES), 0) != 0
una_sola_pata = pata_prop_abierta != pata_hedge_abierta   # XOR: exactamente una, no las dos ni ninguna
ok("la version INGENUA SI produce una pata sola -- la comprobacion la caza",
   una_sola_pata, dict(resultado=r, prop_abierta=pata_prop_abierta, hedge_abierta=pata_hedge_abierta))
print(f"       -> con la version rota: prop_abierta={pata_prop_abierta} hedge_abierta={pata_hedge_abierta}"
      f" (exactamente una pata queda sola: {una_sola_pata})")

print("=== 8. DEFECTO 1 (revision operador 20-08-2026): rechazo/cancelacion limpios ANTES del timeout ===")
print("    8a. hedge RECHAZADO de inmediato: cero tiempo consumido, sin alerta maxima")
rf, dormir, ad = nuevo()
ad.programa_abrir('H', MES, rechazar=True)
ev = []
t0 = rf.t
r = P.abre_las_dos_patas(ad, 'H', 'PR', 'MES 12-26', 1, 2, 15, eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("hedge rechazado: no se abre nada, motivo limpio",
   r['abierto'] is False and r['motivo'] == 'hedge_rechazado_no_se_opera_hoy', r)
ok("hedge rechazado: CERO tiempo logico consumido (antes: N_hedge=30s enteros)", (rf.t - t0) < 1e-6)
ok("hedge rechazado: SIN alerta maxima (es informacion cierta, no ambigua)",
   ev and 'alerta' not in ev[0], ev)

print("    8b. prop RECHAZADA de inmediato: el hedge YA abierto se aplana, sin dejarlo N segundos desnudo")
rf, dormir, ad = nuevo()
ad.programa_abrir('PR', 'MES 12-26', rechazar=True)
ev = []
t0 = rf.t
r = P.abre_las_dos_patas(ad, 'H', 'PR', 'MES 12-26', 1, 2, 15, eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("prop rechazada: no se abre nada, hedge aplanado",
   r['abierto'] is False and r['motivo'] == 'prop_rechazada_hedge_aplanado', r)
ok("prop rechazada: CERO tiempo logico consumido (antes: N=5s enteros con el hedge desnudo)",
   (rf.t - t0) < 1e-6)
ok("prop rechazada: hedge NO queda abierto", ad.posiciones.get(('H', MES), 0) == 0)
ok("prop rechazada: SIN alerta maxima", not any('alerta' in e for e in ev), ev)

print("=== 9. DEFECTO 2 (revision operador 20-08-2026): hay_conexion() antes de abrir nada ===")
rf, dormir, ad = nuevo()
ad.desconecta('PR')
ev = []
r = P.abre_las_dos_patas(ad, 'H', 'PR', 'MESprop', 1, 4, 15, eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("con la prop desconectada, NO se abre ninguna pata",
   r['abierto'] is False and r['motivo'] == 'conexion_caida_no_se_abre_nada', r)
ok("no queda ninguna posicion abierta", not ad.posiciones, ad.posiciones)
ok("evento de conexion caida con alerta maxima registrado",
   ev and ev[0]['tipo'] == 'conexion_caida' and ev[0]['alerta'] == 'MAXIMA', ev)
# control: con las dos conectadas, abre normal
rf, dormir, ad = nuevo()
r_ok = P.abre_las_dos_patas(ad, 'H', 'PR', 'MESprop', 1, 4, 15, eventos=[], reloj=rf.ahora, dormir=dormir)
ok("control: con las dos conectadas, SI abre normal", r_ok['abierto'] is True, r_ok)

print("=== 10. DEFECTO 3 (revision operador 20-08-2026): aplanar sale por POSICION, no por estado de orden ===")
print("    10a. adaptador MENOS complaciente: rechaza aplanar() de cantidad cero")
rf, dormir, ad = nuevo()
ad.rechaza_aplanar_cantidad_cero = True
ev = []
ok_, intentos_ = P._aplana_hasta_confirmar(ad, 'PR', 'MESprop', rf.ahora, dormir, ev, 'prueba')
ok("cuenta ya plana: confirmado sin mandar NINGUNA orden (0 intentos)",
   ok_ is True and intentos_ == 0, (ok_, intentos_))
ok("cuenta ya plana: no se genero ninguna alerta", ev == [], ev)

print("    10b. cierre real con el adaptador rechazando cantidad cero: sigue funcionando de punta a punta")
rf, dormir, ad = nuevo()
ad.rechaza_aplanar_cantidad_cero = True
P.abre_las_dos_patas(ad, 'H', 'PR', 'MES 12-26', 1, 2, 15, eventos=[], reloj=rf.ahora, dormir=dormir)
ev = []
r = P.cierra_las_dos_patas(ad, 'PR', 'MES 12-26', 'H', eventos=ev, reloj=rf.ahora, dormir=dormir)
ok("cierra correctamente incluso con el falso rechazando cantidad cero",
   r['cerrado'] is True, r)
ok("las dos patas quedan exactamente en cero",
   ad.posiciones.get(('H', MES), 0) == 0 and ad.posiciones.get(('PR', 'MES 12-26'), 0) == 0)

print("\n" + "="*70)
n_ok = sum(1 for _, c, _ in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
sys.exit(0 if n_ok == len(resultados) else 1)
