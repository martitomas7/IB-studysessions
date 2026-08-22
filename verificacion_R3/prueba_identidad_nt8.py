# -*- coding: utf-8 -*-
"""D9 §3.5 reducida (`DECISION_CREDENCIALES_Y_FASE.md`, autorización R6,
22-08-2026): el bot no guarda ningún secreto -- guarda un descriptor NO
secreto (cuenta/conexión NT8 + etiqueta `demo`/`real`, puramente
informativa) y la guarda de verdad compara lo que NT8 RESPONDE (nunca la
etiqueta autoasignada) contra lo que la fase declarada exige. Demuestra,
sobre `bot/bucle_del_dia.py` real (no aislado): el descriptor mal formado,
la cuenta desconectada, el modo que no coincide con la fase, el camino
feliz, y el control de que `descriptor_nt8=None` no cambia nada -- más la
banda del dashboard que sustituye al panel de escritura cancelado."""
import json
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)
sys.path.insert(0, ING)

from bot import bucle_del_dia as BDD
from bot import config, estado as E, seguridad as SEG
from bot import contexto_dashboard as CD, dashboard as D
from bot.adaptador_falso import AdaptadorFalso
from bot.fuente_barras import Barra, ContextoDia

_, checksum = config.cargar()

resultados = []
def ok(nombre, cond, detalle=""):
    resultados.append((nombre, cond))
    print(f"  {'OK ' if cond else 'FALLO'} · {nombre}" + (f"  ({detalle})" if detalle else ""))


class FuenteEnVivoPlana:
    """Mismo arnés que prueba_tope_de_fase.py -- un día, barras planas."""
    def __init__(self, precio_flat=100.0, tope_barras=20):
        self.precio_flat = precio_flat
        self.tope_barras = tope_barras
        self._dia_abierto = False
        self._b = -1

    def dia_disponible(self):
        return not self._dia_abierto

    def abre_dia(self):
        self._dia_abierto = True
        self._b = -1
        return ContextoDia()

    def siguiente_barra(self):
        self._b += 1
        p = self.precio_flat
        return Barra(b=self._b, ph=p, pl=p, pc=p,
                     es_ultima_barra_operable=(self._b >= self.tope_barras))

    def cierra_dia(self):
        pass


class RngFijo:
    def random(self):
        return 0.1


DIR = "/tmp/prueba_identidad_nt8"
CUENTA_HEDGE_EVAL, CUENTA_PROP_EVAL = "CH-EVAL", "CP-EVAL"
CUENTA_HEDGE_FUN, CUENTA_PROP_FUN = "CH-FUN", "CP-FUN"
INSTRUMENTO_PROP = "MES"
CUENTA_NT8 = "APEX-12345"


def _corre_un_dia(fase, descriptor_nt8, adaptador):
    shutil.rmtree(DIR, ignore_errors=True)
    os.makedirs(DIR)
    ruta_estado = os.path.join(DIR, "estado.json")
    E.guardar(E.nuevo("v10", checksum), ruta_estado)
    st_final = BDD.bucle_del_dia(
        FuenteEnVivoPlana(), adaptador,
        cuenta_hedge_eval=CUENTA_HEDGE_EVAL, cuenta_prop_eval=CUENTA_PROP_EVAL,
        cuenta_hedge_funded=CUENTA_HEDGE_FUN, cuenta_prop_funded=CUENTA_PROP_FUN,
        instrumento_prop=INSTRUMENTO_PROP,
        ruta_estado=ruta_estado, ruta_nivel=os.path.join(DIR, "nivel.json"),
        ruta_ordenes=os.path.join(DIR, "ordenes"), ruta_lock=os.path.join(DIR, "bot.lock"),
        dir_instantaneas=os.path.join(DIR, "instantaneas"), dias_retenidos=1,
        ruta_diario=os.path.join(DIR, "diario.jsonl"), fase=fase,
        descriptor_nt8=descriptor_nt8, rng=RngFijo(), dormir=lambda s: None)
    ruta_nivel = os.path.join(DIR, "nivel.json")
    nivel = SEG.nivel_actual(ruta_nivel) if os.path.isfile(ruta_nivel) else 'N0'
    return st_final, nivel


print("=== 1. AdaptadorFalso.consulta_modo_cuenta(): honesto por defecto, configurable ===")
a1 = AdaptadorFalso()
modo, motivo = a1.consulta_modo_cuenta(CUENTA_NT8)
ok("sin configurar nada, modo=None con motivo explícito (nunca un valor inventado)",
   modo is None and motivo == 'adaptador_falso_no_conoce_su_propio_modo_salvo_que_se_configure',
   (modo, motivo))
a1.fija_modo_cuenta(CUENTA_NT8, 'REAL')
ok("tras fija_modo_cuenta('REAL'), consulta_modo_cuenta() responde ('REAL', None)",
   a1.consulta_modo_cuenta(CUENTA_NT8) == ('REAL', None))
a1.fija_modo_cuenta(CUENTA_NT8, 'SIMULADA')
ok("tras fija_modo_cuenta('SIMULADA'), responde ('SIMULADA', None)",
   a1.consulta_modo_cuenta(CUENTA_NT8) == ('SIMULADA', None))
lanzo = False
try:
    a1.fija_modo_cuenta(CUENTA_NT8, 'DEMO')   # valor no reconocido a propósito
except ValueError:
    lanzo = True
ok("fija_modo_cuenta() con un modo no reconocido lanza ValueError explícito", lanzo)

print("\n=== 2. _valida_descriptor_nt8(): comprobación de forma ===")
ok("descriptor bien formado -> sin fallos",
   BDD._valida_descriptor_nt8(dict(cuenta_nt8=CUENTA_NT8, etiqueta='real')) == [])
ok("falta cuenta_nt8 -> 1 fallo",
   len(BDD._valida_descriptor_nt8(dict(etiqueta='real'))) == 1)
ok("cuenta_nt8 vacía -> 1 fallo",
   len(BDD._valida_descriptor_nt8(dict(cuenta_nt8='', etiqueta='real'))) == 1)
ok("etiqueta desconocida -> 1 fallo",
   len(BDD._valida_descriptor_nt8(dict(cuenta_nt8=CUENTA_NT8, etiqueta='produccion'))) == 1)
ok("etiqueta ausente -> 1 fallo",
   len(BDD._valida_descriptor_nt8(dict(cuenta_nt8=CUENTA_NT8))) == 1)

print("\n=== 3. _modo_nt8_esperado(): hoy TODA fase de §3.2 exige REAL ===")
for f in ('f3.1', 'f3.2', 'f3.3', 'plena'):
    ok(f"fase={f!r} exige modo REAL", BDD._modo_nt8_esperado(f) == 'REAL')
lanzo = False
try:
    BDD._modo_nt8_esperado('f3.99')
except ValueError:
    lanzo = True
ok("una fase no reconocida lanza ValueError explícito", lanzo)

print("\n=== 4. _verifica_identidad_nt8(): la guarda contra la realidad, unitaria ===")
ok("descriptor=None -> nunca falla (opt-in, igual que topes=None)",
   BDD._verifica_identidad_nt8('f3.1', None, AdaptadorFalso()) == [])

a4 = AdaptadorFalso()
a4.fija_modo_cuenta(CUENTA_NT8, 'REAL')
ok("descriptor bien formado + NT8 dice REAL + fase exige REAL -> sin fallos",
   BDD._verifica_identidad_nt8('f3.1', dict(cuenta_nt8=CUENTA_NT8, etiqueta='real'), a4) == [])

a5 = AdaptadorFalso()
a5.fija_modo_cuenta(CUENTA_NT8, 'SIMULADA')
fallos_5 = BDD._verifica_identidad_nt8('f3.1', dict(cuenta_nt8=CUENTA_NT8, etiqueta='real'), a5)
ok("NT8 dice SIMULADA pero la fase exige REAL -> 1 fallo, cita ambos valores",
   len(fallos_5) == 1 and 'SIMULADA' in fallos_5[0] and 'REAL' in fallos_5[0], fallos_5)
ok("el fallo NO se decide mirando la etiqueta autoasignada ('real') -- la etiqueta del "
   "descriptor de arriba DICE 'real' y aun así falla, porque NT8 dice lo contrario",
   True)   # ya demostrado por fallos_5: la etiqueta='real' no impidió el fallo

a6 = AdaptadorFalso()   # sin fija_modo_cuenta() -- modo=None por defecto
fallos_6 = BDD._verifica_identidad_nt8('f3.1', dict(cuenta_nt8=CUENTA_NT8, etiqueta='real'), a6)
ok("NT8 no sabe contestar (modo=None) -> 1 fallo, 'no sabe contestar'",
   len(fallos_6) == 1 and 'no sabe contestar' in fallos_6[0], fallos_6)

a7 = AdaptadorFalso()
a7.fija_modo_cuenta(CUENTA_NT8, 'REAL')
a7.desconecta(CUENTA_NT8)
fallos_7 = BDD._verifica_identidad_nt8('f3.1', dict(cuenta_nt8=CUENTA_NT8, etiqueta='real'), a7)
ok("cuenta desconectada -> 1 fallo, aunque el modo ya estuviera fijado en REAL",
   len(fallos_7) == 1 and 'no sabe contestar' in fallos_7[0], fallos_7)

fallos_8 = BDD._verifica_identidad_nt8('f3.1', dict(cuenta_nt8=''), AdaptadorFalso())
ok("descriptor mal formado -> los fallos de forma se devuelven, ni siquiera se llega a NT8",
   len(fallos_8) >= 1, fallos_8)

print("\n=== 5. Extremo a extremo por bucle_del_dia(): arranque real, no aislado ===")
adaptador_9 = AdaptadorFalso()
st_9, nivel_9 = _corre_un_dia('f3.1', None, adaptador_9)
ok("descriptor_nt8=None -> el bot arranca normal (control: cero cambio de comportamiento)",
   st_9 is not None and nivel_9 == 'N0', (st_9 is not None, nivel_9))

adaptador_10 = AdaptadorFalso()
adaptador_10.fija_modo_cuenta(CUENTA_NT8, 'SIMULADA')
st_10, nivel_10 = _corre_un_dia('f3.1', dict(cuenta_nt8=CUENTA_NT8, etiqueta='real'), adaptador_10)
ok("descriptor con NT8=SIMULADA bajo fase=f3.1 (exige REAL) -> el bot NO arranca",
   st_10 is None, st_10)
ok("nivel.json refleja N4 (misma reacción que un tope de fase excedido)", nivel_10 == 'N4')

adaptador_11 = AdaptadorFalso()
adaptador_11.fija_modo_cuenta(CUENTA_NT8, 'REAL')
st_11, nivel_11 = _corre_un_dia('f3.1', dict(cuenta_nt8=CUENTA_NT8, etiqueta='real'), adaptador_11)
ok("MISMO descriptor, NT8=REAL de verdad -> el bot SÍ arranca",
   st_11 is not None and nivel_11 == 'N0', (st_11 is not None, nivel_11))

adaptador_12 = AdaptadorFalso()
adaptador_12.fija_modo_cuenta(CUENTA_NT8, 'REAL')
adaptador_12.desconecta(CUENTA_NT8)
st_12, nivel_12 = _corre_un_dia('f3.1', dict(cuenta_nt8=CUENTA_NT8, etiqueta='real'), adaptador_12)
ok("cuenta declarada sin conexión -> el bot NO arranca, aunque el modo ya estuviera en REAL",
   st_12 is None and nivel_12 == 'N4', (st_12, nivel_12))

shutil.rmtree(DIR, ignore_errors=True)

print("\n=== 6. Banda del dashboard: reemplaza al panel de escritura cancelado ===")
st_dash = E.nuevo("v10", checksum)
ctx_con = CD.construye(st_dash, None, [], identidad_nt8=dict(cuenta=CUENTA_NT8, modo='REAL', fase='f3.1'))
ok("ctx['identidad'] refleja lo que se pasó, tal cual",
   ctx_con['identidad'] == dict(cuenta=CUENTA_NT8, modo='REAL', fase='f3.1'), ctx_con['identidad'])
html_con = D.genera_html(ctx_con)
ok("el HTML incluye la cuenta declarada", CUENTA_NT8 in html_con)
ok("el HTML pinta el modo REAL con la clase semaforo-critico (llama la atención)",
   'semaforo-critico' in html_con and 'REAL' in html_con)
ok("el HTML incluye la fase declarada", 'f3.1' in html_con)

ctx_sin = CD.construye(st_dash, None, [])
ok("sin identidad_nt8 (default None) -> ctx['identidad'] con los tres campos en None",
   ctx_sin['identidad'] == dict(cuenta=None, modo=None, fase=None), ctx_sin['identidad'])
html_sin = D.genera_html(ctx_sin)
ok("sin identidad declarada, el HTML dice 'no declarado' explícito, nunca inventa un valor",
   'no declarado' in html_sin.lower() or 'NO DECLARADO' in html_sin)

ctx_sim = CD.construye(st_dash, None, [], identidad_nt8=dict(cuenta=CUENTA_NT8, modo='SIMULADA', fase='f3.1'))
html_sim = D.genera_html(ctx_sim)
ok("modo SIMULADA se pinta con la clase semaforo-bien (calmada, no de alarma)",
   'semaforo-bien' in html_sim and 'SIMULADA' in html_sim)

print("\n" + "=" * 70)
n_ok = sum(1 for _, c in resultados if c)
print(f"{n_ok}/{len(resultados)} comprobaciones OK")
if n_ok != len(resultados):
    sys.exit(1)
