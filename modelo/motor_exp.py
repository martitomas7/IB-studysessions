# -*- coding: utf-8 -*-
"""MOTOR EXPERIMENTAL.  Copia del oraculo con knobs nuevos.

ORIGINAL:  Copia literal de /root/work/bld/sim5_fix.py
con tres anadidos que NO cambian la semantica:
  1. los caminos se cargan desde fuera (para poder usar H7/L7/C7 de 7 anos)
  2. IDXM opcional: matriz de sorteos pregenerada, para poder replicar bit a bit en el motor escalar
  3. LAM: escala la volatilidad de los caminos en puntos (sensibilidad de instrumento)

KNOBS ANADIDOS (todos con el valor por defecto = comportamiento del oraculo):
  COSTES   array indexado por k con el coste round-turn en $ (para probar minis
           contra micros).  None -> CMS*k, igual que antes.
  IDXPOOL  subconjunto de sesiones del que sortear (filtro de volatilidad).
  RANGO    rango en puntos de cada sesion (para el filtro).

`lab/valida.py` comprueba que con los knobs por defecto este motor reproduce
`tests/ref_sim5.py` sesion a sesion.  Si no, el laboratorio no vale nada.
"""
import numpy as np

ULTIMA_HOLGURA = None
ULTIMAS_SESIONES = None

SPX = 7777.0
AR = None


def carga(pref='H7', dirdat=None, lam=1.0):
    global AR
    if dirdat is None:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from core.datos import carpeta
        dirdat = str(carpeta())
    H_ = np.load(f'{dirdat}/{pref}.npy')
    L_ = np.load(f'{dirdat}/{pref.replace("H", "L", 1)}.npy')
    C_ = np.load(f'{dirdat}/{pref.replace("H", "C", 1)}.npy')
    PH = (np.exp(H_) - 1) * SPX
    PL = (np.exp(L_) - 1) * SPX
    PC = (np.exp(C_) - 1) * SPX
    MU = PC.mean(0)
    PH = PH - MU
    PL = PL - MU
    PC = PC - MU
    if lam != 1.0:
        PH, PL, PC = PH * lam, PL * lam, PC * lam
    AR = np.arange(PH.shape[1])[None, :]
    return PH, PL, PC


def fase(rng, n, T, DD, dll, kcap, m0, G, s0, CAPeq, MUm, PH, PL, PC,
         mmin=1, hold=500., mind=1, dcap=None, lock=None, maxses=140,
         CMS=0., SPR=0., PUT=0., b0=None, delev=True, IDXM=None,
         bal0=None, pk0=None, H0=None, dia_espera=True, COSTES=None, IDXPOOL=None,
         GRADUAL=False, CONSIST=None, TPMAX=None, SLMAX=None, EXPMAX=None,
         MMAX=None, KOBJ=1.0, KMIN=1, EODDEATH=False, IDX0=None, FLIP0=None,
         PAUSAFRAC=False):
    NS, NB = PH.shape
    ar = np.arange(NB)[None, :]
    bal = np.zeros(n) if bal0 is None else np.asarray(bal0, float) * np.ones(n)
    pk = np.zeros(n) if pk0 is None else np.asarray(pk0, float) * np.ones(n)
    Hh = np.zeros(n) if H0 is None else np.asarray(H0, float) * np.ones(n)
    Gv = np.asarray(G, float) * np.ones(n); S0 = np.asarray(s0, float) * np.ones(n)
    mv = np.full(n, float(m0)); st = np.zeros(n, np.int8); dias = np.zeros(n); nd = np.zeros(n, int)
    dbar = np.zeros(n, int); nlev = np.zeros(n, bool)
    B0 = np.zeros(n, int) if b0 is None else np.asarray(b0, int).copy()
    # CONSIST: objetivo DINAMICO que cumple la regla de consistencia sin trocear
    # el dia.  El tope no es un limite a lo que se puede ganar hoy: es que el
    # mejor dia no puede pasar del `CONSIST` del beneficio TOTAL del ciclo.  Asi
    # que en vez de capar el dia, se sube el objetivo hasta que el mejor dia
    # quepa:  T_efectivo = max(T, mejor_dia / CONSIST).
    mxd = np.zeros(n)
    Tv = np.full(n, float(T))
    # HOLGURA MINIMA: el equity que se usa para desapalancar es el del PRINCIPIO
    # de la sesion y solo cuenta el P&L REALIZADO.  IBKR marca a mercado en
    # continuo, asi que lo que de verdad puede provocar una llamada de margen es
    # el equity MINIMO INTRASESION.  Aqui se mide.
    holg = np.full(n, np.inf)
    for t in range(maxses):
        live = st == 0
        if not live.any():
            break
        done = live & (bal >= Tv - 1e-9)
        dias = np.where(done & dia_espera, dias + 1., dias); nd = np.where(done, nd + 1, nd)
        st = np.where(done & (nd >= mind), 1, st); live = st == 0
        if not live.any():
            break
        if delev:
            eq = CAPeq - (S0 - Hh)
            if GRADUAL:
                # baja al MAYOR m que el equity sostiene, no directamente al suelo.
                # El salto m->1 es un acantilado: con m0 alto deja k<1 y bloquea
                # el tramo aunque el equity sostuviera m-1 sin problema.
                sost = np.floor((eq - hold) / MUm)
                nuevo = np.clip(sost, mmin, mv)
                baja = live & (nuevo < mv)
                mv = np.where(baja, nuevo, mv); nlev |= baja
            else:
                baja = live & (mv > mmin) & (eq < mv * MUm + hold)
                mv = np.where(baja, mmin, mv); nlev |= baja
            if MMAX:
                # SUBIR m cuando la cobertura se estrecha.  k <= m*M/G, asi que
                # si G ha crecido tanto que k caeria por debajo de KOBJ, se sube
                # m hasta donde el equity aguante (m*MUm + hold <= equity).
                fl_ = pk - DD if lock is None else np.minimum(pk - DD, lock)
                Mm_ = bal - fl_
                den_ = Gv - Hh + (SPR * mv + PUT)
                k_ = np.where(den_ <= 0, 1e9, mv * Mm_ / np.maximum(den_, 1e-9))
                sost_ = np.floor((eq - hold) / MUm)
                nec = np.ceil(KOBJ * np.maximum(den_, 1e-9) / np.maximum(Mm_, 1e-9))
                nuevo_ = np.clip(np.minimum(nec, np.minimum(sost_, float(MMAX))), mv, float(MMAX))
                sube = live & (k_ < KOBJ) & (nuevo_ > mv)
                mv = np.where(sube, nuevo_, mv)
        fl = pk - DD if lock is None else np.minimum(pk - DD, lock)
        Mm = bal - fl; Ms = np.minimum(dll, Mm)
        den = Gv - Hh + (SPR * mv + PUT)
        k = np.where(den <= 0, float(kcap), np.floor(np.minimum(mv * Mm / np.maximum(den, 1e-9), kcap)))
        # KMIN: abandono temprano (auditoria 16-08-2026).  El oraculo bloquea en
        # k < 1; con KMIN > 1 la cuenta se abandona ANTES de ponerse a moler
        # sesiones a k bajisima con objetivos inalcanzables.  La rama bloqueada
        # es la unica que pierde dinero Y la que mas dias consume: cortarla
        # antes ataca numerador y denominador del EV a la vez.
        # KMIN=1 (por defecto) reproduce el oraculo EXACTAMENTE.
        st = np.where(live & (k < KMIN), 3, st); live = st == 0
        k = np.maximum(k, 1.); pv = 5 * k
        cst = (CMS * k) if COSTES is None else COSTES[k.astype(int)]
        top = (Tv - bal + cst) if dcap is None else np.minimum(Tv - bal + cst, dcap + cst)
        nu = np.maximum(top, 1e-9) / pv; ndn = np.maximum(Ms, 1e-9) / pv
        # TPMAX: tope al objetivo del dia EN PUNTOS, no en dolares.  Solo muerde
        # cuando k es pequena: con k=1 el objetivo cae a 200 puntos del precio,
        # que no se toca nunca (el rango medio de la sesion son 94), asi que la
        # sesion se va a la campana arrastrando toda la excursion a favor de la
        # prop — y eso es exactamente lo que le cuesta equity al hedge.
        if TPMAX:
            nu = np.minimum(nu, float(TPMAX))
        if EXPMAX:
            # el tope de verdad esta en DOLARES de exposicion del hedge, no en
            # puntos: 100 puntos del ES son 1,29 % y del NQ un 0,4 %.  En puntos
            # sale  EXPMAX / (m · v_h),  que ademas se ensancha solo al
            # desapalancar, que es justo lo correcto.
            nu = np.minimum(nu, float(EXPMAX) / (5. * mv))
        # SLMAX: la idea gemela en el stop.  Con k=1 el stop tambien queda a 200
        # puntos, asi que la sesion no puede ni morir: se va a la campana a la
        # deriva pagando friccion.  Acercarlo la hace resolver.
        if SLMAX:
            ndn = np.minimum(ndn, float(SLMAX))
        if t == 0 and IDX0 is not None:
            # REARRANQUE CON CONTINUIDAD (17-08-2026).  La primera sesion de la
            # cadena continua sobre EL MISMO camino en el que murio la cuenta
            # anterior (IDX0), desde su barra (b0), en vez de sobre un camino
            # independiente.  Es lo que permite medir el sorteo informado: sin
            # continuidad, la correlacion intradia muerte->resto-del-dia no
            # existe en el simulador.  FLIP0 espeja el camino por filas segun la
            # politica de direccion.  IDX0=None (defecto) = oraculo EXACTO.
            idx = IDX0
        elif IDXM is not None:
            idx = IDXM[t]
        elif IDXPOOL is not None:
            idx = IDXPOOL[rng.integers(0, len(IDXPOOL), n)]
        else:
            idx = rng.integers(0, NS, n)
        ph = PH[idx]; pl = PL[idx]; pc = PC[idx]
        bi = np.minimum(B0, NB - 1); p0 = np.take_along_axis(pc, bi[:, None], 1)
        if t == 0 and IDX0 is not None and FLIP0 is not None and FLIP0.any():
            f_ = FLIP0[:, None]
            ph2 = np.where(f_, 2 * p0 - pl, ph)
            pl2 = np.where(f_, 2 * p0 - ph, pl)
            pc = np.where(f_, 2 * p0 - pc, pc)
            ph, pl = ph2, pl2
        val = ar >= B0[:, None]
        hD = val & ((pl - p0) <= -ndn[:, None]); hU = val & ((ph - p0) >= nu[:, None])
        iD = np.where(hD.any(1), hD.argmax(1), NB + 1); iU = np.where(hU.any(1), hU.argmax(1), NB + 1)
        low = live & (iD <= NB) & (iD <= iU); tgt = live & (iU <= NB) & (iU < iD)
        if EODDEATH:
            # MUERTE SOLO AL CIERRE (auditoria del Rapid EOD, 17-08-2026).
            # En un plan de drawdown EOD no hay barrera de muerte intradia: la
            # sesion sale por el objetivo (intradia, orden limite) o llega a la
            # campana, y ALLI se compara el balance con el suelo.  Consecuencias
            # que cambian la geometria entera:
            #   - la muerte y el cierre del hedge ocurren AL MISMO precio (la
            #     campana): la cobertura no tiene deslizamiento de barrera
            #   - no hay pausa del DLL ni muerte temprana: cada sesion dura el
            #     dia entero y el rearranque es al dia siguiente (dbar=NB-1)
            #   - la excursion intradia en contra no mata: puede respirar
            # EODDEATH=False (por defecto) reproduce el oraculo EXACTAMENTE.
            tgt = live & (iU <= NB)
            low = np.zeros_like(low)
            iD = np.full_like(iD, NB + 1)   # sin barrera: la holgura se mide hasta el objetivo o la campana
            dx = np.where(tgt, nu, pc[:, -1] - p0[:, 0])
        else:
            dx = np.where(low, -ndn, np.where(tgt, nu, pc[:, -1] - p0[:, 0]))
        muere = low & (Ms >= Mm - 1e-9)
        Hh0 = Hh.copy()
        Hh = np.where(live, Hh - 5 * mv * dx - (SPR * mv + PUT), Hh)
        bal = np.where(live, bal + dx * pv - cst, bal)
        if EODDEATH:
            fl_eod = pk - DD if lock is None else np.minimum(pk - DD, lock)
            muere = live & ~tgt & (bal < fl_eod - 1e-9)
        pk = np.where(live, np.maximum(pk, bal), pk)
        usado = np.where(muere & ~np.bool_(EODDEATH), (iD - B0) / NB, (NB - B0) / NB)
        if PAUSAFRAC:
            # CAMBIO DE CUENTA EN PAUSA (17-08-2026, idea del usuario).  Cuando
            # el DLL pausa (toque del stop SIN muerte), el resto del dia hoy se
            # pierde.  Con inventario de evaluaciones (MFF: hasta 10 en cartera,
            # 1 activa), otra cuenta podria usar ese resto.  Este knob cobra a
            # la pausa solo la fraccion USADA del dia: es la COTA SUPERIOR del
            # valor del cambio (supone conmutacion sin coste y regla de MFF
            # favorable — pendiente de confirmar por escrito).  Defecto: off.
            pausa = low & ~muere
            usado = np.where(pausa, (iD - B0) / NB, usado)
        dias = np.where(live, dias + np.maximum(usado, 1. / NB), dias)
        dbar = np.where(muere, (NB - 1) if EODDEATH else np.minimum(iD, NB - 1),
                        dbar)
        nd = np.where(live, nd + 1, nd)
        if CONSIST:
            gan = dx * pv - cst
            mxd = np.where(live, np.maximum(mxd, np.maximum(gan, 0.)), mxd)
            Tv = np.maximum(float(T), mxd / CONSIST)
        # peor excursion a favor de la prop antes de que cierre la sesion:
        # es lo que mas puede llegar a perder el hedge con la posicion abierta
        sal = np.minimum(np.minimum(iD, iU), NB - 1)
        msk = (ar >= B0[:, None]) & (ar <= sal[:, None])
        fav = np.where(msk, ph - p0, -np.inf).max(1)
        fav = np.clip(fav, 0., nu)
        eq_ini = CAPeq - (S0 - Hh0)
        eq_low = eq_ini - 5 * mv * fav
        holg = np.where(live, np.minimum(holg, eq_low - mv * MUm), holg)
        st = np.where(muere, 2, np.where(tgt & (bal >= Tv - 1e-9) & (nd >= mind), 1, st))
        B0 = np.zeros(n, int)
    st = np.where(st == 0, 3, st)
    global ULTIMA_HOLGURA, ULTIMAS_SESIONES
    ULTIMA_HOLGURA = holg          # se deja aparte para no cambiar la firma
    ULTIMAS_SESIONES = nd          # sesiones consumidas por camino
    return st, Hh, dias, dbar, nlev, mv
