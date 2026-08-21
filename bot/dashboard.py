# -*- coding: utf-8 -*-
"""dashboard.py · D-C · 05_ORDEN_DE_CONSTRUCCION.md · 08_LABORATORIO.md §6

Genera el dashboard operativo: un único HTML autocontenido (CSS embebido,
sin JS de terceros, sin CDN, sin red) a partir de un `ctx` ya construido por
`bot/contexto_dashboard.py` -- este módulo NO lee ficheros ni decide nada:
solo pinta lo que `ctx` ya trae, tal como exige §6.1 ("se genera desde los
ficheros del laboratorio y el diario del orquestador, sin inventar ninguna
fuente nueva" -- la separación entre "reunir los datos" y "pintarlos" es la
misma que ya usa el resto del bot entre `ciclo_vida.py` y `sesion.py`).

Los ocho bloques de §6.2, las reglas de estilo de §6.3 (oscuro por defecto,
monoespaciada, sin adorno, colores de estado reservados con icono+etiqueta,
paleta de `bot/paleta.py`) y el párrafo de §0 siempre visible.
"""
import html as _html

from bot import paleta as P

UMBRAL_SPR = (3.00, 4.10, 4.50, 4.75)  # 08_LABORATORIO.md §3/§6.2, ya medidas


def _esc(x):
    return _html.escape(str(x), quote=True)


def _num(x, decimales=2, unidad=""):
    if x is None:
        return '<span class="atenuado">—</span>'
    try:
        s = f"{x:,.{decimales}f}".replace(",", " ")  # espacio fino como separador de miles
    except (TypeError, ValueError):
        return _esc(x)
    return f'{s}{(" " + unidad) if unidad else ""}'


def _semaforo(estado, texto=None):
    """§6.3: 'nunca van solos: siempre con icono y con etiqueta'."""
    estado = estado if estado in P.ESTADO else 'aviso'
    icono = P.ESTADO_ICONO[estado]
    etiqueta = texto if texto is not None else estado.upper()
    return (f'<span class="semaforo semaforo-{estado}">'
            f'<span class="semaforo-icono">{icono}</span> {_esc(etiqueta)}</span>')


def _frescura(ts_monotono, ahora_monotono, rancio_seg):
    """§6.1: 'un dato viejo tiene que parecer viejo' -- devuelve (clase_css, texto)."""
    if ts_monotono is None:
        return "no-disponible", "no disponible"
    edad = max(0.0, ahora_monotono - ts_monotono)
    if edad > rancio_seg:
        return "rancio", f"rancio · hace {edad:.0f} s"
    return "vivo", f"vivo · hace {edad:.1f} s"


def _tabla(filas, cabeceras, clase=""):
    th = "".join(f"<th>{_esc(c)}</th>" for c in cabeceras)
    trs = []
    for fila in filas:
        tds = "".join(f"<td>{c}</td>" for c in fila)
        trs.append(f"<tr>{tds}</tr>")
    tabla = f'<table class="tabla {clase}"><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table>'
    return f'<div class="tabla-scroll">{tabla}</div>'


def _bloque_ahora(ctx):
    a = ctx['ahora']
    conexiones = "".join(
        f'<div class="fila-conexion">'
        f'<span>{_esc(c["nombre"])}</span>'
        f'<span>{_semaforo("bien" if c["hay_conexion"] else "critico", "conectado" if c["hay_conexion"] else "caída")}</span>'
        f'<span class="atenuado">feed: {_esc(c["estado_feed"])}</span></div>'
        for c in a['conexiones']
    )
    patas = "".join(
        f'<div class="fila-pata"><span>{_esc(p["cuenta"])}</span>'
        f'<span class="num">{_esc(p["tipo"])}={_num(p["cantidad"], 0)}</span></div>'
        for p in a['patas']
    ) or '<div class="atenuado">sin patas abiertas</div>'
    # DECISION_DEGRADACION_N3.md §3/§5 (test 5): la causa tipada de la
    # escalera N0-N4 se pinta -- nunca solo el nivel a secas, siempre con
    # la causa y el motivo que la acompañan (mismo principio de §6.3: "los
    # colores de estado nunca van solos").
    c = a.get('contencion', {'nivel': 'N0', 'nombre': 'NORMAL', 'causa': None, 'motivo': None})
    nivel_estado = ('bien' if c['nivel'] == 'N0'
                    else ('critico' if c['nivel'] in ('N3', 'N4') else 'grave'))
    etiqueta_nivel = f"{c['nivel']} · {c['nombre']}"
    detalle_nivel = (f'<div class="atenuado">causa: {_esc(c["causa"])}'
                      + (f' — {_esc(c["motivo"])}' if c.get('motivo') else '') + '</div>'
                      if c.get('causa') else '')
    return f'''
    <section class="bloque" id="bloque-ahora">
      <h2>1 · AHORA</h2>
      <div class="grid-ahora">
        <div><span class="etiqueta">Dirección</span><span class="valor num">{'+1' if a['direccion']==1 else '-1'}</span></div>
        <div><span class="etiqueta">Ventana</span><span class="valor">{_esc(a['ventana'])}</span></div>
        <div><span class="etiqueta">Barra actual</span><span class="valor num">{_num(a['barra_actual'],0)}</span></div>
        <div><span class="etiqueta">Semáforo global</span><span class="valor">{_semaforo(a['semaforo_global'])}</span></div>
        <div><span class="etiqueta">Nivel de contención</span><span class="valor">{_semaforo(nivel_estado, etiqueta_nivel)}</span>{detalle_nivel}</div>
      </div>
      <div class="subseccion"><h3>Patas abiertas</h3>{patas}</div>
      <div class="subseccion"><h3>Conexiones</h3>{conexiones}</div>
    </section>'''


def _bloque_riesgo(ctx):
    r = ctx['riesgo']
    estado = 'critico' if r['degradado'] else ('grave' if r['distancia_degradacion'] < r.get('umbral_grave', 0) else 'bien')
    return f'''
    <section class="bloque bloque-riesgo" id="bloque-riesgo">
      <h2>2 · RIESGO</h2>
      <div class="riesgo-grande">
        <span class="etiqueta">Distancia a la degradación</span>
        <span class="valor-enorme num">{_num(r['distancia_degradacion'],2,'USD')}</span>
        {_semaforo(estado, 'DEGRADADO' if r['degradado'] else None)}
      </div>
      <div class="grid-riesgo">
        <div><span class="etiqueta">Caja</span><span class="valor num">{_num(r['caja'],2,'USD')}</span></div>
        <div><span class="etiqueta">Retirado</span><span class="valor num">{_num(r['retirado'],2,'USD')}</span></div>
        <div><span class="etiqueta">Tesorería viva</span><span class="valor num">{_num(r['caja']-r['retirado'],2,'USD')}</span></div>
        <div><span class="etiqueta">Muro dinámico</span><span class="valor num">{_num(r['muro'],2,'USD')}</span></div>
      </div>
    </section>'''


def _bloque_pendientes(ctx):
    # DOS RELOJES DISTINTOS (03_CONFIG.yaml §10, RECOMENDACIÓN 3 / revisión del
    # operador 20-08-2026): "5 días" (reloj del BOT, escalada de la alerta a un
    # canal más ruidoso) y "~7 días" (reloj del PROVEEDOR, MyFundedFutures mata
    # la cuenta por inactividad) NO son la misma cifra -- son dos relojes
    # separados sobre el mismo evento de origen ("lleva bloqueada N días"), y
    # se pintan como dos columnas distintas, nunca fundidas en una. La columna
    # del proveedor lleva su propio semáforo: "crítico" cuando quedan 0 días
    # o menos (SUPUESTO -- 01_ESPECIFICACION_E2E.md R-2.4 lo cita con
    # virgulilla, no es una cifra DADA como la del bot).
    items = ctx['pendientes']
    if not items:
        return '''<section class="bloque" id="bloque-pendientes"><h2>3 · PENDIENTES DEL HUMANO</h2>
        <div class="atenuado">nada pendiente</div></section>'''
    filas = []
    for it in items:
        estado = 'critico' if it.get('dias_esperando', 0) >= it.get('umbral_escalada_dias', 5) else 'aviso'
        columnas = [_esc(it['tipo']), _esc(it['detalle']),
                    f'<span class="num">{_num(it.get("dias_esperando"), 0)}</span>', _semaforo(estado)]
        if 'dias_hasta_proveedor_mata' in it:
            restantes = it['dias_hasta_proveedor_mata']
            estado_prov = 'critico' if restantes <= 0 else ('grave' if restantes <= 2 else 'aviso')
            columnas.append(
                f'<span class="num">≈{_num(restantes, 0)}</span> {_semaforo(estado_prov)}'
            )
        else:
            columnas.append('—')
        filas.append(tuple(columnas))
    # `bloque-ancho`: con las dos columnas de reloj (revisión 4) la tabla ya
    # no cabe cómoda en el tercio de rejilla que ocupaba antes -- igual que
    # `bloque-riesgo`, pasa a ancho completo para no depender del scroll
    # horizontal en el caso común.
    return f'''<section class="bloque bloque-ancho" id="bloque-pendientes"><h2>3 · PENDIENTES DEL HUMANO</h2>
    {_tabla(filas, ['tipo', 'detalle', 'días bloqueada (reloj bot)', 'estado', 'días hasta que el proveedor la mate (≈, reloj proveedor)'])}</section>'''


def _bloque_cuentas(ctx):
    c = ctx['cuentas']
    ev, fu, rec, pool = c['eval'], c['funded'], c['recamara'], c['pool']
    filas_eval = [(k, f'<span class="num">{_num(v, 2 if isinstance(v, float) else 0)}</span>')
                  for k, v in ev.items() if k != 'activa']
    filas_fu = [(k, f'<span class="num">{_num(v, 2 if isinstance(v, float) else 0)}</span>')
                for k, v in fu.items() if k != 'activa']
    filas_dormidas = [(f'#{i+1}', f'<span class="num">{_num(d["s0"], 2, "USD")}</span>',
                        f'<span class="num">{_num(d["desde_dia"], 0)}</span>')
                       for i, d in enumerate(rec['dormidas'])] or [('—', '—', '—')]
    return f'''
    <section class="bloque" id="bloque-cuentas"><h2>4 · CUENTAS</h2>
      <div class="subseccion"><h3>Eval {_semaforo('bien' if ev['activa'] else 'aviso', 'activa' if ev['activa'] else 'vacía')}
        {_semaforo('critico','BLOQUEADA') if ev.get('bloqueada') else ''}</h3>
        {_tabla(filas_eval, ['campo', 'valor'])}</div>
      <div class="subseccion"><h3>Fondeada {_semaforo('bien' if fu['activa'] else 'aviso', ('fase %d' % fu['fase']) if fu['activa'] else 'inactiva')}</h3>
        {_tabla(filas_fu, ['campo', 'valor'])}</div>
      <div class="subseccion"><h3>Recámara ({_num(rec['n'],0)} dormidas, sunk_total {_num(rec['sunk_total'],2,'USD')})</h3>
        {_tabla(filas_dormidas, ['dormida', 's₀ propio', 'desde día'])}</div>
      <div class="subseccion"><h3>Pool</h3>
        <span class="num">frescas={_num(pool['frescas'],0)}</span>
        &nbsp;<span class="num">rotas={_num(pool['rotas'],0)}</span></div>
    </section>'''


def _bloque_mercado(ctx):
    m = ctx['mercado_friccion']
    if not m['disponible']:
        return f'''<section class="bloque" id="bloque-mercado"><h2>5 · MERCADO Y FRICCIÓN</h2>
        <div class="no-disponible-grande">E1 no disponible — {_esc(m.get("motivo_no_disponible", "feed retrasado"))}</div>
        </section>'''
    rancio_seg = ctx.get('rancio_seg', 30.0)
    clase_fresc, texto_fresc = _frescura(m.get('ts_monotono'), ctx.get('ahora_monotono', 0.0), rancio_seg)
    badge_frescura = f'<span class="frescura frescura-{clase_fresc}">{_esc(texto_fresc)}</span>'
    barras = []
    ancho_max = max(UMBRAL_SPR[-1], m['friccion_realista'], m['friccion_optimista']) * 1.1
    for etiqueta, valor, color in (("optimista", m['friccion_optimista'], P.ACENTO_1),
                                    ("realista", m['friccion_realista'], P.ACENTO_2)):
        pct = min(100.0, 100.0 * valor / ancho_max)
        barras.append(f'<div class="barra-fila"><span class="barra-etq">{etiqueta}</span>'
                       f'<div class="barra-pista"><div class="barra-rellena" '
                       f'style="width:{pct:.1f}%;background:{color}"></div></div>'
                       f'<span class="num">{_num(valor,2,"$/micro")}</span></div>')
    marcas = "".join(
        f'<div class="marca-linea" style="left:{100.0*v/ancho_max:.1f}%" title="{v}">'
        f'<span class="marca-etq">{v:.2f}</span></div>' for v in UMBRAL_SPR)
    return f'''
    <section class="bloque" id="bloque-mercado"><h2>5 · MERCADO Y FRICCIÓN</h2>
      <div class="subseccion"><h3>Horquilla actual {badge_frescura}</h3>
        <span class="num">{_num(m['horquilla_actual'],2,'USD/micro')}</span></div>
      <div class="subseccion"><h3>Proyecciones de fricción vs. líneas medidas (3,00 · 4,10 · 4,50 · 4,75)</h3>
        <div class="barras-container">{"".join(barras)}<div class="marcas-container">{marcas}</div></div>
        {_tabla([('optimista', _num(m['friccion_optimista'],2)), ('realista', _num(m['friccion_realista'],2))],
                ['proyección', 'valor ($/micro)'])}
      </div>
    </section>'''


def _bloque_modelo_vs_realidad(ctx):
    filas = []
    for f in ctx['modelo_vs_realidad']:
        estado = 'bien' if f['concluye'] else 'aviso'
        texto = 'concluye' if f['concluye'] else 'todavía no concluye'
        filas.append((_esc(f['evento']), _num(f['tasa_observada'],3), _num(f['n'],0),
                       _num(f['tasa_esperada'],3), _num(f.get('sd'),3), _semaforo(estado, texto)))
    return f'''<section class="bloque bloque-ancho" id="bloque-modelo"><h2>6 · MODELO vs REALIDAD</h2>
    {_tabla(filas, ['evento', 'observado/mes', 'n', 'esperado/mes', 'sd', 'estado'])}
    </section>'''


def _bloque_laboratorio(ctx):
    filas = []
    for e in ctx['laboratorio']:
        pct = min(100.0, 100.0 * e['n'] / max(e['n_minimo'], 1)) if e.get('n_minimo') else None
        progreso = f'{_num(pct,0)}%' if pct is not None else '—'
        filas.append((e['nombre'], _num(e.get('n'),0), _esc(e.get('intervalo','—')),
                       _esc(e['estado']), progreso))
    return f'''<section class="bloque bloque-ancho" id="bloque-laboratorio"><h2>7 · LABORATORIO</h2>
    {_tabla(filas, ['estimador', 'n', 'intervalo', 'estado', 'progreso hacia n mínimo'])}
    </section>'''


def _bloque_incidencias(ctx):
    # BUG real cazado en R3 (Task 22, prueba_lector_laboratorio.py, comprobación
    # end-to-end disco->contexto_dashboard->genera_html): este bloque leía
    # i['ts'], pero el campo que 08_LABORATORIO.md §1.4 define para una
    # incidencia es 'ts_pared' -- nunca se había ejercitado con datos de
    # forma real (prueba_dashboard.py no pasaba incidencias_recientes con
    # esa forma), así que el KeyError quedaba sin cazar. Corregido.
    inc = ctx['incidencias']
    filas = [(_esc(i['ts_pared']), _esc(i['tipo']), _esc(i['detalle'])) for i in inc['ultimas']] or [('—', '—', '—')]
    contadores = " · ".join(f'{_esc(k)}={_num(v,0)}' for k, v in inc['contadores'].items()) or "sin incidencias"
    return f'''<section class="bloque" id="bloque-incidencias"><h2>8 · INCIDENCIAS</h2>
    <div class="atenuado">{contadores}</div>
    {_tabla(filas, ['hora', 'tipo', 'detalle'])}
    </section>'''


def _bloque_desviaciones(ctx):
    dv = ctx.get('desviaciones_activas', [])
    if not dv:
        return ''
    filas = [(_esc(d['palanca']), _esc(d['quien']), _esc(d['desde_dia']), _esc(d['hasta_dia']),
               _num(d.get('coste_ev_usd_mes'), 1)) for d in dv]
    return f'''<section class="bloque bloque-desviaciones" id="bloque-desviaciones">
    <h2>⚠ DESVIACIONES DE CLASE B ACTIVAS</h2>
    {_tabla(filas, ['palanca', 'quién', 'desde día', 'hasta día', 'coste EV $/mes'])}
    </section>'''


def genera_html(ctx):
    """Devuelve el documento HTML completo, autocontenido, del dashboard."""
    ok_paleta, _ = P.valida()
    bloques = [
        _bloque_desviaciones(ctx),
        _bloque_ahora(ctx),
        _bloque_riesgo(ctx),
        _bloque_pendientes(ctx),
        _bloque_cuentas(ctx),
        _bloque_mercado(ctx),
        _bloque_modelo_vs_realidad(ctx),
        _bloque_laboratorio(ctx),
        _bloque_incidencias(ctx),
    ]
    return f'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Dashboard operativo · circuito cubierto v10</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{
  --fondo: {P.FONDO}; --superficie: {P.SUPERFICIE}; --borde: {P.BORDE};
  --texto: {P.TEXTO}; --atenuado: {P.TEXTO_ATENUADO}; --muy-atenuado: {P.TEXTO_MUY_ATENUADO};
  --bien: {P.ESTADO['bien']}; --aviso: {P.ESTADO['aviso']};
  --grave: {P.ESTADO['grave']}; --critico: {P.ESTADO['critico']};
  --acento1: {P.ACENTO_1}; --acento2: {P.ACENTO_2};
}}
* {{ box-sizing: border-box; }}
body {{
  background: var(--fondo); color: var(--texto); margin: 0; padding: 16px;
  font-family: ui-monospace, "SF Mono", "Cascadia Mono", "JetBrains Mono", Consolas, monospace;
  font-size: 13px; line-height: 1.5;
}}
.num {{ font-variant-numeric: tabular-nums; text-align: right; display: inline-block; min-width: 2ch; }}
.cabecera {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:12px;
  border-bottom:1px solid var(--borde); padding-bottom:8px; flex-wrap: wrap; gap: 8px;}}
.cabecera h1 {{ font-size: 15px; margin:0; font-weight:600; }}
.atenuado {{ color: var(--atenuado); }}
.parrafo-limite {{ background: var(--superficie); border:1px solid var(--borde); border-left:3px solid var(--aviso);
  padding:10px 12px; margin-bottom:14px; font-size:12px; color: var(--texto); }}
.rejilla {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap:12px; }}
.bloque {{ background: var(--superficie); border:1px solid var(--borde); border-radius:4px; padding:12px 14px;
  min-width:0; overflow:hidden; }}
.bloque h2 {{ font-size:12px; letter-spacing:.04em; margin:0 0 10px 0; color: var(--atenuado); font-weight:700; }}
.bloque h3 {{ font-size:11.5px; margin:10px 0 6px; color: var(--atenuado); font-weight:600; }}
.subseccion {{ margin-top:6px; }}
.bloque-riesgo, .bloque-ancho {{ grid-column: 1 / -1; }}
.riesgo-grande {{ display:flex; align-items:baseline; gap:14px; margin-bottom:10px; flex-wrap:wrap; }}
.valor-enorme {{ font-size:34px; font-weight:700; }}
.grid-ahora, .grid-riesgo {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap:8px; margin-bottom:8px; }}
.grid-ahora > div, .grid-riesgo > div {{ display:flex; flex-direction:column; gap:2px; }}
.etiqueta {{ color: var(--atenuado); font-size:11px; }}
.valor {{ font-size:16px; }}
table.tabla {{ width:100%; border-collapse:collapse; font-size:12px; }}
table.tabla th {{ text-align:left; color: var(--atenuado); font-weight:600; border-bottom:1px solid var(--borde);
  padding:4px 10px 4px 6px; white-space:nowrap; }}
table.tabla td {{ padding:4px 10px 4px 6px; border-bottom:1px solid var(--borde); white-space:nowrap; }}
table.tabla tbody tr:last-child td {{ border-bottom:none; }}
.semaforo {{ display:inline-flex; align-items:center; gap:4px; padding:1px 6px; border-radius:3px;
  font-size:11px; font-weight:700; white-space:nowrap; }}
.tabla-scroll {{ overflow-x:auto; max-width:100%; }}
.semaforo-bien {{ color: var(--bien); background: color-mix(in srgb, var(--bien) 14%, transparent); }}
.semaforo-aviso {{ color: var(--aviso); background: color-mix(in srgb, var(--aviso) 14%, transparent); }}
.semaforo-grave {{ color: var(--grave); background: color-mix(in srgb, var(--grave) 14%, transparent); }}
.semaforo-critico {{ color: var(--critico); background: color-mix(in srgb, var(--critico) 14%, transparent); }}
.fila-conexion, .fila-pata {{ display:flex; gap:10px; align-items:center; padding:2px 0; }}
.no-disponible-grande {{ color: var(--atenuado); font-style:italic; padding:20px 0; text-align:center; }}
.frescura {{ font-size:10px; font-weight:600; padding:1px 5px; border-radius:3px; margin-left:6px; }}
.frescura-vivo {{ color: var(--bien); background: color-mix(in srgb, var(--bien) 14%, transparent); }}
.frescura-rancio {{ color: var(--aviso); background: color-mix(in srgb, var(--aviso) 14%, transparent); }}
.frescura-no-disponible {{ color: var(--muy-atenuado); background: transparent; }}
.barras-container {{ position:relative; margin:10px 0 26px; }}
.barra-fila {{ display:grid; grid-template-columns: 70px 1fr 110px; align-items:center; gap:8px; margin:4px 0; }}
.barra-etq {{ color:var(--atenuado); font-size:11px; }}
.barra-pista {{ background: var(--fondo); border:1px solid var(--borde); height:14px; position:relative; }}
.barra-rellena {{ height:100%; }}
.marcas-container {{ position:relative; height:14px; margin-left:78px; margin-right:110px; }}
.marca-linea {{ position:absolute; top:0; border-left:1px dashed var(--muy-atenuado); height:100%; }}
.marca-etq {{ position:absolute; top:2px; left:2px; font-size:9px; color:var(--muy-atenuado); }}
.bloque-desviaciones {{ grid-column: 1 / -1; border-color: var(--aviso); }}
.bloque-desviaciones h2 {{ color: var(--aviso); }}
.pie {{ margin-top:16px; color: var(--muy-atenuado); font-size:10.5px; text-align:center; }}
@media (prefers-color-scheme: light) {{
  /* Regla explícita de 08_LABORATORIO.md §6.3: "modo oscuro por defecto ...
     no un modo claro invertido automáticamente" -- no se define un tema
     claro: el dashboard se queda oscuro sí o sí. */
}}
</style>
</head>
<body>
  <div class="cabecera">
    <h1>Dashboard operativo · circuito cubierto v10</h1>
    <span class="atenuado">generado {_esc(ctx.get('generado_ts','—'))}
      {'· <span style="color:var(--critico)">paleta con fallos, ver bot/paleta.py</span>' if not ok_paleta else ''}</span>
  </div>
  <div class="parrafo-limite">
    <strong>El papel puede medir la mecánica del circuito y dar una cota inferior de la fricción del
    mercado. NO puede medir la fricción real del hedge (<code>spr_usd</code>) ni el deslizamiento real
    por muerte (<code>slip_usd_micro</code>) — esos dos solo salen de la Fase 3.1, con dinero real.
    Cualquier cifra de este dashboard que diga "fricción confirmada" o "deslizamiento confirmado" está
    mal.</strong> (08_LABORATORIO.md §0)
  </div>
  <div class="rejilla">
    {"".join(bloques)}
  </div>
  <div class="pie">Generado por bot/dashboard.py — HTML autocontenido, sin servidor, sin red.
  No decide nada por su cuenta: muestra, avisa, y ejecuta lo que el operador le pide explícitamente
  (08_LABORATORIO.md §7).</div>
</body>
</html>'''
