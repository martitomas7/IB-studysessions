# -*- coding: utf-8 -*-
"""fuente_barras.py · D8.4 · ORDEN_DE_TRABAJO_D8.md §0 · diseño grounded

"El bucle del día tiene que ser UNO SOLO, con la fuente de barras como
puerto." Este módulo define ese puerto -- solo se ocupa de barras, nunca
decide dirección/ventana/resets (mismo principio que `calendario.py`: "el
acto de tirar la moneda vive en el llamador").

`FuenteDeReplay` reproduce un pack de replay -- lo que hace posible que la
Puerta Grande (ORDEN_DE_TRABAJO_D8.md §4) compare `bot/bucle_del_dia.py`
contra `bot/orquestador.py::corre_replay()` sobre los mismos 504 días.

`FuenteEnVivo` (lectura de barras reales) queda con un hueco documentado:
necesita un método del adaptador que HOY no existe en `07_ADAPTADOR_NT8.md`
§1 (la tabla solo lista `Bid`/`Ask`/`Last`/`MarketData`, ninguna operación
"dame la última barra de N minutos cerrada"). Es una ampliación real de
ese documento, igual que `coloca_bracket` se añadió en su revisión 5 --
decisión del operador, no inventada aquí."""
from collections import namedtuple
from dataclasses import dataclass

Barra = namedtuple('Barra', ['b', 'ph', 'pl', 'pc', 'es_ultima_barra_operable'])


@dataclass
class ContextoDia:
    """Lo que `abre_dia()` decide para el día que empieza. `direccion=None`
    es la señal de que esta fuente NO fuerza nada -- quien llama
    (`bot/bucle_del_dia.py`) sortea de verdad (dirección, ventana, resets)
    y refleja el camino él mismo, exactamente como hace
    `orquestador.py::procesa_dia_replay` con los valores forzados del
    pack."""
    direccion: object = None
    ventana_txt: object = None
    b0v: object = None
    n_resets_hoy: object = None
    ph: object = None   # crudo (sin reflejar) -- solo relevante si direccion no es None
    pl: object = None
    pc: object = None


class FuenteDeReplay:
    """Sirve un pack de replay, un día detrás de otro, forzando TODO
    (dirección/ventana/b0v/resets/barras crudas) desde `pack_dias`
    (`replay_v10.json['dias']`) -- mismo contrato de datos que ya usa
    `orquestador.py::procesa_dia_replay`."""

    def __init__(self, pack_dias):
        self._dias = list(pack_dias)
        self._i = -1          # índice del día actual, -1 = antes de abrir_dia()
        self._b = -1          # índice de barra dentro del día actual

    def dia_disponible(self):
        return (self._i + 1) < len(self._dias)

    def abre_dia(self):
        self._i += 1
        self._b = -1
        dia = self._dias[self._i]
        return ContextoDia(
            direccion=dia["direccion"], ventana_txt=dia["ventana"],
            b0v=None,   # lo calcula el llamador desde ventana_txt (b0_rth de config), igual que hoy
            n_resets_hoy=dia["eventos"]["resets"],
            ph=dia["barras"]["ph"], pl=dia["barras"]["pl"], pc=dia["barras"]["pc"],
        )

    def siguiente_barra(self):
        dia = self._dias[self._i]
        ph, pl, pc = dia["barras"]["ph"], dia["barras"]["pl"], dia["barras"]["pc"]
        self._b += 1
        if self._b >= len(pc):
            return None
        return Barra(b=self._b, ph=ph[self._b], pl=pl[self._b], pc=pc[self._b],
                     es_ultima_barra_operable=(self._b == len(pc) - 1))

    def cierra_dia(self):
        pass   # nada que liberar -- el array vive en memoria, servido por índice


class FuenteEnVivo:
    """HUECO DOCUMENTADO (diseño D8.4, §5 de la síntesis): `lector_barras`
    necesita un método del adaptador/feed que hoy NO existe en
    `07_ADAPTADOR_NT8.md` §1 -- "dame la última barra de
    `sesion.minutos_por_barra` minutos cerrada". Esta clase queda con el
    esqueleto de su ciclo de vida (mismo puerto que `FuenteDeReplay`) pero
    `siguiente_barra()` lanza `NotImplementedError` hasta que ese método
    del puerto se decida y se documente -- NUNCA se inventa aquí (R2/R7:
    un puerto a medio especificar es peor que uno que falla ruidoso)."""

    def __init__(self, lector_barras, reloj=None, dormir=None):
        import time
        self._lector_barras = lector_barras
        self._reloj = reloj or time.monotonic
        self._dormir = dormir or time.sleep

    def dia_disponible(self):
        raise NotImplementedError(
            "FuenteEnVivo.dia_disponible() depende de un calendario de mercado real "
            "(festivos, medio-días) -- no está en el alcance grounded de este diseño, "
            "es una decisión del operador (ver §5 de la síntesis de D8.4)")

    def abre_dia(self):
        return ContextoDia()   # direccion=None -> el llamador sortea de verdad

    def siguiente_barra(self):
        raise NotImplementedError(
            "FuenteEnVivo.siguiente_barra() depende de una operación del puerto de "
            "07_ADAPTADOR_NT8.md §1 que hoy no existe (\"dame la última barra cerrada\") "
            "-- ampliación real del documento, decisión del operador, no inventada aquí")

    def cierra_dia(self):
        pass
