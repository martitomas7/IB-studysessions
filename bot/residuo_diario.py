# -*- coding: utf-8 -*-
"""residuo_diario.py · D8, instrumentación §3.1 · REVISION_REV5.md §4.1 ·
ORDEN_DE_TRABAJO_D8.md §3.1 · 10_SEGURIDAD.md §4.E

"El residuo diario modelo-contra-realidad: resolver_dia con las barras
reales y el estado real, menos lo que pasó. Por cuenta y día." No es solo
instrumentación -- es el detector de corrupción silenciosa (10_SEGURIDAD.md
§4.E: "un sistema equivocado pero funcionando no hace ningún ruido"), y en
Fase 3.1 se convierte literalmente en la MEDICIÓN de `spr_usd`/
`slip_usd_micro` (REVISION_REV5.md §4.1) -- los dos SUPUESTOS de
`03_CONFIG.yaml` que hoy son un punto de partida razonado, no un dato
medido.

Este módulo contiene SOLO la comparación pura: dado el resultado TEÓRICO
(lo que `sesion.resolver_dia`, o su equivalente en vivo verificado por
oráculo, habría dado con fills exactos al nivel) y el resultado REAL (lo
que de verdad pasó, con el fill real del bracket), calcula el residuo.
NO decide de dónde salen esos dos dicts -- eso depende de D8.4
(`bucle_del_dia`, todavía sin construir): esta función solo necesita que
los dos tengan la forma exacta de `sesion.resolver_dia()` (`dx_puntos`,
`hedge_dolares`, `comision`, `muere`, `pausa`, `objetivo`, `barra_evento`).

PROHIBIDO (mismo principio que el resto de `bot/`): esto no decide nada --
no aplana, no alerta, no sube de nivel. Solo mide y devuelve el número;
`bot/seguridad.py` (o quien evalúe la banda de alerta, todavía sin decidir
-- ver `03_CONFIG.yaml → pendientes`, la banda es explícitamente una
decisión del operador) es quien reacciona."""
from bot import calendario, sesion


def calcula_residuo_dia(dia_teorico, dia_real):
    """Residuo de UN día, UNA cuenta: `hedge_dolares` real menos el
    teórico (positivo = el hedge ganó MÁS de lo que el modelo predecía;
    negativo = ganó menos -- p.ej. por deslizamiento/fricción reales
    peores que lo asumido). También compara `dx_puntos` (el residuo "en
    puntos", antes de convertir a dólares) y si `muere`/`objetivo`
    coincidieron -- una discrepancia en estos booleanos es MÁS grave que
    una simple diferencia de importe: significa que el día se resolvió
    por un camino de negocio distinto (p.ej. el modelo decía "sobrevive"
    y en la realidad murió), no solo que el precio de fill varió.

    Devuelve un dict con el residuo y un diagnóstico -- nunca decide si
    eso es "aceptable": la banda de alerta es una decisión del operador
    (10_SEGURIDAD.md §8), no un umbral que este módulo pueda inventar."""
    residuo_dx = dia_real['dx_puntos'] - dia_teorico['dx_puntos']
    residuo_hedge_usd = dia_real['hedge_dolares'] - dia_teorico['hedge_dolares']
    residuo_comision_usd = dia_real['comision'] - dia_teorico['comision']
    mismo_desenlace = (dia_real['muere'] == dia_teorico['muere']
                        and dia_real['pausa'] == dia_teorico['pausa']
                        and dia_real['objetivo'] == dia_teorico['objetivo'])
    return dict(
        residuo_dx_puntos=residuo_dx,
        residuo_hedge_usd=residuo_hedge_usd,
        residuo_comision_usd=residuo_comision_usd,
        residuo_total_usd=residuo_hedge_usd + residuo_comision_usd,
        mismo_desenlace=mismo_desenlace,
        desenlace_teorico=dict(muere=dia_teorico['muere'], pausa=dia_teorico['pausa'],
                                objetivo=dia_teorico['objetivo']),
        desenlace_real=dict(muere=dia_real['muere'], pausa=dia_real['pausa'],
                             objetivo=dia_real['objetivo']),
    )


def residuo_dia_desde_barras_reales(ph_crudo, pl_crudo, pc_crudo, direccion, barra_inicio,
                                     plan, m, fric, deslizamiento, dia_real):
    """D9 §3.6 (autorización R6, 22-08-2026): el reconstructor del 'teórico'
    para el camino EN VIVO -- decisión explícita del operador (no mía):
    **el oráculo offline reconstruido con las barras reales**, NUNCA
    `det_diagnostico` (el propio `DetectorEnVivo` del camino en vivo, que es
    justo lo que se está midiendo -- usarlo de referencia daría residuo
    CERO por construcción incluso con un fallo de ejecución real).

    "El oráculo offline" es, literalmente, `sesion.resolver_dia()` -- el
    MISMO núcleo R6 (frozen, 14 goldens) que usa el replay -- alimentado con
    `ph_crudo/pl_crudo/pc_crudo` (las barras QUE DE VERDAD SIRVIÓ
    `fuente_barras` ese día, capturadas por `bot/bucle_de_tiempo.py` antes
    de repartirlas a las máquinas) reflejadas exactamente como reflejaría
    un pack de replay (`calendario.refleja_camino`, misma función, cero
    reimplementación) y el `plan`/`m`/`fric`/`deslizamiento`/`barra_inicio`
    que de verdad se usó ESE intento -- nunca recalculados aparte.

    Esto es lo único de este módulo que deja de ser "sin importar nada del
    proyecto salvo lo que se le pasa" (`calcula_residuo_dia`/
    `acumula_residuos`, arriba, siguen siendo puras): reutiliza el núcleo
    R6 en vez de reimplementar su aritmética, que es justo lo que R6 exige.

    `dia_real` ya tiene la forma de `sesion.resolver_dia()` (es
    `MaquinaEnVivo.resultado`/`ResuelveDiaEnVivo` -- ver sus docstrings).
    Devuelve `calcula_residuo_dia(dia_teorico, dia_real)` con `dia_teorico`
    y `dia_real` añadidos, para que quien lo persista vea los dos lados,
    no solo la resta."""
    ph_r, pl_r, pc_r = calendario.refleja_camino(ph_crudo, pl_crudo, pc_crudo, direccion)
    dia_teorico = sesion.resolver_dia(ph=ph_r, pl=pl_r, pc=pc_r, barra_inicio=barra_inicio,
                                       plan_resultado=plan, m=m, fric=fric,
                                       deslizamiento=deslizamiento)
    residuo = calcula_residuo_dia(dia_teorico, dia_real)
    residuo['dia_teorico'] = dia_teorico
    residuo['dia_real'] = dia_real
    return residuo


def acumula_residuos(residuos_por_dia):
    """Agregación simple sobre una lista de `calcula_residuo_dia(...)` --
    la comparación de REVISION_REV5.md/ORDEN_DE_TRABAJO_D8.md §4 (pasada 2
    de la Puerta Grande): "el residuo diario acumulado ≈ deslizamiento ×
    muertes + fricción × operaciones". Este módulo NO conoce
    deslizamiento/fricción de config (eso violaría "sesion y sizing no
    importan nada salvo config" trasladado aquí: este módulo ni siquiera
    importa config) -- solo suma lo que ya se calculó, para que quien SÍ
    tiene esos números (D8.4, o el test de la Puerta Grande) compare."""
    n = len(residuos_por_dia)
    dias_con_desenlace_distinto = sum(1 for r in residuos_por_dia if not r['mismo_desenlace'])
    return dict(
        n_dias=n,
        residuo_total_usd_acumulado=sum(r['residuo_total_usd'] for r in residuos_por_dia),
        residuo_hedge_usd_acumulado=sum(r['residuo_hedge_usd'] for r in residuos_por_dia),
        residuo_comision_usd_acumulado=sum(r['residuo_comision_usd'] for r in residuos_por_dia),
        dias_con_desenlace_distinto=dias_con_desenlace_distinto,
    )
