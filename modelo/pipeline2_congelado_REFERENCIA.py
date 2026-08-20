# -*- coding: utf-8 -*-
"""PIPELINE v2 · el modelo definitivo multi-cuenta · 17-08-2026.

Todo lo hablado, junto:
  - CONTRA: tras un dia con muerte, la direccion del sistema se mantiene
  - COBERTURAS PARALELAS: cada cuenta (funded + evals) lleva SU hedge con SU
    identidad de cobertura (den = G - H + friccion, k = floor(m*Mm/den))
  - POOL DE SUSCRIPCIONES: N evals COMPRADAS (<=10).  Coste fijo N*77/mes.
    Una eval rota espera el reset GRATIS de su dia de facturacion (tasa
    sostenida: 1 reset/sub/30 dias -> p=1/30 diaria; conservador porque la
    primera espera media real es ~15 dias).  Al aprobar, la sub se cancela
    (gratis) y se recompra una nueva ($77) para mantener el pool.
  - EMPALME: si la eval que opera muere, el bot EMPALMA el mismo dia con una
    eval fresca del pool en la barra de la muerte, HEREDANDO el hedge (misma
    direccion por CONTRA): el intento empalmado paga media friccion (estimacion
    adoptada, igual que en el modelo de cadena).
  - EMERGENCIA (opcional): pool sin frescas -> cancelar una rota y recomprar
    ($77) para no dejar el slot vacio.
  - Funded: 1 activa, dormida se activa AL DIA SIGUIENTE de morir la anterior;
    anti-hedging interno -> todas las cuentas comparten la direccion del dia.

pool=0 reproduce EXACTAMENTE el pipeline v1 (cuota $77 por intento) con la
misma semilla: es la regresion.
Anti-overfitting: cero parametros estadisticos; mitades; crono; 2 semillas;
pesimista (MARGEN 500, SPR 4, crono).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import motor_exp as M

FX = 1.15738
B = 100.0 * FX
CUOTA = 77.0
CMS = 1.04
KCAP = 40
MLL, DLL, LOCK = 2000.0, 1000.0, 100.0
T_EVAL = 3000.0
BUF = 2100.0
W_BRUTO = 2000.0
SP = 0.80
CONS = 0.50
M_FUN, EXP_FUN = 3.0, 1000.0
CAPITAL = 5300.0 * FX

PH, PL, PC = M.carga('HG22')
NS, NB = PH.shape

FASES = [((BUF + W_BRUTO if c == 1 else W_BRUTO), SP * W_BRUTO,
          (BUF + W_BRUTO if c == 1 else W_BRUTO) * CONS) for c in range(1, 6)]


def sesion(bal, pk, G, H, b0, ph, pl, pc, T, dcap, m, exp, kcap, act, fricv, eod=False):
    """UNA sesion vectorizada (filas activas `act`).  Matematica 1:1 del motor
    validado; `fricv` es la friccion POR FILA (permite empalme a media)."""
    fl = np.minimum(pk - MLL, LOCK)
    Mm = bal - fl
    Ms = np.minimum(DLL, Mm)
    den = G - H + fricv
    k = np.where(den <= 0, float(kcap),
                 np.floor(np.minimum(m * Mm / np.maximum(den, 1e-9), kcap)))
    if eod:  # cuña de comision: dimensionar con Mm - cst para cubrir el gate EOD
        k1 = np.maximum(k, 1.0)
        k = np.where(den <= 0, float(kcap),
                     np.floor(np.minimum(m * np.maximum(Mm - CMS * k1, 1e-9)
                                         / np.maximum(den, 1e-9), kcap)))
    k = np.where(act, k, 1.0)
    bloq = act & (k < 1)
    k = np.maximum(k, 1.0)
    pv = 5.0 * k
    cst = CMS * k
    top = np.minimum(T - bal + cst, dcap + cst)
    nu = np.minimum(np.maximum(top, 1e-9) / pv, exp / (5.0 * m))
    ndn = (np.full_like(Ms, DLL) if eod else np.maximum(Ms, 1e-9)) / pv
    ar = np.arange(NB)[None, :]
    p0 = np.take_along_axis(pc, np.minimum(b0, NB - 1)[:, None], 1)
    val = ar >= b0[:, None]
    hD = val & ((pl - p0) <= -ndn[:, None])
    hU = val & ((ph - p0) >= nu[:, None])
    iD = np.where(hD.any(1), hD.argmax(1), NB + 1)
    iU = np.where(hU.any(1), hU.argmax(1), NB + 1)
    low = act & (iD <= NB) & (iD <= iU)
    tgt = act & (iU <= NB) & (iU < iD)
    dx = np.where(low, -ndn, np.where(tgt, nu, pc[:, -1] - p0[:, 0]))
    if eod:
        # muerte si la perdida REALIZADA (pausa DLL o cierre) perfora el suelo vivo
        muere = act & (dx * pv - cst <= -(Mm - 1e-9))
        pausa = low & ~muere
    else:
        muere = low & (Ms >= Mm - 1e-9)
        pausa = low & ~muere
    h = np.where(act, -5.0 * m * dx - fricv, 0.0)
    ib = np.minimum(np.where(low, iD, np.where(tgt, iU, NB - 1)), NB - 1)
    return dx, h, k, cst, muere, pausa, tgt, ib, bloq


def corre(R=3000, DIAS=252, E=1, m_eval=3.0, exp_eval=1000.0, seed=7,
          crono=False, half=None, dormidas_ini=1,
          pool=0, empalme=False, emerg=False, rebuy=True,
          SPR=3.0, reset_p=1.0 / 30.0, guarda=None,
          retencion=None, puerta=-1e18, pausa_f=None, holg=None, qcap=None,
          qcap_tes=None, eval_lo=None,
          m_fun=None, exp_fun=None, b0g=0, contra_dias=1, ventana=None, eod=False,
          cal_rth=None):
    rng = np.random.default_rng(seed)
    if m_fun is None: m_fun = M_FUN
    if exp_fun is None: exp_fun = EXP_FUN
    lo, hi = 0, NS
    if half == 0: hi = NS // 2
    if half == 1: lo = NS // 2
    caja = np.zeros(R); fees = np.zeros(R)
    n_att = np.zeros(R); n_apr = np.zeros(R); n_fd = np.zeros(R)
    idle = np.zeros(R)
    n_emerg = np.zeros(R); n_rebuy = np.zeros(R); n_reset = np.zeros(R)
    minc = np.zeros(R)
    meses = np.zeros((R, DIAS // 21))
    peakm = np.zeros(R); dd = np.zeros(R)      # drawdown desde marcas mensuales
    throt = np.zeros(R, bool)                  # guarda de tesoreria (frena evals)
    # tesoreria EXACTA: retiros simulados, umbral de activacion, freno funded
    ret = np.zeros(R)                          # retirado acumulado
    min_tes = np.zeros(R)                      # minimo de la tesoreria viva
    throtf = np.zeros(R, bool)                 # freno de la funded
    # muro DINAMICO: solo cuenta el capital realmente comprometido hoy
    br_dyn = np.zeros(R, bool)
    fday = np.full(R, -1)                      # primer dia de parada (muro dinamico)
    mode22 = np.zeros(R, bool)                 # ventana dinamica: False=RTH, True=22h
    if holg is None:
        holg = CAPITAL - 2.0 * (m_fun * 150.0 + exp_fun)
    sdir = np.where(rng.random(R) < 0.5, 1.0, -1.0)
    hubo_muerte = np.zeros(R, bool)
    cont_cnt = np.zeros(R, int)                # contra multi-dia (contador)
    # funded
    f_act = np.zeros(R, bool); f_fase = np.zeros(R, int)
    f_bal = np.zeros(R); f_pk = np.zeros(R)
    f_s0 = np.zeros(R); f_H = np.zeros(R); f_nd = np.zeros(R, int)
    f_espera = np.zeros(R, bool)
    d_n = np.full(R, dormidas_ini, int)
    d_sunk = np.full(R, 500.0) * dormidas_ini
    # evals
    e_act = np.zeros((R, E), bool)
    e_bal = np.zeros((R, E)); e_pk = np.zeros((R, E))
    e_s0 = np.zeros((R, E)); e_H = np.zeros((R, E))
    # pool de suscripciones (solo si pool>0)
    fresh = np.full(R, pool, int)
    broken = np.zeros(R, int)
    if crono:
        ini = rng.integers(lo, hi, R)

    def toma(need):
        """Saca una eval fresca del pool para las filas `need`.  Devuelve
        (arranca, coste): con pool=0 arranca siempre y cuesta CUOTA."""
        if pool == 0:
            return need, np.where(need, CUOTA, 0.0)
        uf = need & (fresh > 0)
        ue = need & ~uf & (emerg & (broken > 0))
        fresh[uf] -= 1
        broken[ue] -= 1
        n_emerg[ue] += 1
        return uf | ue, np.where(ue, CUOTA, 0.0)

    for t in range(DIAS):
        j = (ini + t) % (hi - lo) + lo if crono else rng.integers(lo, hi, R)
        ph0, pl0, pc0 = PH[j], PL[j], PC[j]
        nueva = np.where(rng.random(R) < 0.5, 1.0, -1.0)
        cont_cnt = np.where(hubo_muerte, contra_dias, np.maximum(cont_cnt - 1, 0))
        sdir = np.where(cont_cnt > 0, sdir, nueva)         # CONTRA (multi-dia)
        hubo_muerte = np.zeros(R, bool)
        p00 = pc0[:, 0:1]
        neg = sdir < 0
        ph = np.where(neg[:, None], 2 * p00 - pl0, ph0)
        pl = np.where(neg[:, None], 2 * p00 - ph0, pl0)
        pc = np.where(neg[:, None], 2 * p00 - pc0, pc0)

        # renovaciones del pool (coste fijo diario) y resets de facturacion
        if pool > 0:
            caja -= pool * CUOTA / 30.0
            fees += pool * CUOTA / 30.0
            r = rng.binomial(broken, reset_p)
            fresh += r
            broken -= r
            n_reset += r

        # freno de la funded cerca del muro (histeresis sobre tesoreria viva)
        tes = caja - ret
        # ventana por CALENDARIO: (frac_dias_de_datos, b0_rth, margen)
        # los dias de vispera de datos se opera RTH (entrada tras el dato);
        # el margen nunca supera `margen` porque nunca se duerme en vispera
        if cal_rth is not None:
            frac, b0r, _mar = cal_rth
            mask_datos = rng.random(R) < frac
            b0v = np.where(mask_datos, b0r, 0).astype(int)
        elif ventana is not None:
            b0r, x_on, x_off, m22, mrth = ventana
            mode22 = np.where(~mode22 & (tes >= x_on), True,
                              np.where(mode22 & (tes < x_off), False, mode22))
            b0v = np.where(mode22, 0, b0r).astype(int)
        else:
            b0v = np.full(R, b0g, int)
        if pausa_f is not None:
            flo, fhi = pausa_f
            throtf = np.where(tes < flo, True, np.where(tes > fhi, False, throtf))

        # --- activar funded dormida (con puerta de tesoreria: fase A -> B)
        puede = ~f_act & ~f_espera & (d_n > 0) & (tes >= puerta)
        if puede.any():
            f_act = f_act | puede
            f_fase = np.where(puede, 1, f_fase)
            f_bal = np.where(puede, 0.0, f_bal)
            f_pk = np.where(puede, 0.0, f_pk)
            s0m = np.where(d_n > 0, d_sunk / np.maximum(d_n, 1), 500.0)
            f_s0 = np.where(puede, s0m, f_s0)
            f_H = np.where(puede, 0.0, f_H)
            f_nd = np.where(puede, 0, f_nd)
            d_sunk = np.where(puede, d_sunk - s0m, d_sunk)
            d_n = np.where(puede, d_n - 1, d_n)
        f_espera = np.zeros(R, bool)

        # --- sesion FUNDED (las filas frenadas por throtf NO operan hoy)
        fa = f_act & ~throtf
        if fa.any():
            fi = np.clip(f_fase - 1, 0, 4)
            TA = np.array([f[0] for f in FASES]); WA = np.array([f[1] for f in FASES])
            DA = np.array([f[2] for f in FASES])
            Tv, Wv, Dv = TA[fi], WA[fi], DA[fi]
            G = np.maximum(f_s0, 0.0) + B
            b0 = b0v
            frv = np.full(R, SPR * m_fun)
            dx, h, k, cst, mu, pa, tg, ib, bq = sesion(
                f_bal, f_pk, G, f_H, b0, ph, pl, pc, Tv, Dv, m_fun, exp_fun,
                KCAP, fa, frv, eod=eod)
            caja += np.where(fa, h, 0.0)
            f_H += np.where(fa, h, 0.0)
            f_bal += np.where(fa, dx * 5 * k - cst, 0.0)
            f_pk = np.maximum(f_pk, f_bal)
            f_nd += fa.astype(int)
            hubo_muerte |= mu
            n_fd += mu
            f_espera |= mu
            f_act = f_act & ~mu & ~bq
            pasa = tg & (f_bal >= Tv - 1e-9) & (f_nd >= 2)
            if pasa.any():
                caja += np.where(pasa, Wv, 0.0)
                f_s0 = np.where(pasa, f_s0 - f_H - Wv, f_s0)
                f_H = np.where(pasa, 0.0, f_H)
                f_bal = np.where(pasa, 0.0, f_bal)
                f_pk = np.where(pasa, 0.0, f_pk)
                f_nd = np.where(pasa, 0, f_nd)
                f_fase = np.where(pasa, f_fase + 1, f_fase)
                fin = pasa & (f_fase > 5)
                f_act = f_act & ~fin
                f_espera |= fin

        # guarda de tesoreria: frena INTENTOS NUEVOS de eval cuando el DRAWDOWN
        # desde la marca de barrido mensual supera `on`; reactiva bajo `off`
        if guarda is not None:
            on, off = guarda
            caida = peakm - caja
            throt = np.where(caida > on, True, np.where(caida < off, False, throt))

        # --- slots de EVAL (qcap: no fabricar aprobadas si la recamara esta llena;
        #     el cap se LEVANTA cuando la tesoreria viva alcanza qcap_tes)
        qok = np.ones(R, bool) if qcap is None else (d_n < qcap)
        if qcap is not None and qcap_tes is not None:
            qok = qok | (caja - ret >= qcap_tes)
        # eval pequena en fase inicial: (m_lo, exp_lo, hasta_tes)
        if eval_lo is not None:
            mlo, xlo, hasta = eval_lo
            chica = (caja - ret) < hasta
            mv = np.where(chica, mlo, m_eval)
            expv = np.where(chica, xlo, exp_eval)
        else:
            mv = np.full(R, m_eval)
            expv = np.full(R, exp_eval)
        commit_e = np.zeros(R)                 # capital comprometido por evals hoy
        commit_m = np.zeros(R); commit_x = np.zeros(R)
        for s in range(E):
            libres = ~e_act[:, s] & ~throt & qok
            arr, coste = toma(libres)
            idle += (libres & ~arr)
            e_act[:, s] = e_act[:, s] | arr
            e_bal[:, s] = np.where(arr, 0.0, e_bal[:, s])
            e_pk[:, s] = np.where(arr, 0.0, e_pk[:, s])
            e_s0[:, s] = np.where(arr, CUOTA, e_s0[:, s])
            e_H[:, s] = np.where(arr, 0.0, e_H[:, s])
            caja -= coste; fees += coste
            n_att += arr
            commit_e += np.where(e_act[:, s], mv * 150.0 + expv, 0.0)
            commit_m += np.where(e_act[:, s], mv, 0.0)
            commit_x += np.where(e_act[:, s], expv, 0.0)
            b0 = b0v
            frv = SPR * mv
            for intento in range(2):
                act = e_act[:, s]
                if not act.any():
                    break
                G = np.maximum(e_s0[:, s], 0.0) + B
                Tv = np.full(R, T_EVAL); Dv = np.full(R, 1e9)
                dx, h, k, cst, mu, pa, tg, ib, bq = sesion(
                    e_bal[:, s], e_pk[:, s], G, e_H[:, s], b0, ph, pl, pc,
                    Tv, Dv, mv, expv, KCAP, act, frv, eod=eod)
                caja += np.where(act, h, 0.0)
                e_H[:, s] += np.where(act, h, 0.0)
                e_bal[:, s] += np.where(act, dx * 5 * k - cst, 0.0)
                e_pk[:, s] = np.maximum(e_pk[:, s], e_bal[:, s])
                hubo_muerte |= mu
                if pool > 0:
                    broken += mu.astype(int)          # la sub muerta se rompe
                pasa = tg & (e_bal[:, s] >= T_EVAL - 1e-9)
                if pasa.any():
                    sunk = e_s0[:, s] - e_H[:, s]
                    d_sunk = np.where(pasa, d_sunk + sunk, d_sunk)
                    d_n = np.where(pasa, d_n + 1, d_n)
                    n_apr += pasa
                    e_act[:, s] = e_act[:, s] & ~pasa
                    if pool > 0 and rebuy:            # recomprar la cancelada
                        caja -= np.where(pasa, CUOTA, 0.0)
                        fees += np.where(pasa, CUOTA, 0.0)
                        fresh += pasa.astype(int)
                        n_rebuy += pasa
                if intento == 0 and mu.any():
                    quiere = mu & (ib < NB - 4) & ~throt & qok
                    rearr, coste = toma(quiere)
                    e_act[:, s] = (e_act[:, s] & ~mu) | rearr
                    e_bal[:, s] = np.where(rearr, 0.0, e_bal[:, s])
                    e_pk[:, s] = np.where(rearr, 0.0, e_pk[:, s])
                    e_s0[:, s] = np.where(rearr, CUOTA, e_s0[:, s])
                    e_H[:, s] = np.where(rearr, 0.0, e_H[:, s])
                    caja -= coste; fees += coste
                    n_att += rearr
                    b0 = np.where(rearr, ib, b0v)
                    if empalme:                        # herencia del hedge
                        frv = np.where(rearr, SPR * mv * 0.5, SPR * mv)
                    if not rearr.any():
                        break
                else:
                    e_act[:, s] = e_act[:, s] & ~mu & ~bq
                    break

        minc = np.minimum(minc, caja)
        dd = np.maximum(dd, peakm - caja)
        min_tes = np.minimum(min_tes, caja - ret)
        # muro dinamico: capital − (par funded reservado + evals comprometidas hoy)
        if cal_rth is not None:
            muro = CAPITAL - (m_fun * _mar + exp_fun) - (commit_m * _mar + commit_x)
        elif ventana is not None:
            mar = np.where(mode22, m22, mrth)
            muro = CAPITAL - (m_fun * mar + exp_fun) - (commit_m * mar + commit_x)
        else:
            muro = CAPITAL - (m_fun * 150.0 + exp_fun) - commit_e
        nuevo = (caja - ret < -muro) & ~br_dyn
        br_dyn |= nuevo
        fday = np.where(nuevo & (fday < 0), t, fday)
        if (t + 1) % 21 == 0:
            meses[:, (t + 1) // 21 - 1] = caja
            peakm = np.maximum(peakm, caja)    # marca de barrido mensual
            if retencion is not None:          # retiro real de fin de mes
                sw = np.maximum(0.0, caja - retencion - ret)
                ret += sw

    jmes = caja / DIAS * 21.0
    return dict(jmes=float(jmes.mean()), p5=float(np.percentile(jmes, 5)),
                p50=float(np.percentile(jmes, 50)),
                fees=float(fees.mean() / DIAS * 21),
                att=float(n_att.mean() / DIAS * 21),
                apr=float(n_apr.mean() / DIAS * 21),
                fdm=float(n_fd.mean() / DIAS * 21),
                idle=float(idle.mean() / DIAS),
                dorm=float(d_n.mean()),
                pos=float((caja > 0).mean()),
                emerg=float(n_emerg.mean() / DIAS * 21),
                rebuy=float(n_rebuy.mean() / DIAS * 21),
                reset=float(n_reset.mean() / DIAS * 21),
                parada=float((min_tes < -holg).mean()),
                parada_dyn=float(br_dyn.mean()),
                fmes=[float(((fday >= 21 * a) & (fday < 21 * b)).mean())
                      for a, b in ((0, 3), (3, 6), (6, 12))],
                cruza_tes=lambda x, m=min_tes: float((m < -x).mean()),
                retirado=float(ret.mean() / DIAS * 21),
                dd=dict(p50=float(np.percentile(dd, 50)),
                        p95=float(np.percentile(dd, 95)),
                        p99=float(np.percentile(dd, 99)),
                        p999=float(np.percentile(dd, 99.9)),
                        peor=float(dd.max()),
                        cruza=lambda x, d=dd: float((d > x).mean())),
                minc=dict(p50=float(np.percentile(minc, 50)),
                          p95=float(np.percentile(-minc, 95) * -1),
                          p99=float(np.percentile(minc, 1)),
                          p999=float(np.percentile(minc, 0.1)),
                          peor=float(minc.min())),
                meses=dict(media=[float(x) for x in meses.mean(0)],
                           p5=[float(x) for x in np.percentile(meses, 5, axis=0)],
                           p50=[float(x) for x in np.percentile(meses, 50, axis=0)]))


def linea(et, r, cap=None):
    c = f" cap {cap:>6,.0f}$" if cap is not None else ""
    print(f"{et:<40} $/mes {r['jmes']:>8,.2f} · p5 {r['p5']:>7,.0f} · "
          f"cuotas {r['fees']:>6,.0f} · int/mes {r['att']:>5.1f} · "
          f"aprob/mes {r['apr']:>4.2f} · mtes.fun/mes {r['fdm']:>4.2f} · "
          f"idle {r['idle']*100:>4.1f}% · dorm.fin {r['dorm']:>4.1f}{c}")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else 'todo'

    if modo in ('reg', 'todo'):
        print("== REGRESION: pool=0 debe reproducir el pipeline v1 (misma semilla) ==")
        r = corre(E=1, m_eval=3.0, exp_eval=1000.0, seed=7, pool=0)
        linea("v2 pool=0 (esperado ~2.006)", r)
        print()

    if modo in ('barrido', 'todo'):
        print("== BARRIDO: pool / empalme / emergencia (E=1, m_eval=3, s7) ==")
        for et, kw in (
            ("pool=0 (cuota por intento, ref)", dict(pool=0)),
            ("pool=0 + empalme", dict(pool=0, empalme=True)),
            ("pool=5, sin emerg", dict(pool=5)),
            ("pool=5 + emerg", dict(pool=5, emerg=True)),
            ("pool=10, sin emerg", dict(pool=10)),
            ("pool=10 + emerg", dict(pool=10, emerg=True)),
            ("pool=10 + emerg + empalme", dict(pool=10, emerg=True, empalme=True)),
            ("pool=5 + emerg + empalme", dict(pool=5, emerg=True, empalme=True)),
        ):
            r = corre(E=1, m_eval=3.0, exp_eval=1000.0, seed=7, **kw)
            linea(et, r)
        print()

    if modo in ('e2', 'todo'):
        print("== ¿E=2 revive con el pool? (coste fijo comparte pool) ==")
        for et, kw in (
            ("E=2 pool=10 + emerg + empalme", dict(E=2, pool=10, emerg=True, empalme=True)),
            ("E=2 m_eval=1 EXP500 pool=10+em+emp", dict(E=2, m_eval=1.0, exp_eval=500.0,
                                                       pool=10, emerg=True, empalme=True)),
        ):
            r = corre(seed=7, **kw)
            me = kw.get('m_eval', 3.0); xe = kw.get('exp_eval', 1000.0)
            cap = (M_FUN * 150 + EXP_FUN) + kw['E'] * (me * 150 + xe)
            linea(et, r, cap)
        print()

    if modo in ('final', 'todo'):
        print("== VALIDACION FINAL (pool=10 + emerg + empalme) ==")
        for E in (1, 2):
            print(f"--- E={E} · m_eval=3 · EXP 1000 ---")
            for et, kw in (("iid s7", dict(seed=7)),
                           ("iid s11", dict(seed=11)),
                           ("crono s7", dict(seed=7, crono=True)),
                           ("mitad 2019-22", dict(seed=7, half=0)),
                           ("mitad 2022-26", dict(seed=7, half=1)),
                           ("pesimista (SPR4, crono)", dict(seed=7, crono=True, SPR=4.0))):
                r = corre(E=E, m_eval=3.0, exp_eval=1000.0,
                          pool=10, emerg=True, empalme=True, **kw)
                linea(f"  {et}", r)
            print()
