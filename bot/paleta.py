# -*- coding: utf-8 -*-
"""paleta.py · D-C · 08_LABORATORIO.md §6.3

"Valida la paleta con un script, no a ojo -- separación suficiente para
daltonismo y contraste sobre la superficie oscura. Es computable, así que se
computa." Este módulo ES ese script: define la paleta fija del dashboard
(`bot/dashboard.py` la importa, no la reinventa) y la valida contra dos
criterios COMPUTABLES:

  1. **Contraste WCAG 2.x** de cada color de texto/icono contra el fondo
     sobre el que se pinta -- fórmula estándar (luminancia relativa
     linearizada), no una opinión. AA normal >= 4.5:1, AA texto grande/
     iconografía UI >= 3:1 (mismos umbrales que usa cualquier auditor de
     accesibilidad).
  2. **Separación de los 4 colores de estado** (bien/aviso/grave/crítico)
     para que una confusión roja-verde (la forma más común de daltonismo)
     no los colapse: se exige separación de matiz (hue) O de luminosidad
     entre cada par -- es la misma razón por la que la regla de estilo dice
     "nunca van solos: siempre con icono y con etiqueta" (§6.3): el color
     nunca es el único canal, pero aun así se computa la separación en vez
     de fiarse a ojo.

Lo que este script NO comprueba (dicho explícito en el propio
`DATOS_Y_DASHBOARD.md` §2.3): "el validador comprueba el color, no la
maquetación -- los solapes de etiquetas y los desbordes se ven mirando."
"""
import colorsys
import re


def _hex_a_rgb(hexcolor):
    hexcolor = hexcolor.lstrip('#')
    return tuple(int(hexcolor[i:i + 2], 16) for i in (0, 2, 4))


def _canal_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminancia_relativa(hexcolor):
    r, g, b = (_canal_linear(c) for c in _hex_a_rgb(hexcolor))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(hex_a, hex_b):
    """WCAG 2.x: (L1+0.05)/(L2+0.05), con L1 la mayor de las dos."""
    la, lb = luminancia_relativa(hex_a), luminancia_relativa(hex_b)
    l1, l2 = max(la, lb), min(la, lb)
    return (l1 + 0.05) / (l2 + 0.05)


def _hue_grados(hexcolor):
    r, g, b = (c / 255.0 for c in _hex_a_rgb(hexcolor))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360.0, l


# =============================================================================
# LA PALETA FIJA (08_LABORATORIO.md §6.3: "modo oscuro por defecto, paleta
# propia validada" -- NO es un tema claro invertido). bot/dashboard.py importa
# estos nombres, no los redefine.
# =============================================================================
FONDO = "#0b0e14"           # superficie oscura de base
SUPERFICIE = "#131826"      # tarjetas/bloques, un paso mas claro que el fondo
BORDE = "#232a3d"           # marcas finas / rejilla / ejes discretos (§6.3)
TEXTO = "#e7ebf3"           # texto principal
TEXTO_ATENUADO = "#8891a7"  # "un dato viejo tiene que parecer viejo" (§6.1) + tinta neutra de ejes
TEXTO_MUY_ATENUADO = "#565f78"

# colores de estado -- RESERVADOS, nunca reutilizados como "serie" (§6.3)
ESTADO = {
    "bien": "#33d17a",
    "aviso": "#e8b339",
    "grave": "#b83d16",
    "critico": "#f0555e",
}
# iconos textuales de acompañamiento obligatorio (§6.3: "nunca van solos")
ESTADO_ICONO = {"bien": "✓", "aviso": "△", "grave": "▲", "critico": "✕"}

# las pocas series/acentos que hacen falta (E1 vs las 4 lineas medidas, etc.)
ACENTO_1 = "#5aa9e6"   # serie primaria (p.ej. friccion_optimista)
ACENTO_2 = "#b98af0"   # serie secundaria (p.ej. friccion_realista)


def _pares_para_contraste():
    """(nombre, color_fg, color_fondo, umbral) -- los pares que de verdad se
    pintan en el dashboard: texto sobre FONDO/SUPERFICIE, y cada color de
    estado sobre FONDO/SUPERFICIE (se usan como icono+etiqueta, no como
    bloques grandes -- por eso el umbral de UI/texto grande, 3:1, no el de
    texto de párrafo, 4.5:1 -- salvo TEXTO, que sí es cuerpo de texto normal)."""
    pares = [
        ("texto principal / fondo", TEXTO, FONDO, 4.5),
        ("texto principal / superficie", TEXTO, SUPERFICIE, 4.5),
        ("texto atenuado / fondo", TEXTO_ATENUADO, FONDO, 3.0),
        ("texto atenuado / superficie", TEXTO_ATENUADO, SUPERFICIE, 3.0),
    ]
    for nombre, hexc in ESTADO.items():
        pares.append((f"estado.{nombre} / fondo", hexc, FONDO, 3.0))
        pares.append((f"estado.{nombre} / superficie", hexc, SUPERFICIE, 3.0))
    for nombre, hexc in (("acento_1", ACENTO_1), ("acento_2", ACENTO_2)):
        pares.append((f"{nombre} / fondo", hexc, FONDO, 3.0))
    return pares


def valida():
    """Devuelve (ok: bool, informe: list[str]). Cada línea del informe dice
    qué se comprobó y si pasó -- ver da1_diagnostico.ps1/romper_mi_*.py para
    el mismo estilo de salida-que-se-pega (R3)."""
    informe = []
    ok = True

    informe.append("--- 1. contraste WCAG (texto/icono contra el fondo sobre el que se pinta) ---")
    for nombre, fg, bg, umbral in _pares_para_contraste():
        c = contraste(fg, bg)
        paso = c >= umbral
        ok = ok and paso
        informe.append(f"  {'OK ' if paso else 'FALLO'} {nombre}: {c:.2f}:1 "
                        f"(umbral {umbral:.1f}:1) [{fg} sobre {bg}]")

    informe.append("--- 2. separacion de los 4 colores de estado (daltonismo rojo-verde) ---")
    nombres = list(ESTADO)
    SEP_HUE_MIN = 25.0   # grados; par de referencia bien/critico (verde/rojo) separa ~140
    SEP_LUM_MIN = 0.08   # luminosidad HLS, 0..1
    for i in range(len(nombres)):
        for j in range(i + 1, len(nombres)):
            a, b = nombres[i], nombres[j]
            ha, la = _hue_grados(ESTADO[a])
            hb, lb = _hue_grados(ESTADO[b])
            dhue = min(abs(ha - hb), 360 - abs(ha - hb))
            dlum = abs(la - lb)
            paso = (dhue >= SEP_HUE_MIN) or (dlum >= SEP_LUM_MIN)
            ok = ok and paso
            informe.append(f"  {'OK ' if paso else 'FALLO'} {a} vs {b}: "
                            f"Δhue={dhue:.1f}° Δlum={dlum:.3f} "
                            f"(pasa si Δhue>={SEP_HUE_MIN}° o Δlum>={SEP_LUM_MIN})")

    informe.append("--- lo que este script NO comprueba (DATOS_Y_DASHBOARD.md §2.3, dicho explícito) ---")
    informe.append("  maquetación: solapes de etiquetas y desbordes -- eso se ve mirando el HTML.")

    return ok, informe


if __name__ == '__main__':
    import sys
    ok, informe = valida()
    print("\n".join(informe))
    print()
    print("PALETA OK" if ok else "PALETA CON FALLOS -- ver arriba")
    sys.exit(0 if ok else 1)
