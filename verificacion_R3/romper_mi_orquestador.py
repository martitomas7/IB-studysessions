# -*- coding: utf-8 -*-
"""R3 (04_GUARDARRAILES) para D2-D7: nada se acepta como correcto sin verse fallar.

Mismo método que romper_mi_nucleo.py (D1): parcheo el CODIGO FUENTE de MI PROPIO
bot/ (nunca tests/ ni modelo/, R6) via string-replace + exec, monkeypatcheo la
funcion rota sobre el modulo real SOLO durante una corrida, corro los 504 dias del
replay pack con bot/orquestador.py::corre_replay, y compruebo que la puerta
(tests/runner_replay_v10.py) SI salta -- por invariante fatal de estado.py (R7,
fatal de verdad: se aborta a media corrida) o por divergencia de fin_de_dia.

Cubre 5 de los 8 patrones de tests/prueba_replay_v10.py, incluida la que D5 exige
explicitamente ("construye tu el orquestador que lo viola: la superviviente opera
dos veces"), mas look-ahead, bloqueada-opera, relevo-D+2 y qcap-ignorado.
"""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ING = os.path.dirname(AQUI)  # ing/ es el padre de verificacion_R3/ en el paquete entregado
sys.path.insert(0, ING)

import bot.sesion as sesion_mod
import bot.ciclo_vida as cv_mod
import bot.orquestador as orq_mod
import bot.estado as E

PACK = json.load(open(os.path.join(ING, 'tests', 'replay_v10.json')))['dias']


def comparar_fin_de_dia(dias, mios):
    """Copia literal de la funcion `comparar()` de tests/runner_replay_v10.py --
    NO se importa ese fichero como modulo (su cuerpo de script corre `sys.exit()`
    al cargarse), y NO se toca tests/ (R6): esto es solo una lectura fiel de su
    misma logica de comparacion, re-declarada aqui."""
    f = []
    for d, m in zip(dias, mios):
        a, b = d['fin_de_dia'], m
        for ruta in (('caja',), ('funded', 'bal'), ('funded', 's0'), ('eval', 'bal'),
                     ('recamara', 'n'), ('pool', 'frescas'), ('pool', 'rotas')):
            x, y = a, b
            for k in ruta: x, y = x[k], y[k]
            if abs(x - y) > 1e-3:
                f.append(f"dia {d['dia']}: {'.'.join(ruta)} esperado {x} obtenido {y}")
    return f


def _fabrica(modulo, viejo, nuevo, nombre_funcion):
    """Compila una copia parcheada del CODIGO FUENTE de `modulo` (un string.replace,
    no el modulo real) y devuelve la funcion `nombre_funcion` resultante. El resto
    de dependencias del modulo (`from bot import config, ...`) se resuelven contra
    los modulos reales, sin tocarlos -- solo la funcion pedida sale distinta."""
    src = open(modulo.__file__).read()
    assert viejo in src, f"ancla no encontrada en {modulo.__file__}: {viejo!r}"
    parcheado = src.replace(viejo, nuevo, 1)
    ns = {'__name__': 'roto_' + modulo.__name__}
    exec(compile(parcheado, 'roto_' + modulo.__name__, 'exec'), ns)
    return ns[nombre_funcion]


def _corre_con_parche(modulo, atributo, funcion_rota):
    """Monkeypatch temporal de `modulo.atributo`, corre los 504 dias, restaura
    SIEMPRE (incluso si el orquestador aborta a media corrida por invariante
    fatal, que es justo lo que estas pruebas buscan disparar)."""
    original = getattr(modulo, atributo)
    setattr(modulo, atributo, funcion_rota)
    try:
        fines, _, _ = orq_mod.corre_replay(
            os.path.join(ING, 'tests', 'replay_v10.json'))
        return dict(abortó=False, día_aborto=None, motivo_aborto=None,
                    divergencias=comparar_fin_de_dia(PACK[:len(fines)], fines))
    except E.EstadoInvalidoError as ex:
        msg = str(ex)
        día = int(msg.split('dia ')[1].split(':')[0]) if 'dia ' in msg else None
        return dict(abortó=True, día_aborto=día, motivo_aborto=msg.splitlines()[0],
                    divergencias=[])
    finally:
        setattr(modulo, atributo, original)


CASOS = []

# --- 1. look-ahead en la barra de entrada (el bug de v8 real: R-3.2) -------------
CASOS.append(('look-ahead en la barra de entrada (R-3.2)', sesion_mod, 'resolver_dia',
    'for b in range(b0 + 1, NB):',
    'for b in range(b0, NB):  # BUG: mira la propia barra de entrada'))

# --- 2. la cuenta bloqueada opera (viola Regla 4.3 / R-2.4) ----------------------
CASOS.append(('la cuenta bloqueada opera (viola R-2.4/4.3)', sesion_mod, 'resolver_dia',
    '''    if bloq:
        dx = 0.0
        cst = 0.0
        h = 0.0
        muere = False
        pausa = False
        tgt = False''',
    '''    if False:  # BUG: la cuenta bloqueada ya no se congela, opera igual
        dx = 0.0
        cst = 0.0
        h = 0.0
        muere = False
        pausa = False
        tgt = False'''))

# --- 3. relevo un dia tarde (D+2 en vez de D+1, ver 05_ORDEN_DE_CONSTRUCCION D6) -
CASOS.append(('relevo un día tarde (D+2)', cv_mod, 'activa_funded_si_toca',
    'if funded_estado["activa"] or funded_estado["espera"] > 0 or not recamara_dormidas:',
    'if funded_estado["activa"] or funded_estado["espera"] > -1 or not recamara_dormidas:  # BUG: un dia de mas'))

# --- 4. qcap ignorado (recamara sin tope, R-4.6) ---------------------------------
CASOS.append(('qcap ignorado (recámara sin tope, R-4.6)', cv_mod, 'qcap_abierto',
    '    return recamara_n < qcap',
    '    return True  # BUG: el tope de recamara ya no se respeta'))

# --- 5. la superviviente opera dos veces el mismo dia (bug de v8, gate de D5) ----
# ANCLA/PARCHE actualizados 20-08-2026 (D8.4 reestructuracion,
# RESPUESTA_D8_CONCURRENCIA.md: procesa_dia_eval se partio en
# arma_intento_eval/arma_empalme_eval/cierra_resolucion_eval -- el texto de la
# version anterior de este caso vivia dentro del cuerpo monolitico que ya no
# existe; b_eval/friccion/T_eval/... dejaron de estar en el scope de
# cierra_resolucion_eval, asi que la inyeccion se reconstruye sobre el
# ENVOLTORIO delgado (procesa_dia_eval), que es donde ph/pl/pc/b0v/resuelve_dia
# siguen en scope justo despues de resolver el intento 0. Mismo bug de
# siempre: una cuenta SUPERVIVIENTE (sin muerte, sin empalme) vuelve a operar
# una SEGUNDA vez el MISMO dia, sobre el mismo b0v -- no debe pasar nunca.
_ANCLA_5 = '''    dia = resuelve_dia(ph=ph, pl=pl, pc=pc, barra_inicio=b0v, plan_resultado=arm["plan"],
                        m=arm["m"], fric=arm["friccion"], deslizamiento=arm["deslizamiento"])
    r = cierra_resolucion_eval(arm["eval_estado"], arm["pool_estado"], arm["caja_delta"], False,
                                arm["eventos"], dia, arm["plan"], cuota, rebuy_on,
                                modo_auto_confirma, m_eval)'''
_PARCHE_5 = '''    dia = resuelve_dia(ph=ph, pl=pl, pc=pc, barra_inicio=b0v, plan_resultado=arm["plan"],
                        m=arm["m"], fric=arm["friccion"], deslizamiento=arm["deslizamiento"])
    r = cierra_resolucion_eval(arm["eval_estado"], arm["pool_estado"], arm["caja_delta"], False,
                                arm["eventos"], dia, arm["plan"], cuota, rebuy_on,
                                modo_auto_confirma, m_eval)
    # BUG INYECTADO (romper_mi_orquestador.py, D5): el bug de v8 -- una cuenta
    # SUPERVIVIENTE (sin muerte, sin empalme) vuelve a operar una SEGUNDA vez
    # el MISMO dia, sobre el mismo b0v. No debe pasar nunca: sesiones_de_eval
    # debe ser <= 1 + empalmes.
    if not dia["muere"]:
        plan_bug = sizing.plan(bal=r["eval_estado"]["bal"], pico=r["eval_estado"]["pico"],
                                G=max(r["eval_estado"]["s0"], 0.0) + cfg.sizing.b_eval_usd.valor(),
                                H=r["eval_estado"]["H"], fric=arm["friccion"], m=m_eval,
                                EXP=cfg.sizing.exp_eval_usd.valor(),
                                T=cfg.proveedor.objetivo_eval_usd.valor(), dcap=1e18,
                                kcap=cfg.sizing.kcap.valor())
        dia_bug = resuelve_dia(ph=ph, pl=pl, pc=pc, barra_inicio=b0v, plan_resultado=plan_bug,
                                m=m_eval, fric=arm["friccion"], deslizamiento=arm["deslizamiento"])
        r = cierra_resolucion_eval(r["eval_estado"], r["pool_estado"], r["caja_delta"],
                                    r["hubo_muerte"], r["eventos"], dia_bug, plan_bug, cuota,
                                    rebuy_on, modo_auto_confirma, m_eval)'''
CASOS.append(('la eval SUPERVIVIENTE opera dos veces (gate D5)', cv_mod, 'procesa_dia_eval',
    _ANCLA_5, _PARCHE_5))

print(f"{'caso roto':50s}{'abortó (invariante)':>22}{'divergencias':>15}{'1er día':>10}")
resultados = []
for nombre, modulo, atributo, viejo, nuevo in CASOS:
    try:
        rota = _fabrica(modulo, viejo, nuevo, atributo)
        r = _corre_con_parche(modulo, atributo, rota)
    except Exception as ex:
        r = dict(abortó=True, día_aborto='?', motivo_aborto=f'EXCEPCION: {ex}', divergencias=[])
    saltó = r['abortó'] or len(r['divergencias']) > 0
    primer_día = r['día_aborto'] or (
        int(r['divergencias'][0].split()[1].rstrip(':')) if r['divergencias'] else '-')
    print(f"{nombre:50s}{str(r['abortó']):>22}{len(r['divergencias']):>15}{str(primer_día):>10}"
          f"  {'SALTÓ ✓' if saltó else 'NO SALTÓ ✗ (FALLO DE LA PRUEBA)'}")
    if r['motivo_aborto']:
        print(f"    -> {r['motivo_aborto']}")
    elif r['divergencias']:
        print(f"    -> {r['divergencias'][0]}")
    resultados.append((nombre, saltó))

print()
n_ok = sum(1 for _, s in resultados if s)
print(f"{n_ok}/{len(resultados)} roturas detectadas por la puerta.")
if n_ok < len(resultados):
    print("AL MENOS UNA ROTURA NO SE DETECTÓ -- la puerta tiene un punto ciego. Ver arriba.")
    sys.exit(1)
sys.exit(0)
