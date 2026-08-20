# Revisión de la revisión 5 · qué está hecho, qué falta, y qué añadiría

**Reproduje todas las puertas yo mismo, desde el zip.** Todas verdes:

```
config OK · 14/14 goldens · discriminación OK · núcleo↔motor 0/60.000
orquestador real vs pack:  504 días · 0 fallos · caja final 29.134,87 $
romper_mi_orquestador 5/5 · protocolo 40/40 · comandos 15/15 · dashboard 14/14
kill -9  10/10 · demostraciones de los tres defectos: corregidos
integración fuera de proceso: 83/83 en nueve suites
```

**El `simulador_nt8/` es la mejor decisión de esta entrega.** Un simulador en proceso aparte,
con protocolo de socket real, permite probar el protocolo de las dos patas, el vigía de conexión
y la reconciliación **matando procesos de verdad** y con timeouts de reloj de pared. Eso no se
podía hacer con el adaptador falso en memoria. Y haberlo sometido después a revisión adversarial
—ocho hallazgos, incluida una carrera reproducida de forma determinista— es exactamente el
método que este proyecto lleva usando.

---

## 1 · Lo que falta, y es una sola cosa: **D8 no existe**

La entrega lo dice sin esconderlo (`arnes_bot_minimo.py`: *"ESTO NO ES D8"*), pero conviene ver
exactamente **qué** falta, porque es más pequeño de lo que parece.

**El problema, concreto.** `bot/sesion.py::resolver_dia(ph, pl, pc, ...)` y
`ciclo_vida.procesa_dia_*` reciben **las barras del día entero** y resuelven el día de golpe. En
papel eso no existe: las barras llegan de una en una. **Falta la pieza que consume barras en vivo
y produce el mismo resultado.**

**Lo he construido para comprobar que el hueco es de cableado y no de diseño.** Un detector
incremental de 30 líneas —suelo primero (R-3.3, el suelo gana el empate), objetivo después,
campana si no dispara nada— y lo validé contra el resolutor offline como oráculo:

```
días del replay: 504 · estados comparados: 1.512
discrepancias detector-en-vivo vs resolver_dia (oráculo): 0
RESULTADO: IDENTICOS
```

Te adjunto el script (`prueba_detector_en_vivo.py`). Dos conclusiones:

1. **El hueco se cierra barato.** No hay nada que rediseñar.
2. **Y trae su propio oráculo gratis.** `resolver_dia` es la referencia perfecta para D8: se le
   dan las mismas barras al detector en vivo, incrementalmente, y se exige resultado idéntico.
   **Es un test de tipo golden que no necesita NT8 ni papel.** Debería ser la puerta de D8.

### El requisito de D8 que NO se ve en el modelo y hay que decir en voz alta

> **Las salidas tienen que ser órdenes en reposo colocadas al abrir, no reacciones al cierre de
> la barra.**

El modelo asume que se sale **exactamente** en `−ndn` o `+nu`. Si D8 detecta el toque al cierre
de la barra y manda una orden a mercado, el fill es el cierre de esa barra, no el nivel — y toda
la identidad de cobertura se desplaza en una cantidad que no está en ningún sitio del modelo.

Así que al abrir hay que dejar puestas: **stop en el suelo, límite en el objetivo**, y usar el
detector para *saber qué pasó*, no para *decidir salir*. Son dos funciones distintas y las dos
hacen falta.

### Lo otro que falta, menor

- **El laboratorio no lee ficheros.** `contexto_dashboard.construye()` recibe `historial_diario`
  en memoria; no hay lector de los `.jsonl` que escribirá el indicador. Ya estaba anotado
  (recomendación 4.3) y sigue abierto.
- `da1_diagnostico.ps1`, `watchdog_bot.ps1` e `IndicadorLaboratorioMercado.cs` siguen sin
  verificar contra Windows/NT8. Bloqueado por falta de máquina, no por falta de trabajo.

---

## 2 · ¿Funciona la fase paper con todo?

**Todas las piezas están construidas y verificadas. Lo que no existe es el día que las une.**

| pieza | estado |
|---|---|
| cargar estado, validar invariantes | ✅ |
| dirección + CONTRA + ventana | ✅ |
| sizing por cuenta | ✅ |
| abrir las dos patas, con sus tres defectos corregidos | ✅ |
| **detectar el evento intradía y salir** | ❌ **D8** |
| cerrar las dos patas | ✅ |
| ciclo de vida, tesorería, persistencia | ✅ (validado 504 días) |
| laboratorio | ⚠️ estimadores sí, lector de ficheros no |
| dashboard | ✅ |
| watchdog, arranque, permisos | ✅ documentado, sin verificar en Windows |

Con el detector de arriba cableado, un día de papel completo es ensamblaje, no diseño. **Yo
diría que estás a un delta de tener la fase paper corriendo.**

---

## 3 · Multicuenta con Topstep: **todavía no, y el motivo no son las cuentas**

La buena noticia es que la arquitectura ya aguanta: `config.cargar(ruta)` y
`estado.cargar/guardar(ruta)` **ya son parametrizables por ruta**. Un circuito más no es
reescribir el núcleo: es **otro proceso con otro fichero de config y otro `estado.json`**. Eso
fue una buena decisión de diseño y se sostiene.

**Pero hay un bloqueo real que no es el que esperábamos: la tesorería es por circuito.**

`tesoreria.muro_dinamico()` calcula el muro contra `capital_usd` — **el capital entero**. Cinco
procesos independientes, cada uno leyendo el mismo capital, **cada uno se creería dueño de todo el
colchón**. Los cinco permitirían el drawdown completo y juntos podrían perder cinco veces lo que
el modelo cree que está en riesgo. La degradación se declararía tarde, o no se declararía.

Antes de la multicuenta hace falta **una vista de tesorería compartida**: o un capital asignado
por circuito (simple, conservador, y ya está tabulado — 7.000 $ por circuito en Topstep), o un
proceso que agregue y frene. **Lo primero es lo correcto para empezar: capital dedicado por
circuito, sin fondo común.**

**Mi recomendación de secuencia:**

1. **Ahora, gratis:** dejar el arranque del bot con `--config` y `--estado` obligatorios en línea
   de comandos, sin rutas por defecto. Es media hora y garantiza que dos circuitos no se pisen.
2. **Ahora, barato:** que `03_CONFIG.yaml` lleve un `circuito.id` y un `circuito.capital_usd`
   propios, y que el muro use el capital **del circuito**, no el global.
3. **Después de F3.1 y de unos meses de MFF:** el segundo circuito, con Topstep.
4. **Antes del tercero:** modelar la multi-fondeada.

No construyas hoy la multicuenta. Construye hoy **la imposibilidad de que dos circuitos compartan
tesorería por accidente**, que es lo que la haría peligrosa.

---

## 4 · Lo que yo añadiría · dos ideas, y la primera me parece importante

### 4.1 · El residuo diario modelo-contra-realidad

**Esto convierte una validación de meses en una señal diaria, y es casi gratis.**

Cada día de papel tienes las barras reales. Puedes darle **esas mismas barras** a
`sesion.resolver_dia` con el estado real de la cuenta y obtener **lo que el modelo decía que
tenía que pasar ese día**. Lo comprobé:

```
el modelo predice el día con las barras REALES:
  {dx_puntos: -6.667, hedge_dolares: 60.667, comision: 57.0,
   muere: False, pausa: True, objetivo: False, barra_evento: 8}
```

Restando lo que pasó de verdad sale un **residuo diario, con n=1**:

- **Residuo cero** → el bot ejecutó exactamente lo que el modelo dice. Es la validación más
  fuerte que existe, y la tienes **el primer día**, no en nueve meses.
- **Residuo ≠ 0** → y ahí está lo bueno: **el residuo ES el coste de ejecución.** La diferencia
  entre el `hedge_dolares` del modelo y el real es literalmente fricción + deslizamiento, medidos
  operación a operación en vez de inferidos.

Te dije que E6 tardaba entre 2 y 9 meses en concluir algo. Eso sigue siendo cierto **para las
tasas de eventos**. Pero el residuo diario mide otra cosa —la fidelidad de la ejecución— y la
mide **desde el día uno**. Y en Fase 3.1 con dinero real, este mismo residuo **es** la medida de
`spr_usd` y `slip_usd_micro`: deja de ser una estimación y pasa a ser una resta.

Cuesta una llamada a `resolver_dia` por cuenta y día. Es la funcionalidad de más valor por línea
de código de todo lo que queda.

### 4.2 · El contrafactual de la dirección contraria

La dirección se sortea 50/50, así que cada día hay un camino no tomado. Con
`calendario.refleja_camino()` —que ya existe— puedes resolver **el mismo día con la dirección
opuesta** y guardarlo.

No cambia ninguna decisión (el laboratorio no decide nada), pero acumula algo que hoy no tienes:
si el sorteo 50/50 es realmente neutral sobre datos reales, o si la serie tiene un sesgo
direccional que el modelo no ve. Con ~250 días tienes una muestra pareada —el mismo día, las dos
direcciones— que es **mucho** más potente estadísticamente que comparar días distintos.

Cuesta otra llamada a `resolver_dia`. Y si algún día aparece un sesgo, es exactamente el tipo de
hallazgo que justificaría reabrir el modelo.

### 4.3 · Menores, si sobra tiempo

- Guardar en el diario **el `k`, el `den` y el `Mm` de cada cuenta y día**. Hoy se persiste el
  resultado, no las entradas. Sin eso, un residuo anómalo no se puede diagnosticar a posteriori.
- Guardar el **estado del feed** y la **horquilla en el instante del disparo y del fill** — ya
  está especificado en D-B, solo hay que asegurarse de que D8 lo emite.

---

## 5 · Veredicto

**No lo daría por terminado, pero está muy cerca y lo que falta está bien acotado.**

Lo que queda, en orden:

1. **D8**, con el detector incremental y su puerta de oráculo (adjunto el script; da 0/1512).
2. **Órdenes en reposo**, no reacciones al cierre de barra. Es un requisito de corrección.
3. **El residuo diario modelo-contra-realidad** (§4.1). Si solo se hace una cosa de esta lista
   además de D8, que sea ésta.
4. **Lector de JSONL** para el laboratorio.
5. **Capital por circuito**, para que la multicuenta no pueda ser peligrosa por accidente.

Y lo de siempre: **nada de esto se escala hasta que F3.1 dé fricción y deslizamiento reales.**
