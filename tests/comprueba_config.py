# -*- coding: utf-8 -*-
"""COMPROBADOR DE 03_CONFIG.yaml.

Hace tres cosas, y las tres son fatales si fallan:
  1. Recalcula TODOS los campos marcados DERIVADO y los compara con lo escrito.
  2. Comprueba que la configuracion del fichero coincide EXACTAMENTE con la config
     congelada V10 con la que se midio la cifra objetivo (modelo/estres_v10.py).
     Si divergen, la cifra publicada deja de aplicar: el paquete esta roto.
  3. Se auto-verifica: rompe el YAML en memoria de tres maneras y exige que salte.

Uso:  python comprueba_config.py [ruta_a_03_CONFIG.yaml]
"""
import os, sys, copy, math
try:
    import yaml
except ImportError:
    sys.exit("falta pyyaml:  pip install pyyaml")

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(AQUI, '..', '03_CONFIG.yaml')

# La config congelada con la que se midio la cifra objetivo.  Copiada a mano de
# modelo/estres_v10.py:13 -- si aquella cambia, esta lista tiene que cambiar con ella.
V10_CONGELADA = dict(E=1, m_eval=2., exp_eval=1110., m_fun=4., exp_fun=1480.,
                     b_eval=40., b_fun=70., pool=2, qcap=3, qcap_tes=10000.,
                     retencion=6860., emerg=True, empalme=True, dormidas_ini=0,
                     eod=True, cms=1.90, nb_use=86, relevo=0, slip_micro=2.5)
TOL = 1e-2          # los DERIVADOS se publican redondeados a 3 decimales


def v(c, *ruta):
    x = c
    for p in ruta:
        x = x[p]
    return x['valor'] if isinstance(x, dict) and 'valor' in x else x


def comprueba(c):
    """Devuelve la lista de fallos.  Vacia = todo bien."""
    f = []

    def eq(nombre, esperado, obtenido, tol=TOL):
        if abs(esperado - obtenido) > tol:
            f.append(f"{nombre}: el fichero dice {obtenido}, el calculo da {esperado}")

    def igual(nombre, esperado, obtenido):
        if esperado != obtenido:
            f.append(f"{nombre}: el fichero dice {obtenido!r}, la config congelada usa {esperado!r}")

    fx = v(c, 'capital', 'fx_eur_usd')

    # ---- 1. DERIVADOS -----------------------------------------------------------
    eq('capital_usd', v(c, 'capital', 'capital_eur') * fx, v(c, 'capital', 'capital_usd'))
    eq('b_eval_usd',  v(c, 'sizing', 'b_eval_eur') * fx,   v(c, 'sizing', 'b_eval_usd'))
    eq('b_fun_usd',   v(c, 'sizing', 'b_fun_eur') * fx,    v(c, 'sizing', 'b_fun_usd'))

    margen = v(c, 'hedge_broker', 'margen_intradia_usd')
    pares = (v(c, 'sizing', 'm_fun') * margen + v(c, 'sizing', 'exp_fun_usd')
             + v(c, 'sizing', 'm_eval') * margen + v(c, 'sizing', 'exp_eval_usd'))
    eq('pares_usd', pares, v(c, 'tesoreria', 'pares_usd'))
    eq('holgura_usd', v(c, 'capital', 'capital_usd') - v(c, 'tesoreria', 'pares_usd'),
       v(c, 'tesoreria', 'holgura_usd'))

    # la escalera se DERIVA de sus cuatro parametros declarados, no de literales
    esc = c['proveedor']['escalera_retiro']
    buf = v(c, 'proveedor', 'buf_usd')
    w   = v(c, 'proveedor', 'w_bruto_usd')
    sp  = v(c, 'proveedor', 'split')
    co  = v(c, 'proveedor', 'cons')
    eq('escalera ciclo_1 umbral', buf + w, esc['ciclo_1']['umbral_bruto_usd'])
    eq('escalera ciclo_1 retira', sp * w,  esc['ciclo_1']['retira_usd'])
    eq('escalera ciclo_1 tope_dia', (buf + w) * co, esc['ciclo_1']['tope_dia_usd'])
    eq('escalera ciclos_2_a_5 umbral', w,  esc['ciclos_2_a_5']['umbral_bruto_usd'])
    eq('escalera ciclos_2_a_5 retira', sp * w, esc['ciclos_2_a_5']['retira_usd'])
    eq('escalera ciclos_2_a_5 tope_dia', w * co, esc['ciclos_2_a_5']['tope_dia_usd'])
    # y esos cuatro tienen que coincidir con las constantes del motor congelado
    igual('buf_usd (BUF del motor)',   2100.0, float(buf))
    igual('w_bruto_usd (W_BRUTO)',     2000.0, float(w))
    igual('split (SP del motor)',      0.80,   float(sp))
    igual('cons (CONS del motor)',     0.50,   float(co))
    if 'fsuelo' in c['sizing']:
        igual('fsuelo',                1.0,    float(v(c, 'sizing', 'fsuelo')))
    igual('kcap (KCAP del motor)',     40,     v(c, 'sizing', 'kcap'))
    igual('n_ciclos',                  5,      v(c, 'proveedor', 'escalera_retiro', 'n_ciclos'))
    igual('mll_usd',   2000.0, float(v(c, 'proveedor', 'mll_usd')))
    igual('dll_usd',   1000.0, float(v(c, 'proveedor', 'dll_usd')))
    igual('lock_usd',   100.0, float(v(c, 'proveedor', 'lock_usd')))
    igual('objetivo_eval_usd', 3000.0, float(v(c, 'proveedor', 'objetivo_eval_usd')))
    igual('cuota_sub_usd',       77.0, float(v(c, 'proveedor', 'cuota_sub_usd')))
    igual('spr_usd (SPR del motor)', 3.0, float(v(c, 'hedge_broker', 'spr_usd')))
    igual('barras_de_la_serie (NB)',  88, v(c, 'sesion', 'barras_de_la_serie'))
    igual('cal_rth.frac', 0.18, float(v(c, 'sesion', 'cal_rth', 'frac_dias_dato')))
    igual('cal_rth.b0',     62, v(c, 'sesion', 'cal_rth', 'b0_rth'))
    igual('cal_rth.margen', 40.0, float(v(c, 'sesion', 'cal_rth', 'margen_usd')))
    igual('contra_dias', 1, v(c, 'sesion', 'direccion', 'contra_dias'))

    # --- NINGUN simbolo de las formulas de la norma puede faltar --------------------
    #     (hallazgo M1 de la auditoria del 19-08: fsuelo y cons se usaban en las formulas
    #      de la norma y NO existian en la config, que se declara unica fuente de numeros)
    claves = set()

    def recoge(x):
        if isinstance(x, dict):
            for k2, v2 in x.items():
                claves.add(k2); recoge(v2)
        elif isinstance(x, list):
            for v2 in x: recoge(v2)
    recoge(c)
    for simbolo in ('fsuelo', 'cons', 'buf_usd', 'w_bruto_usd', 'split', 'kcap',
                    'barras_por_dia', 'barras_de_la_serie', 'contra_dias', 'spr_usd',
                    'slip_usd_micro', 'empalme_friccion_factor', 'reset_prob_diaria',
                    'dias_por_mes', 'retencion_c_usd', 'qcap', 'qcap_tes_usd'):
        if simbolo not in claves:
            f.append(f"simbolo '{simbolo}' usado por la norma y AUSENTE de la config")

    # --- la taxonomia tiene que ser una de las cuatro, y SUPUESTO exige coste -------
    def recorre(x, ruta=''):
        if isinstance(x, dict):
            t = x.get('tipo')
            if t is not None and t not in ('DADO', 'SUPUESTO', 'OPTIMIZADO', 'DERIVADO'):
                f.append(f"{ruta}: tipo desconocido {t!r}")
            for k2, v2 in x.items():
                recorre(v2, f"{ruta}.{k2}" if ruta else k2)
    recorre(c)

    eq('spr_usd >= comision + tick',
       v(c, 'hedge_broker', 'comision_rt_usd') + v(c, 'hedge_broker', 'tick_usd'),
       v(c, 'hedge_broker', 'spr_usd'), tol=0.20)      # se redondea al alza, conservador
    if v(c, 'hedge_broker', 'spr_usd') < v(c, 'hedge_broker', 'comision_rt_usd') + v(c, 'hedge_broker', 'tick_usd'):
        f.append("spr_usd es MENOR que comision + tick: la friccion estaria infravalorada")

    eq('reset_prob_diaria = 1/30', 1.0 / 30.0, v(c, 'proveedor', 'reset_prob_diaria'), tol=1e-6)

    # ---- 2. COINCIDENCIA CON LA CONFIG CONGELADA --------------------------------
    igual('n_evals_simultaneas (E)', V10_CONGELADA['E'], v(c, 'orquestacion', 'n_evals_simultaneas'))
    igual('m_eval',        V10_CONGELADA['m_eval'],     float(v(c, 'sizing', 'm_eval')))
    igual('exp_eval_usd',  V10_CONGELADA['exp_eval'],   float(v(c, 'sizing', 'exp_eval_usd')))
    igual('m_fun',         V10_CONGELADA['m_fun'],      float(v(c, 'sizing', 'm_fun')))
    igual('exp_fun_usd',   V10_CONGELADA['exp_fun'],    float(v(c, 'sizing', 'exp_fun_usd')))
    igual('b_eval_eur',    V10_CONGELADA['b_eval'],     float(v(c, 'sizing', 'b_eval_eur')))
    igual('b_fun_eur',     V10_CONGELADA['b_fun'],      float(v(c, 'sizing', 'b_fun_eur')))
    igual('pool_subs',     V10_CONGELADA['pool'],       v(c, 'orquestacion', 'pool_subs'))
    igual('qcap',          V10_CONGELADA['qcap'],       v(c, 'orquestacion', 'qcap'))
    igual('qcap_tes_usd',  V10_CONGELADA['qcap_tes'],   float(v(c, 'orquestacion', 'qcap_tes_usd')))
    igual('retencion_c_usd', V10_CONGELADA['retencion'], float(v(c, 'orquestacion', 'retencion_c_usd')))
    igual('empalme',       V10_CONGELADA['empalme'],    v(c, 'orquestacion', 'empalme'))
    igual('emergencia',    V10_CONGELADA['emerg'],      v(c, 'orquestacion', 'emergencia'))
    igual('dormidas_ini',  V10_CONGELADA['dormidas_ini'], v(c, 'orquestacion', 'dormidas_ini'))
    igual('eod',           V10_CONGELADA['eod'],        v(c, 'sesion', 'eod'))
    igual('comision_rt_usd (cms)', V10_CONGELADA['cms'], float(v(c, 'proveedor', 'comision_rt_usd')))
    igual('barras_por_dia (nb_use)', V10_CONGELADA['nb_use'], v(c, 'sesion', 'barras_por_dia'))
    igual('relevo_dias',   V10_CONGELADA['relevo'],     v(c, 'proveedor', 'relevo_dias'))
    igual('slip_usd_micro', V10_CONGELADA['slip_micro'], float(v(c, 'hedge_broker', 'slip_usd_micro')))

    return f


def main():
    c = yaml.safe_load(open(RUTA))
    fallos = comprueba(c)
    for x in fallos:
        print("FALLA  " + x)
    print(f"03_CONFIG.yaml: {'OK' if not fallos else str(len(fallos)) + ' FALLOS'}")

    # ---- 3. AUTO-VERIFICACION: que se demuestre que sabe fallar -----------------
    print("\nauto-verificacion (la comprobacion tiene que romper cuando se rompe el fichero):")
    pruebas = [
        ('capital_usd mal (6134 -> 6000)',
         lambda d: d['capital'].__setitem__('capital_usd', {'valor': 6000.0})),
        ('m_fun cambiado (4 -> 3): ya no es la config medida',
         lambda d: d['sizing'].__setitem__('m_fun', {'valor': 3})),
        ('spr_usd por debajo de comision + tick',
         lambda d: d['hedge_broker'].__setitem__('spr_usd', {'valor': 1.00})),
        ('cons cambiado (0,50 -> 0,60): la escalera deja de cuadrar',
         lambda d: d['proveedor'].__setitem__('cons', {'valor': 0.60})),
        ('tipo inventado (DADO -> IMPUESTO_POR_MI)',
         lambda d: d['sizing']['fsuelo'].__setitem__('tipo', 'IMPUESTO_POR_MI')),
        ('fsuelo BORRADO del fichero (el fallo M1 de la auditoria)',
         lambda d: d['sizing'].pop('fsuelo')),
    ]
    ok = not fallos
    for nombre, rompe in pruebas:
        d = copy.deepcopy(c)
        rompe(d)
        n = len(comprueba(d))
        print(f"  {nombre:<52} -> {n} fallo(s) {'OK' if n else 'ERROR: NO DETECTADO'}")
        if not n:
            ok = False
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
