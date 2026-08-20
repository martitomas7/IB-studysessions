# 08 · LABORATORIO · el instrumento de medida
### D-B · documento, no código (salvo el dashboard, D-C: código, con puerta). El laboratorio mide y avisa; no decide nada por iniciativa propia — el dashboard además ejecuta lo que el operador le pide explícitamente (§7).
**revisión 4 · 20-08-2026 — D-C construido, probado, y en verde (revisión 3, 19-08-2026, había cerrado el
origen del dato de mercado y especificado el dashboard entero; esta revisión lo construye y lo demuestra
contra R3).** Fuentes: `PROMPT_INGENIERIA_NT8.md` §1.3-§1.4 y §2 (el laboratorio, completo),
`02_ARQUITECTURA.md` §4 y §6 (`estado.json`, el diario), `07_ADAPTADOR_NT8.md` revisión 3 (§4, §5.3/§5.4,
§9), `05_ORDEN_DE_CONSTRUCCION.md` (la puerta F3.1, en $/micro; el delta D-C), `03_CONFIG.yaml`
(`dias_por_mes`, `pendientes`), `modelo/cifras_citadas.py` §8 (tasas de evento por mes, 8 semillas),
`modelo/estres_v10.json` (EV/p5/`P(degradar)` de las palancas de §7.1), `tests/replay_v10.json` (los
datos contra los que se construye y se prueba el dashboard, §6.4). Ver §12 para el detalle de qué cambió
y por qué en cada revisión.

---

## 0 · Propósito, y la frase que va dentro del dashboard para que nadie la olvide

El operador no quiere solo un bot que opere en papel: quiere que la fase de papel sea un **instrumento
de medida** a gran escala. Pero el papel puede confirmar unas cosas y no otras, y si el informe no lo
dice, da una confirmación falsa. Por eso esta frase va **dentro del propio dashboard, siempre visible**
(§6.2 — revisión 3: antes vivía solo en el informe periódico, §6.5, que ya no es la superficie
principal), no solo aquí:

> **El papel puede medir la mecánica del circuito y dar una cota inferior de la fricción del mercado.
> NO puede medir la fricción real del hedge (`spr_usd`) ni el deslizamiento real por muerte
> (`slip_usd_micro`) — esos dos solo salen de la Fase 3.1, con dinero real. Cualquier cifra de este
> informe que diga "fricción confirmada" o "deslizamiento confirmado" está mal. Prohibido
> (`PROMPT_INGENIERIA_NT8.md` §2.1).**

Lo que el papel **sí** mide, y es mucho (§2.2 del prompt): la horquilla que se habría cruzado (cota
inferior de la fricción, alerta temprana), la latencia del ciclo completo, el mapeo barra→hora real, las
sesiones reales de MES comparadas con `HG22`, los incidentes de ejecución (rechazos, desconexiones,
fills parciales, patas colgadas), y si el orquestador reproduce las estadísticas del modelo.

---

## 1 · Qué se registra

Cuatro corrientes. Las cuatro son **append-only**, llevan **reloj monótono además del de pared** (para
que un ajuste de hora del sistema no corrompa una medida de latencia), y cada fichero abre con una
cabecera que fija `version_config` y `checksum_config` — el mismo checksum que ya calcula `bot/config.py`
(D0) para `estado.json`, reutilizado aquí, no reinventado.

### 1.1 · Snapshots de mercado — **decidido: Rama B, indicador NinjaScript que escribe a fichero**

> **Corrección de esta revisión (operador, `DATOS_Y_DASHBOARD.md` §1.2): deja de estar pendiente de
> `da1_diagnostico.ps1`.** La revisión 2 dejaba la elección Rama A/Rama B abierta al resultado empírico
> de D-A1.2 (§8 de `07_ADAPTADOR_NT8.md`). Se adopta **Rama B** directamente, con Rama A degradada a
> contraste — no a fuente.

**Por qué Rama B, sin esperar al dato de D-A1.2:** un indicador NinjaScript enganchado al flujo de ticks
interno de NT8 es exacto por construcción (no depende de a qué ritmo responda un sondeo), desacopla el
laboratorio del bot (cada uno sobrevive a que el otro esté parado o se caiga, sin coordinación) y
sobrevive a los reinicios de los dos lados. El precio es aceptado con los ojos abiertos: **reintroduce el
bucle de F5** para este componente — únicamente para él, no para el resto del bot (`PROMPT_INGENIERIA_
NT8.md` §1.3 sigue rigiendo todo lo demás).

**Reglas estrictas, precisamente porque cada iteración cuesta abrir NT8 y pulsar F5 — el indicador se
especifica entero antes de escribirlo, no se itera después:**
- **Solo escribe. No decide, no calcula, no filtra, no agrega.** Ni una condición de negocio: si tiene
  un `if` sobre algo que no sea "¿ha cambiado el valor?", está mal.
- **Cabe en una pantalla.**
- **No bloquea a NT8:** escritura con buffer y volcado periódico, nunca `flush` por tick, y jamás una
  operación de red o de interfaz dentro del indicador.
- El lector tolera la última línea incompleta, igual que el resto de corrientes de este documento (§2).

**Rama A (ATI, muestreo por sondeo) se conserva como contraste, no como fuente:** con el bot corriendo,
un muestreo ATI ocasional compara contra lo que escribió el indicador. Dos fuentes independientes del
mismo dato es la forma más barata de cazar un bug en cualquiera de las dos — una divergencia sostenida
entre ambas es una incidencia (§1.4), no un detalle a ignorar.

**Campos** (una línea por cambio, igual en el indicador y en el muestreo de contraste): `ts_pared`
(ISO 8601), `ts_monotono` (segundos, reloj monótono del proceso), `instrumento` (el contrato MES vigente,
con vencimiento — nunca "MES" a secas, ver `07_ADAPTADOR_NT8.md` §1 sobre fijar el instrumento), `bid`,
`ask`, `last`, **y `estado_feed`** (nuevo en esta revisión, ver abajo). **Frecuencia:** cada cambio de
valor, no un intervalo fijo de sondeo.

#### Estado del feed — dato de primera clase, no un detalle de conexión

> **Corrección de esta revisión (`DATOS_Y_DASHBOARD.md` §1.1): ni AMP/CQG ni Tradovate garantizan tiempo
> real por defecto.** Un feed retrasado (típicamente 10 min) da `bid`/`ask` perfectamente plausibles —
> solo que son la horquilla de hace diez minutos. Sin marcar esto, E1 mediría un número creíble y falso,
> y nadie se enteraría: exactamente la confirmación falsa que §0 prohíbe.

- **`estado_feed` ∈ {`TIEMPO_REAL`, `RETRASADO`, `DESCONOCIDO`}**, por conexión y por instrumento. Se
  determina al arrancar **y se vuelve a comprobar en cada sesión** — una conexión puede degradarse a
  media sesión. Va en la cabecera de cada fichero de mercado **y en cada snapshot**, no solo una vez.
- **`DESCONOCIDO` se trata como `RETRASADO`.** Nunca se asume tiempo real por defecto.
- **Efecto sobre los estimadores** (detalle por estimador en §3-§4): E1 no se publica con feed
  `RETRASADO`/`DESCONOCIDO` — ver la corrección de E1 más abajo. E2, E5 y E6 no dependen de que el
  precio sea actual, siguen funcionando igual. E3 y E4 sí quedan tocados: con feed retrasado, E4 mide la
  forma de la distribución (se conserva) pero no los tiempos (no se conservan).
- **`da1_diagnostico.ps1` (D-A1.0-D-A1.2) incorpora una comprobación explícita del tipo de feed de cada
  conexión** — ver el script actualizado, entregado junto con este documento; su salida se pega aquí en
  cuanto el operador lo corra contra NT8 real (sigue pendiente de eso, igual que el resto de §8 de
  `07_ADAPTADOR_NT8.md`).

### 1.2 · Eventos de orden

Cada transición de la máquina de estados de `07_ADAPTADOR_NT8.md` §4 (`ENVIADA → ACEPTADA → PARCIAL →
LLENA / RECHAZADA / CANCELADA`), con: `ts_pared`, `ts_monotono`, `order_id`, `cuenta` (prop o hedge),
`instrumento`, `estado`, `precio` (si aplica), `cantidad` (si aplica). **Frecuencia:** un registro por
transición detectada — el propio sondeo de §4 es la fuente, no una corriente aparte.

**De aquí salen, sin corriente propia porque ya son una vista de esta:**
- **La latencia del ciclo completo** (E2, §3): se deriva restando `ts_monotono` entre el evento de
  decisión y el de `LLENA`.
- **Los timeouts `N` y `N_hedge`** de `07_ADAPTADOR_NT8.md` §5.2/§5.2b: cada disparo es, precisamente,
  una secuencia de eventos de orden que termina en `CANCELADA` (o en el caso ambiguo). **Esto cierra el
  campo que quedó pendiente de nombrar en la revisión 3 de `07_ADAPTADOR_NT8.md`:** el evento se
  identifica por su propia secuencia de estados, no hace falta un campo booleano aparte —
  `timeout_pata = (motivo_cancelacion == 'N_expirado')` marcado en el registro `CANCELADA`.
- **La divergencia de precio de fill entre las dos patas** (el retoque de revisión 3 de
  `07_ADAPTADOR_NT8.md` §5.3, ramas 4b-LLENA y 2b-LLENA): se deriva de dos eventos `LLENA` — uno por
  cuenta — restando sus `precio`. No hace falta guardarlo aparte; se calcula al leer.

### 1.3 · Eventos del orquestador — reutiliza el diario de `02_ARQUITECTURA.md` §6, no lo duplica

El diario JSONL de una línea por día que ya especifica Arquitectura §6 (`dia`, `direccion`, `ventana`,
`eventos`, `invariantes`, `fin_de_dia`) **ya contiene** intentos, aprobaciones, muertes, empalmes,
bloqueos, emergencias, y el bloque `fin_de_dia` que es, literalmente, el `estado.json` de ese día. El
laboratorio **lee y agrega** ese diario — no inventa un segundo formato paralelo. Esto también resuelve
"estado diario" como corriente separada: no hace falta una, ya está dentro de `fin_de_dia`.

### 1.4 · Incidencias

Rechazos de orden, desconexiones (`Connected()` = falso a media sesión — la fila de `07_ADAPTADOR_NT8.md`
§7 sobre caída del puente), fills parciales, y los dos casos de "pata colgada" que `07_ADAPTADOR_NT8.md`
§5.3/§5.4 ya identifican por nombre (estado ambiguo tras cancelar, reintento de cierre sostenido). Campos:
`ts_pared`, `ts_monotono`, `tipo`, `cuenta` (si aplica), `detalle` (texto libre, para que el humano que
lo lee entienda qué pasó sin tener que reconstruirlo de otros ficheros).

---

## 2 · Formato y rotación

- **Formato:** JSONL (una línea = un registro JSON), igual que el diario de Arquitectura §6 y que
  `tests/replay_v10.json` — coherente con el resto del paquete, no un formato nuevo por capricho.
- **Ficheros:** `laboratorio/mercado_<dia_negociacion>.jsonl`, `laboratorio/ordenes_<dia_negociacion>.jsonl`,
  `laboratorio/incidencias_<dia_negociacion>.jsonl`. El diario del orquestador (§1.3) ya vive donde
  Arquitectura lo puso; el laboratorio lo lee, no lo mueve.
- **Rotación por `dia_negociacion`, no por medianoche de reloj.** La sesión de 22 h cruza la medianoche
  civil; rotar por reloj partiría un día de sesión en dos ficheros. Se rota al mismo límite que usa el
  propio contador `dia_negociacion` de `estado.json`.
- **Cabecera de cada fichero, primera línea:** `{"version_config": "...", "checksum_config": "...",
  "dia_negociacion": N, "hora_arranque_pared": "...", "hora_arranque_monotona": ...}` — mismo checksum
  que `bot/config.py` (D0) ya calcula, reutilizado.
- **Durabilidad, diferenciada por corriente** (propuesta razonada, no una cifra medida — el operador
  puede pedir otra política):
  - **Eventos de orden e incidencias:** se escriben y se fuerzan a disco (`fsync`) **de inmediato**. Son
    pocos y valen mucho — perder uno es perder la reconstrucción de un incidente real de la latencia
    crítica de ejecución.
  - **Snapshots de mercado:** se bufferizan y se vuelcan cada pocos segundos o cada _K_ registros. Son
    ~1,6 millones de observaciones al mes (§2.3 del prompt): forzar disco en cada uno sería el propio
    instrumento de medida compitiendo por I/O con el bot. Se acepta una ventana de pérdida acotada y
    conocida (los últimos segundos antes de una caída) — aceptable porque el estimador que los consume
    (E1, horquilla) no necesita ni un registro concreto: necesita el volumen agregado.
- **Nada se pierde al reiniciar porque nada se sobrescribe:** append-only puro. La reconciliación de
  arranque de `07_ADAPTADOR_NT8.md` §6 ya se ocupa de `estado.json`; el laboratorio no necesita una
  reconciliación propia — si el proceso se cae a media escritura de una línea JSONL, esa línea parcial se
  descarta al leer (JSONL tolera líneas incompletas al final: se ignoran, no invalidan las anteriores).

---

## 3 · Los estimadores

Para cada pregunta de §2.2 del prompt de arranque: fórmula, `n` mínimo (cuando aplica), intervalo con el
que se publica. **Ninguna estimación se publica sin su `n`** — es la misma regla que el resto del
proyecto (`PROMPT_INGENIERIA_NT8.md` §2.4).

### E1 · La horquilla que se habría cruzado — cota inferior de `spr_usd`

> **Corrección del operador: la revisión 1 comparaba peras con manzanas, y el error apuntaba al lado
> peligroso.** `(ask−bid)·valor_punto_usd` es el coste de **un solo cruce**; `spr_usd = 3,00` es la
> **fricción total del round trip** (comisión 1,60 + un tick 1,25 = 2,85, ver `03_CONFIG.yaml →
> hedge_broker.spr_usd`). Comparar directamente la horquilla observada contra 3,00, como hacía la
> revisión 1, **infradeclara el riesgo**: una horquilla de 1,25 parece tranquilizadora frente a 3,00
> cuando en realidad ya implica 2,85 con un solo cruce del round trip completo, y **4,10 si cada pata
> cruza la suya** — la fila que triplica `P(degradar)` en `01_ESPECIFICACION_E2E.md` R-9.3. Corregido.

```
horquilla_usd_micro(t) = (ask(t) - bid(t)) * hedge_broker.valor_punto_usd

friccion_optimista = hedge_broker.comision_rt_usd + 1 * horquilla_usd_micro   # un cruce por round trip
friccion_realista  = hedge_broker.comision_rt_usd + 2 * horquilla_usd_micro   # cada pata cruza la suya
```
calculadas en el instante de disparo (decisión) **y** en el instante de fill, para cada apertura de la
pata hedge. **Unidad: $/micro, round-trip — la misma que exige la puerta F3.1** (`05_ORDEN_DE_CONSTRUCCION.md`,
"SIEMPRE por micro, nunca por muerte"). Se publican la mediana y el p90 de las dos proyecciones, con
`n` = número de aperturas observadas, **contrastadas contra la tabla ya medida de la puerta F3.1**:

| SPR | 3,00 (adoptado) | 4,10 (un cruce por pata) | 4,50 (último que pasa) | 4,75 (rompe el criterio) |
|---|---|---|---|---|

**No tiene un `n` mínimo fijado por una fórmula de precisión** (es una comparación de medianas, no un
conteo de Poisson) — pero converge rápido: a 1 snapshot/segundo, ~1,6 millones de observaciones/mes
(§2.3 del prompt), así que en días hay señal. **Es una alerta temprana, no una medida de `spr_usd`**: si
`friccion_realista` ya supera 4,50 antes de llegar a Fase 3.1, es aviso — no se cambia nada del bot por
esto, se avisa (§9). Ninguna de las dos proyecciones "confirma" `spr_usd` — eso sigue siendo exclusivo de
F3.1 (§0): son una cota, no una medida.

> **Corrección de esta revisión (`DATOS_Y_DASHBOARD.md` §1.1): con `estado_feed` en `RETRASADO` o
> `DESCONOCIDO`, E1 NO se publica.** Ni en el dashboard ni en el informe semanal — en su sitio va,
> literalmente, "E1 no disponible — feed retrasado", nunca un número. Una horquilla vieja calculada
> igual que una fresca es exactamente la confirmación falsa que §0 prohíbe: parece dato, y es ruido con
> apariencia de dato. La comprobación de que esto se cumple es la comprobación 6 de §8.

### E2 · Latencia del ciclo completo (decisión → orden → confirmación → fill)

```
latencia(evento) = ts_monotono(evento_LLENA) - ts_monotono(evento_decision)
```
por cada apertura de pata, separado por pata (hedge / prop) porque son las dos distribuciones que fijan
los valores definitivos de `N` y `N_hedge` (`07_ADAPTADOR_NT8.md` §5.2/§5.2b: percentil alto de esta
misma distribución).

**`n` mínimo — esto sí tiene fórmula, y no es una cifra elegida a ojo:** para que un percentil `p` no sea
un solo punto extremo hace falta, en promedio, al menos `1/(1-p)` observaciones. Verificado (ver §8,
comprobación 2):

| percentil | `n` mínimo |
|---|---|
| p90 | 10 |
| p99 | 100 |
| **p99,9** (el que usa `N`) | **1.000** |

Con eso delante: **antes de tener al menos unos pocos miles de aperturas de la pata prop registradas, el
p99,9 de `N` no es fiable — es ruido con forma de número.** El informe (§6) publica el percentil junto
con `n`, nunca uno sin el otro.

### E3 · Mapeo barra → hora de reloj

No es un estimador de precisión estadística — es una comprobación de consistencia. Cada día de papel se
registra, junto al diario del orquestador, la hora real de la barra `b0` observada por el adaptador de
mercado. **Una vez el mapeo es estable en varios días seguidos** (no hace falta un `n` grande: es una
pregunta de "¿cambia o no cambia?", no de precisión de una tasa), pasa de "pregunta abierta"
(`03_CONFIG.yaml → sesion.barras_por_dia.ojo`) a dato fijado, y se anota en `03_CONFIG.yaml` — **eso lo
decide el operador cuando lo vea, no lo fija este documento por adelantado.**

### E4 · Sesiones reales de MES vs. `HG22`

Ver §4, aparte, porque tiene su propio protocolo de divergencia.

### E5 · Rechazos, desconexiones, fills parciales, patas colgadas

Tallies simples desde §1.4: cuenta por tipo, por día, con tasa = eventos / día operado. **Sin `n` mínimo
formal** — son diagnóstico e informativos por sí mismos, no alimentan ninguna decisión de sizing ni de
`P(degradar)`. Una tasa alta es, en sí misma, la señal (se avisa; §9).

### E6 · ¿El orquestador reproduce las estadísticas del modelo? (muertes, aprobaciones, empalmes, bloqueos, emergencias)

**El estimador central del laboratorio, y el que tiene la tabla de tiempos más importante (§5).** Para
cualquier tasa de tipo Poisson (muertes totales, muertes-eval, muertes-funded, aprobaciones, empalmes,
bloqueos, emergencias):

```
tasa_mes = eventos_observados / dias_operados * tesoreria.dias_por_mes
SE_relativo ≈ 1 / sqrt(n)          [n = eventos_observados]
```

Verificado en §8 contra la propia tabla del prompt de arranque, cifra por cifra. Se publica siempre como
`tasa (n=…, SE_relativo=…)`, nunca la tasa sola.

**Valores de referencia, ahora regenerables desde el paquete.** La revisión 1 citaba estas cifras del
prompt de arranque sin fuente regenerable propia (el desglose por tipo de evento no estaba en ningún JSON
del paquete con la agregación de 8 semillas que exige `01_ESPECIFICACION_E2E.md` §10 — lo más cercano,
`modelo_v10.json:esc.crono`, es de una sola semilla y la propia cabecera de `03_CONFIG.yaml` prohíbe
citarlo). **Corregido: `modelo/cifras_citadas.py` §8 (añadido tras la revisión de D-B) las regenera con
la agregación correcta de 8 semillas** — `modelo/cifras_citadas.json:tasas_evento_mes`:

| evento | /mes | sd |
|---|---|---|
| intentos de eval | 11,593 | 0,026 |
| aprobaciones | **4,501** | 0,008 |
| muertes de eval | **7,093** | 0,021 |
| muertes de fondeada | **4,247** | 0,008 |
| **muertes totales** | **11,340** | 0,026 |
| emergencias | 6,385 | 0,023 |
| recompras | 4,501 | 0,008 |
| resets gratis | 0,600 | 0,005 |

Esta es ahora la tabla de referencia contra la que E6 compara las tasas observadas en papel — regenerable
con `python modelo/cifras_citadas.py`, sin salvedad de trazabilidad.

---

## 4 · Comparación con `HG22`

> **Corrección del operador: el KS de la revisión 1 saltaría siempre, y eso es peor que no tenerlo.**
> Los retornos por barra no son independientes (agrupamiento de volatilidad — un movimiento grande tiende
> a ir seguido de otro movimiento grande, no de ruido plano), y con ~86 barras/día × muchos días el `n`
> efectivo del test es enorme: un KS de dos muestras rechazará con p<0,05 casi con cualquier par de series
> reales, sean o no representativas la una de la otra. Y la regla asociada es "avisar y parar" — con un
> test que siempre rechaza, se pararía siempre, y la alarma se acabaría ignorando por costumbre, que es
> exactamente lo contrario de lo que un instrumento de aviso temprano tiene que hacer. Corregido.

**Qué estadísticos:** volatilidad (desviación estándar de los retornos por barra), rango diario medio,
percentiles de cola (p1/p5/p95/p99 de movimiento por barra) de las sesiones reales observadas en papel,
contra la misma familia de estadísticos calculados sobre `modelo/datos/HG22.npy` (la serie con la que se
calibró el modelo).

**Método: estadísticos resumen con intervalos por bootstrap por bloques, no un test de hipótesis.**
El bootstrap por bloques (remuestrear tramos contiguos de barras, no barras sueltas) respeta la
autocorrelación que un KS barra-a-barra ignora. El KS de dos muestras se mantiene, pero **descriptivo,
no decisorio** — se publica como una lectura más, nunca como el disparador de "avisar y parar".

**La divergencia se define por magnitud, no por significación.** "La volatilidad real cae fuera del
intervalo del 95 % construido por bootstrap sobre `HG22`" es una frase accionable — dice cuánto y en qué
dirección. Un p-valor no lo es: dice si la diferencia es *distinguible de cero* con este `n`, no si
*importa*. **El 95 % del intervalo es una convención propuesta, igual que antes** — se anota en §10 para
que el operador la confirme o la cambie, pero ya no es un umbral de significación que se dispara solo
por acumular datos: es un ancho de intervalo que no crece sin límite según entren más barras.

**Qué se hace si divergen (esto SÍ es una regla cerrada, verbatim del prompt de arranque):**

> **Recoger y comparar. NO re-optimizar** — si divergen, se emite un aviso y se para; tocar el modelo
> requiere permiso explícito del operador.

El laboratorio nunca decide "esto significa que hay que recalibrar" — eso lo decide el operador,
siempre, con el aviso delante.

> **Nota de esta revisión (`DATOS_Y_DASHBOARD.md` §1.1): con `estado_feed` en `RETRASADO`, E4 mide la
> forma de la distribución (volatilidad, rango, percentiles de cola) — eso se conserva con un feed
> retrasado, porque es una propiedad de la SERIE, no del instante. Lo que NO se conserva son los
> tiempos: no se cruza E4 con E3 (mapeo barra→hora) para nada que dependa de "a qué hora ocurrió esto"
> mientras el feed esté retrasado.**

---

## 5 · Cuánto tarda cada estimador en decir algo

Tabla del prompt de arranque §2.3, reproducida aquí porque es la que fija expectativas — verificada
contra la fórmula de E6 en §7. Los conteos de eventos son redondos a propósito (ilustran el orden de
magnitud); la tasa exacta de referencia contra la que se mide el `n` real es la tabla regenerable de
E6 (§3) — 11,34 muertes/mes, no 11,36: la diferencia es la corrección de trazabilidad, no un cambio de
expectativa.

| lo que se quiere concluir | eventos | tiempo de papel |
|---|---|---|
| tasa de muertes con ±30 % | 11 | ~1 mes |
| tasa de muertes con ±20 % | 25 | ~2,2 meses |
| tasa de muertes con ±10 % | 100 | ~8,8 meses |
| aprobaciones con ±20 % | 25 | ~5,5 meses |
| microestructura (E1, E4) | ~1,6 M obs./mes | días |

**La conclusión que hay que trasladar, tal cual la tiene el prompt:** el laboratorio da respuestas sobre
**el mercado** en días, y sobre **la mecánica del circuito** en meses. El diseño de §1-§2 ya está hecho
para que lo primero salga pronto y lo segundo se acumule sin perder nada — no hay nada que optimizar
aquí, solo que no sorprenda cuando E6 tarde meses en tener un `n` decente.

---

## 6 · El dashboard operativo

> **Esta sección sustituye por completo a la antigua "§6 · El informe" de la revisión 2**
> (`DATOS_Y_DASHBOARD.md`, cabecera). El Markdown periódico no desaparece — se queda como archivo
> histórico (§6.5) — pero deja de ser la superficie principal. La superficie principal es este
> dashboard: HTML autocontenido, sin servidor, abrible de un doble clic y desde el móvil.

### 6.1 · Reglas duras

- **Se genera desde los ficheros del laboratorio y el diario del orquestador**, sin inventar ninguna
  fuente nueva. Un script lo regenera; el HTML resultante es autocontenido (datos incrustados, sin CDN,
  sin red).
- **Todo número lleva su frescura y su `n`.** Un dato viejo tiene que *parecer* viejo: si el último tick
  tiene más de `X` segundos, se muestra atenuado y con su antigüedad al lado. *Vivo*, *rancio* y *no
  disponible* tienen que distinguirse sin leer.
- **Nada se muestra sin unidad.** Fricciones y deslizamientos en $/micro, nunca por muerte — la misma
  regla que la puerta F3.1 (`05_ORDEN_DE_CONSTRUCCION.md`).
- **No decide nada por su cuenta.** Muestra, avisa, y ejecuta lo que el operador le pide explícitamente
  (§7). Ningún umbral suyo cambia el comportamiento del bot solo — ver §9, que sigue rigiendo también
  para el dashboard.

### 6.2 · Los ocho bloques

Los tres primeros se miran a diario; el resto es para cuando algo llama la atención.

1. **AHORA** — dirección del día, ventana, barra actual, patas abiertas con su `k` y su `m`, estado de
   las dos conexiones, `estado_feed` de cada una (§1.1), y el semáforo global.
2. **RIESGO** — caja, retirado, tesorería viva, muro dinámico y **la distancia a la degradación**. Va
   grande y solo: es el número que decide si el proyecto sigue vivo.
3. **PENDIENTES DEL HUMANO** — recompras, confirmaciones de aprobación, payouts que pedir, cuenta
   bloqueada esperando decisión, con los días que llevan esperando (la cuenta bloqueada tiene un reloj
   de ~7 días detrás, `07_ADAPTADOR_NT8.md` P3).
4. **CUENTAS** — la eval activa (`bal`, pico, `Mm`, `s₀`, `H`, `k` de hoy, `den`, `ndn`, `nu`, y si está
   bloqueada) y la fondeada con su ciclo; la recámara con **cada dormida y su `s₀` propio** (`bot/
   ciclo_vida.py::activa_funded_si_toca`, D6: el reparto igual del agregado — la lista desagregada que
   Arquitectura §4 pide se pinta aquí tal cual está en `estado.json`); el pool con frescas y rotas.
5. **MERCADO Y FRICCIÓN** — horquilla actual y su distribución del día, y las dos proyecciones de
   fricción (E1, optimista y realista) contra las líneas medidas **3,00 · 4,10 · 4,50 · 4,75**. Con feed
   `RETRASADO`/`DESCONOCIDO`, el bloque entero dice "no disponible" (§1.1, §3).
6. **MODELO vs REALIDAD** — tasas observadas contra las esperadas
   (`cifras_citadas.json:tasas_evento_mes`), cada una con su `n` e intervalo, y cuánto falta para que la
   comparación signifique algo (§5: E6 tarda meses) — dice claramente que **todavía no concluye**, nunca
   lo insinúa.
7. **LABORATORIO** — E1 a E6 con `n`, intervalo y estado, más el progreso hacia el `n` mínimo de cada
   uno.
8. **INCIDENCIAS** — las últimas, con su hora y su detalle, y los contadores por tipo.

El párrafo de §0 —lo que el papel **no** puede confirmar— va **dentro del dashboard, siempre visible**,
no en un enlace.

### 6.3 · Cómo se ve

- **Modo oscuro por defecto**, paleta propia validada contra la superficie oscura — no un modo claro
  invertido automáticamente.
- **Números en monoespaciada, alineados a la derecha**, para comparar en columna sin leer uno a uno.
- **Densidad alta, cero adorno.** Nada de agujas, donuts, 3D ni animaciones — el espacio se gasta en
  datos.
- **Nunca dos escalas verticales en un mismo gráfico.** Dos medidas de magnitud distinta son dos
  gráficos, o se indexan a una base común.
- **Los colores de estado (bien/aviso/grave/crítico) están reservados**, nunca reutilizados como "serie
  4", y nunca van solos: siempre con icono y etiqueta, para que el estado se lea también sin color.
- **La identidad nunca depende solo del color:** con dos o más series, leyenda siempre, etiquetas
  directas en las pocas que importan.
- **Marcas finas, rejilla y ejes discretos**, texto en tinta neutra, no en el color de la serie.
- **Toda vista gráfica tiene su tabla equivalente accesible.**
- **La paleta se valida con un script, no a ojo** — separación para daltonismo y contraste sobre la
  superficie oscura, es computable. La maquetación (solapes, desbordes) se comprueba mirándolo — el
  validador de color no lo hace por sí solo.

### 6.4 · Cuándo se construye

**No depende de NT8 ni de papel corriendo.** Se construye contra datos sintéticos y contra `tests/
replay_v10.json` — 504 días de diario real del modelo con todos los campos que los bloques 4, 6 y 7
necesitan. Eso además lo prueba: si el dashboard sabe pintar los 504 días del replay —incluido el
bloqueo del día 210 y la fase 5, días 255-258, ver el informe de D2-D7— sabrá pintar el papel.

**Sitio en el orden de construcción:** después de la puerta de Fase 1, antes de Fase 2 — delta **D-C**,
ver `05_ORDEN_DE_CONSTRUCCION.md`.

### 6.5 · El informe periódico (histórico, ya no es la superficie principal)

Se conserva tal cual quedó en la revisión 2, como registro de archivo — algo que se pueda mirar seis
meses después sin depender de que el HTML del dashboard de aquel día siga existiendo.

**Formato y sitio:** Markdown, a disco, dentro del repositorio del bot (junto a `laboratorio/`, no
dentro de él). Un TL;DR de tres líneas arriba (verde/ámbar/rojo por métrica clave), detalle debajo. La
separación del §0 va dentro del informe mismo, siempre, en el mismo sitio.

**Cadencia:**
- **Diario, a disco:** semáforo de salud operativa — snapshots capturados hoy, incidencias del día,
  `degradado` sí/no.
- **Semanal, completo:** E1-E6 con sus `n` e intervalos, comparación `HG22` (§4), y el historial de cómo
  evolucionan las tasas de E6 según se acumulan días.

**Lo único que interrumpe fuera de ritmo es una alerta roja**, tres condiciones, no una lista abierta:
1. **Pata colgada** — el estado ambiguo de `07_ADAPTADOR_NT8.md` §5.3/§5.4.
2. **Degradación** — `estado.json.degradado` pasa a verdadero.
3. **`friccion_realista` de E1 por encima de 4,50.**

Nada más dispara un informe fuera de ritmo. **En el dashboard estas mismas tres condiciones son, además,
lo primero que se ve en el bloque 1 (AHORA) y en el bloque 2 (RIESGO) — el informe periódico ya no es
la única forma de enterarse, es el respaldo cuando nadie está mirando el dashboard ese día.**

---

## 7 · Acciones del operador desde el dashboard

El dashboard **no es de solo lectura**. Esto no contradice §9 ("el laboratorio no decide nada"): el
dashboard nunca decide por iniciativa propia, pero sí **ejecuta lo que el operador le pide
explícitamente** — la diferencia entre "decidir" y "ser el sitio desde el que el operador pulsa un
botón" es exactamente la que separa esta sección de §9.

### 7.1 · Las palancas están medidas — no hay que debatir si son baratas

Contra base 1.198,5 · p5 797,2 · `P(degradar)` 1,10 % (`modelo/estres_v10.json`):

| palanca | EV $/mes | Δ | p5 | `P(degradar)` |
|---|---|---|---|---|
| desactivar empalme | 1.184,8 | −13,7 | 776,3 | 1,29 % |
| desactivar CONTRA | 1.195,0 | −3,5 | 800,0 | 1,11 % |
| las dos a la vez | 1.180,7 | −17,8 | 777,7 | 1,33 % |

Menos del 1,5 % del EV y unas décimas de riesgo: eso justifica que las dos palancas estén en el
dashboard. **No justifica que se activen sin dejar rastro** — §7.5.

### 7.2 · Tres clases de acción — la línea que las separa es una sola pregunta

**¿Reduce, mantiene o aumenta la exposición?**

**Clase A · Reducen exposición — siempre permitidas, sin fricción.** Botón directo, una confirmación,
se ejecutan cuanto antes: aplanar las dos patas ahora (y no reabrir hoy), parada del día (no abrir
nada nuevo, lo abierto sigue su flujo normal), parada total / kill switch (aplanar todo, no operar hasta
que un humano reanude explícitamente), cancelar una orden viva colgada.

**Clase B · Cambian el régimen sin abrir nada — permitidas, pero DEJAN MARCA (§7.5 entero).**
Interruptores de configuración operativa que no abren ni cierran nada por sí mismos, pero cambian lo
que el bot hará mañana: desactivar/reactivar empalme, desactivar/reactivar CONTRA, desactivar
emergencia (no recomprar para no dejar el hueco vacío), pausar intentos nuevos de eval dejando vivo lo
que ya está en marcha.

**Clase C · Aumentan exposición o tocan la norma — PROHIBIDAS en el dashboard, sin excepciones y sin
"modo avanzado":** abrir una pata a mano o cualquier cosa que abra posición, cambiar `k`/`m`/buffers/
`qcap`/retención o cualquier valor de `03_CONFIG.yaml`, forzar la dirección del día, desbloquear una
cuenta bloqueada (R-2.4) o forzarla a operar, reanudar tras una degradación. Estas siguen siendo lo que
ya eran — edición de config con su checksum, o intervención manual fuera del bot. **El dashboard nunca
es la vía para aumentar riesgo.**

### 7.3 · El mecanismo — una cola de intención en fichero, no un servidor

El dashboard sigue siendo HTML autocontenido, sin servidor y sin red. Para actuar, escribe una
**intención** en un fichero; el bot la lee y la ejecuta — el bot sigue siendo lo único que toca al
bróker, que es lo que hace esto auditable.

- **`comandos/<id>.json`**, uno por comando, append-only, nunca se editan ni se borran: el bot escribe
  al lado su resultado en `comandos/<id>.resultado.json`.
- **Cada comando lleva:** `id` único, `ts_pared`, `ts_monotono`, `tipo`, `parametros`, `caduca_en`, quién
  lo pidió.
- **Caducidad obligatoria.** Un "aplanar ahora" escrito a las 15:00 no puede ejecutarse a las 17:00, y
  mucho menos mañana. Si el bot lo lee pasada su caducidad, lo marca `CADUCADO` y no lo ejecuta.
- **Idempotencia por `id`.** Un comando se ejecuta exactamente una vez, aunque el bot reinicie a mitad —
  el resultado se escribe antes de considerarlo consumido.
- **Frecuencia de lectura por clase:** Clase A se sondea de forma continua durante la sesión (una parada
  de emergencia que tarda diez minutos no es una parada de emergencia); Clase B, en el punto de decisión
  del día siguiente — no a media sesión, porque cambiar el régimen con posiciones abiertas es justo el
  tipo de cosa que nadie ha medido.
- **Confirmación en dos pasos en la interfaz** para toda acción de Clase A, con el estado actual delante
  (qué patas hay abiertas, con qué tamaño) para que nadie pulse a ciegas.
- **El fichero es local.** El dashboard no se sirve por red ni se expone fuera de la máquina.

### 7.4 · La regla crítica — aplanar las dos patas usa el MISMO protocolo, no un atajo

> **Un botón que aplane las dos patas a la vez reintroduce exactamente la carrera cancelar-vs-fill que
> se corrigió en la revisión 2 de `07_ADAPTADOR_NT8.md`.**

El comando de Clase A "aplanar ambas" **no abre un camino nuevo**: entra por el mismo protocolo de §5.3/
§5.4 de `07_ADAPTADOR_NT8.md` — resolver a estado terminal la orden viva antes de tocar la pata
confirmada, y ante ambigüedad forzar "ninguna pata" aplanando las dos con alerta máxima. Si el código
del comando no llama al mismo camino que usa el cierre de campana, está mal. No es una recomendación de
estilo: el fallo más caro posible de este sistema es quedarse con una pata sola, y un botón de pánico
mal hecho es la forma más fácil de producirlo precisamente en el momento de más nervios.

### 7.5 · Trazabilidad — sin esto, las palancas contaminan el laboratorio en silencio

Es el motivo por el que la Clase B no es gratis aunque cueste 13 $/mes (§7.1). El laboratorio compara
las tasas observadas contra las del modelo (E6, §3) — si el operador desactiva el empalme tres días y
no queda registrado, E6 verá una desviación real y nadie sabrá de dónde viene, y lo peor: alguien podría
concluir que el modelo está mal cuando lo que pasó es que se apagó una palanca.

- **Cada cambio de Clase B es un evento con marca de tiempo** en el diario y en `estado.json`, con
  quién, cuándo y hasta cuándo.
- **`estado.json` lleva un bloque de desviaciones activas**, validado al arrancar como cualquier otro
  invariante.
- **El dashboard muestra, siempre y arriba, si hay alguna desviación activa** — con la palanca, desde
  cuándo, y su coste medido de la tabla de §7.1.
- **El laboratorio excluye o marca los periodos con desviaciones activas** en E6 y en cualquier
  estimador de mecánica — un periodo con el empalme apagado no es comparable con el modelo, que lo
  tiene encendido.
- **Toda desviación de Clase B caduca sola.** Se pide con una duración (hoy, N días); al expirar, el bot
  vuelve a la configuración certificada y avisa de que lo ha hecho. Nada se queda apagado
  indefinidamente por olvido.

---

## 8 · Comprobaciones de que el instrumento mide bien (R3)

Plantilla de `04_GUARDARRAILES_CONSTRUCCION.md` §4: qué comprueba → qué implementación rota debería
saltar → la rotura ejecutada → lo correcto pasando. **Dos de los seis estimadores (E2 y E6) son fórmulas
puramente matemáticas que no dependen de datos de papel ni de NT8** — así que, a diferencia del resto de
este documento, **estas dos se pudieron ejecutar ya, con datos sintéticos, y se pegan las salidas
reales.** Las demás (E1, E3, E4, E5) sí dependen de que exista papel corriendo — se describe qué
rotura debería saltar, para cuando haya datos con los que ejecutarla.

### Comprobación 1 · `SE_relativo ≈ 1/√n` (usada en E6) reproduce la tabla del prompt exactamente

```
=== 1. precision_relativa_poisson -- IMPLEMENTACION CORRECTA ===
  n=  11 -> SE relativo = 30.15 %  (tabla del prompt NT8 dice ~30.15 %)
  n=  25 -> SE relativo = 20.00 %  (tabla del prompt NT8 dice ~20.0 %)
  n= 100 -> SE relativo = 10.00 %  (tabla del prompt NT8 dice ~10.0 %)
  n= 400 -> SE relativo = 5.00 %  (tabla del prompt NT8 dice ~5.0 %)
```

**Rotura a propósito** (falta la raíz cuadrada — `1/n` en vez de `1/√n`):
```
=== 3. ROTURA a proposito: precision_relativa_poisson con formula equivocada (1/n en vez de 1/sqrt(n)) ===
  n=100: correcto=10.00%  roto=1.00%
  -> DIFERENCIA DETECTADA (>5 puntos porcentuales): la rotura SI se distingue. OK, R3 cumplido.
```

**Y una comprobación empírica más — que se rompió a sí misma primero, lo cual es exactamente el
punto de R3.** El primer intento de validar la fórmula por simulación generaba como mucho un evento al
día (una moneda al aire por día, 21 tiradas), no un Poisson de verdad — eso **infraestima** la varianza
frente a un proceso real, donde más de una cuenta puede morir el mismo día:
```
  media observada: 11.432 eventos/mes
  SE relativo EMPIRICO (Bernoulli 1/dia, MAL):  19.90 %
  SE relativo de la FORMULA 1/sqrt(n):          29.58 %
  diferencia: 9.68 puntos porcentuales  <-- no deberían diferir tanto: la propia
                                             comprobacion estaba mal construida, no la formula
```
Corregido con un generador de Poisson de verdad (`numpy.random.poisson`, 20.000 réplicas):
```
=== (corregido) ===
lambda usado: 11.36  ·  replicas: 20000
media observada:                    11.3578
SE relativo EMPIRICO (Poisson real): 29.60 %
SE relativo de la FORMULA 1/sqrt(n): 29.67 %
diferencia: 0.07 puntos porcentuales
-> OK: convergen (diferencia < 2 puntos porcentuales). El fallo de antes era
   del generador sintetico del chequeo (Bernoulli acotado a 1/dia), no de la formula.
```
**Por qué se deja esto en el documento en vez de solo el resultado final:** es el ejemplo más honesto que
tengo de la propia regla R3 — una comprobación que "no ha disparado nunca" es un comentario, no una
comprobación, y aquí la primera versión de la comprobación empírica sí disparó (contra sí misma) antes
de arreglarse.

### Comprobación 2 · `n_min = 1/(1-p)` (usada en E2, la tabla de percentiles)

```
=== 2. n_minimo_percentil -- IMPLEMENTACION CORRECTA ===
  p90.0 -> n minimo = 10
  p99.0 -> n minimo = 100
  p99.9 -> n minimo = 1000
```

**Rotura a propósito** (devuelve el propio `p` como si fuera `n`, sin invertir `1-p`):
```
=== 4. ROTURA a proposito: n_minimo_percentil con p mal puesto como fraccion de n en vez de percentil ===
  p=0.999: correcto n_min=1000  roto n_min=0.999
  -> DIFERENCIA DETECTADA (tres ordenes de magnitud): la rotura SI se distingue. OK, R3 cumplido.
```

### Comprobación 3 · E1 (horquilla) — descrita, pendiente de datos de papel para ejecutarse

**Qué comprueba:** que `horquilla_usd_micro` usa `ask - bid` y no al revés (un signo cambiado daría
horquillas negativas la mitad del tiempo, indetectable a ojo en una tabla larga).
**Implementación rota:** invertir a `bid - ask`.
**Qué debería saltar:** una aserción `horquilla >= 0` (el ask nunca está por debajo del bid en un
mercado sano) — con datos reales, la rotura produce ~50 % de valores negativos; sin datos reales,
esta aserción se ejecuta hoy contra una serie sintética con `ask > bid` siempre, y contra una serie
sintética con `bid`/`ask` intercambiados a propósito, cuando se implemente el sampler.

### Comprobación 4 · E4 (comparación `HG22`) — descrita, pendiente de datos de papel

**Qué comprueba:** que el test KS compara la serie de papel contra `HG22`, no `HG22` contra sí misma.
**Implementación rota:** pasar `HG22` dos veces como las dos muestras del test.
**Qué debería saltar:** el propio KS de dos muestras contra sí misma da `p=1,0` siempre (las dos muestras
son idénticas) — una aserción `p < 1,0 - 1e-9` lo detecta sin necesitar datos de papel todavía: se puede
ejecutar hoy mismo contra `HG22` cargada dos veces, y es una comprobación barata de añadir a la
implementación cuando exista.

### Comprobación 5 · E5 (incidencias) — descrita, pendiente de datos de papel

**Qué comprueba:** que un rechazo de orden se cuenta una vez, no una vez por cada sondeo que lo detecta
(la máquina de estados de `07_ADAPTADOR_NT8.md` §4 es por sondeo, no por evento — el mismo `RECHAZADA`
podría leerse varias veces si el conteo no dedupca por `order_id`).
**Implementación rota:** contar cada lectura de `OrderStatus` en vez de cada transición nueva.
**Qué debería saltar:** con un `order_id` sondeado 5 veces seguidas en estado `RECHAZADA`, la
implementación rota cuenta 5 incidencias; la correcta cuenta 1. Aserción: `incidencias_por_order_id <= 1`
por transición real.

### Comprobaciones 6-12 · el dashboard y las acciones del operador (`DATOS_Y_DASHBOARD.md` §4) — EJECUTADAS, D-C construido

**Las siete se han ejecutado, sin NT8**, contra `bot/adaptador_falso.py` y contra `tests/replay_v10.json`
— exactamente como estaban pensadas. Salidas reales pegadas en `prueba_protocolo_dos_patas.py`,
`prueba_comandos.py` y `prueba_dashboard.py` (entregados junto con el código). Resumen aquí, en la misma
plantilla que las anteriores.

**Del dashboard como instrumento (`bot/dashboard.py` + `bot/contexto_dashboard.py`):**

**Comprobación 6 · un dato rancio pintado como si estuviera vivo — PASA.**
Qué comprueba: que §6.1 ("todo número lleva su frescura") realmente atenúa y marca la antigüedad de un
snapshot viejo. Implementación rota descartada en el propio desarrollo: la primera versión de
`dashboard.py` calculaba `_frescura()` pero nunca la pintaba en el bloque 5 — la propia comprobación 6 la
cazó (`frescura-rancio` ausente del HTML) antes de entregarse. Corregido: el bloque 5 ahora lleva un
badge `vivo`/`rancio` junto a la horquilla. Ejecutada: un snapshot a 530 s (> `dashboard.rancio_seg`=30 s)
se pinta con la clase `frescura-rancio`; uno a 1 s, con `frescura-vivo`.

**Comprobación 7 · un `n` insuficiente presentado como conclusión — PASA.**
Qué comprueba: que el bloque 6 dice "todavía no concluye" cuando `n` está muy por debajo del mínimo de
§5. Ejecutada: con `n=2` el HTML dice "todavía no concluye"; con `n=40` (≥25, el mínimo de referencia de
§5 para ±20 %) pasa a "concluye".

**Comprobación 8 · E1 publicando un número con el feed en `RETRASADO` — PASA.**
Qué comprueba: la corrección de §3. Ejecutada contra `estado_feed` ∈ {`RETRASADO`, `DESCONOCIDO`}: en los
dos casos el bloque 5 dice "E1 no disponible", nunca un número; con `TIEMPO_REAL`, sí publica.

**De las acciones (`bot/comandos.py`, `bot/protocolo_dos_patas.py`):**

**Comprobación 9 · un comando caducado que se ejecuta igual — PASA.**
Ejecutada: un comando con `caduca_en` en el pasado se marca `CADUCADO` en `<id>.resultado.json` y el
`ejecutor` nunca se llama (contador de llamadas = 0).

**Comprobación 10 · un comando ejecutado dos veces — PASA.**
Ejecutada, simulando la caída real: se reclama el comando (`<id>.tomado`), se ejecuta, y se corta ANTES de
escribir `<id>.resultado.json` — el comando sigue viéndose pendiente. Al "reiniciar" (releer pendientes),
se re-ejecuta una vez más (idempotente por diseño, ver `bot/comandos.py`), y el resultado observable es
idéntico a haberlo ejecutado una sola vez. Una tercera lectura ya no lo ve pendiente.

**Comprobación 11 · el botón de pánico produce una pata sola — la importante (§7.4) — PASA, y cazó un
bug real en el propio desarrollo.** Al escribir `bot/protocolo_dos_patas.py`, la primera versión de las
ramas de aborto de §5.3 llamaba a `aplanar()` una vez y devolvía sin confirmar el resultado — la propia
suite de pruebas (no esta comprobación 11, sino su hermana de apertura) lo cazó primero: una pata quedaba
en `ENVIADA` para siempre. Corregido con `_aplana_hasta_confirmar()` (reintenta hasta `LLENA`, la misma
disciplina en aborto y en cierre). Con eso corregido, la comprobación 11 en sí: contra el adaptador falso
configurado para que el cierre de la prop no confirme a la primera, `cierra_las_dos_patas()` (la
CORRECTA) reintenta y cierra las dos patas siempre; `cierra_las_dos_patas_INGENUO_ROTO()` (construida a
propósito, sin esperar ni reintentar) deja la prop abierta y el hedge cerrado en el MISMO escenario —
exactamente una pata sola. **Saltó. D-C se entrega con esta comprobación en verde.**

**Comprobación 12 · una desviación de Clase B que no deja rastro — PASA.**
Ejecutada: `bot/comandos.py::valor_efectivo()` es la única función de todo el bot que lee
`desviaciones_activas` — sin desviación registrada, siempre devuelve el valor certificado (nunca apaga
nada por su cuenta); con una desviación bien formada, apaga la palanca solo dentro de su ventana y la
reactiva sola al expirar; `estado.py::validar()` rechaza una desviación mal formada, duplicada, o con
`hasta_dia <= desde_dia`. **Límite honesto, no disimulado:** `bot/ciclo_vida.py` (D2-D7, ya verificado en
504/504) todavía NO llama a `valor_efectivo()` — sigue leyendo `03_CONFIG.yaml` directo para
`empalme`/`emergencia`/CONTRA. Cablearlo es la recomendación #1 del zip entregado: no se ha hecho en este
pase para no reabrir sin una re-verificación completa el orquestador que costó siete bugs cerrar en 0/504.

---

## 9 · Qué NO decide el laboratorio

> **El laboratorio no decide nada: mide y avisa. Ningún umbral suyo cambia el comportamiento del bot sin
> que lo apruebe el operador.** (`PROMPT_INGENIERIA_NT8.md` §2.4, verbatim.)

En concreto, y para que quede escrito una vez y no haya que repetirlo: E1 por encima de `spr_usd`
supuesto → aviso, no una pausa automática. E4 divergiendo de `HG22` → aviso y parar, nunca
re-optimizar solo. E6 fuera del rango esperado → aviso, no un cambio de sizing. Todos los umbrales de
"cuándo avisar" que este documento propone (el `p<0,05` de §4, por ejemplo) son eso — propuestas — hasta
que el operador los confirme.

---

## 10 · Relación con Fase 3.1

**El laboratorio no mide `spr_usd` ni `slip_usd_micro` — eso es exclusivo de F3.1 con dinero real (§0).**
Lo que sí hace: deja el **formato y las unidades ya listos** para cuando F3.1 llegue.

- **Corrección de esta revisión:** la revisión 1 decía que E1 "ya publica en $/micro, round-trip, la
  unidad exacta de la puerta F3.1" — y no era cierto: publicaba `(ask−bid)·valor_punto_usd` a secas, el
  coste de la horquilla sola, sin la comisión que `spr_usd` sí incluye por definición
  (`03_CONFIG.yaml → hedge_broker.spr_usd`: "comisión + tick"). **Con la corrección de E1 (arriba), ahora
  sí es cierto:** `friccion_optimista`/`friccion_realista` son `comision_rt_usd + n·horquilla`, la misma
  construcción que `spr_usd`. Cuando F3.1 mida `spr_usd` real, el informe de F3.1 puede reusar el mismo
  formato de tabla que este documento ya habrá probado durante meses de papel — no hay que inventar el
  informe de F3.1 desde cero, y sigue siendo E1 el que mueve el semáforo de aviso temprano mientras
  tanto.
- El campo de divergencia de precio de fill (§1.2, del retoque de `07_ADAPTADOR_NT8.md` revisión 3)
  acumula, durante todo el papel, una distribución de cuánto se mueve el precio entre las dos patas por
  el simple paso del tiempo — un dato que **complementa** (no sustituye) la medida de F3.1, porque separa
  "cuánto cuesta el tiempo entre las dos aperturas" de "cuánto cuesta cruzar la horquilla", que son dos
  cosas distintas mezcladas en la fricción total observada en F3.1.

---

## 11 · Decisiones abiertas

| tema | estado |
|---|---|
| Ancho del intervalo de bootstrap para "diverge" en §4 | propuesto 95 %, sin confirmar — ya no es un umbral de significación, es un ancho de intervalo (corrección 2, revisión 2) |
| Mapeo barra → hora de reloj (E3) | se fija solo, con días de observación — no es una decisión, es una espera |
| ¿Liquidar deliberadamente un linaje bloqueado vs dejarlo morir por inactividad? (heredado de `07_ADAPTADOR_NT8.md` P3) | **anotado, no medido, no decidido.** Ocurre ~1 vez cada 504 días — cualquier estimador de esto tardaría años en tener `n` útil por sí solo; no se diseña un estimador dedicado, se registra como una incidencia más (§1.4) y se revisa manualmente cuando ocurra |
| ¿Cablear `bot/comandos.py::valor_efectivo()` dentro de `ciclo_vida.py` para las 4 palancas de Clase B? | **construido y probado en aislamiento (comprobación 12), NO integrado todavía en el orquestador real** — recomendación #1 del zip de esta entrega; requiere re-verificar el replay de 504 días tras el cambio, no hecho en este pase por prudencia |
| Rotación exacta por `dia_negociacion` dentro de `IndicadorLaboratorioMercado.cs` | el `.cs` entregado usa un marcador de posición sin verificar (ver el propio fichero) — se fija al compilar por primera vez contra NT8 real, con el calendario de sesión real delante |

**Cerradas en esta revisión** (ya no son decisiones abiertas): **snapshots de mercado, Rama A vs Rama B**
(§1.1 — se adopta Rama B, indicador NinjaScript, con Rama A como contraste), **entrega y superficie
principal del informe** (§6 — el dashboard sustituye al Markdown como superficie principal; el Markdown
queda como archivo histórico, §6.5), **las acciones del operador** (§7 — mecanismo, clases, y
trazabilidad, las tres cerradas y no solo descritas), **el umbral `X` de "cuánto es rancio"** (§6.1/§6.3
— `dashboard.rancio_seg` = 30 s, provisional, razonado en `03_CONFIG.yaml`, ver historial §12), y **la
duración de una desviación de Clase B** (§7.5 — se cerró con "sin valor por defecto": `bot/comandos.py`
rechaza un comando de Clase B sin `duracion_dias` explícito, en vez de inventar uno).

**Cerradas en la revisión 2** (para que el historial de qué sigue abierto no obligue a leer §12 entero):
cadencia del informe periódico, canal de entrega original (fichero Markdown, sin canal — ahora secundario
por la corrección de esta revisión), y la tabla de tasas esperadas por tipo de evento de E6 (§3,
regenerable desde `modelo/cifras_citadas.json:tasas_evento_mes`).

---

## 12 · Historial de verificación

- **19-08-2026, revisión 1** — documento redactado contra `PROMPT_INGENIERIA_NT8.md` §2,
  `02_ARQUITECTURA.md` §4/§6, `07_ADAPTADOR_NT8.md` revisión 3, `05_ORDEN_DE_CONSTRUCCION.md` y
  `03_CONFIG.yaml`. Las dos fórmulas puramente matemáticas (E2, E6) se implementaron y ejecutaron con
  datos sintéticos — ver §8, comprobaciones 1 y 2 — incluida una comprobación empírica que falló en su
  primer intento por un generador sintético incorrecto, diagnosticada y corregida en el mismo pase. Las
  demás comprobaciones (E1, E4, E5) están descritas pero no ejecutadas: dependen de que exista papel
  corriendo, que depende a su vez de D-A1 contra NT8 real. La rama de snapshots de mercado (§1.1) sigue
  abierta, a la espera de `da1_diagnostico.ps1`.
- **19-08-2026, revisión 2** — el operador revisó la revisión 1 y encontró cuatro fallos, todos
  corregidos: (1) **E1 (§3) comparaba una horquilla sola contra `spr_usd`, que incluye comisión — error
  que infradeclaraba el riesgo.** Corregido a `friccion_optimista`/`friccion_realista` =
  `comision_rt_usd + n·horquilla`, contrastadas contra la tabla ya medida de la puerta F3.1; corregido
  también §10 (entonces §9), que afirmaba (sin serlo, antes de esta corrección) que E1 ya estaba en la
  unidad de la puerta. (2) **El KS de dos muestras de §4 rechazaría casi siempre** por la autocorrelación
  de los retornos por barra y el `n` efectivo enorme — con la regla "avisar y parar" asociada, eso
  paraliza el informe. Corregido a estadísticos resumen con intervalos por bootstrap por bloques (respeta
  la autocorrelación), KS descriptivo no decisorio, divergencia definida por magnitud (fuera del
  intervalo) en vez de por significación (p-valor). (3) **Las tasas de E6 (§3) citaban el prompt de
  arranque sin fuente regenerable propia** — cerrado con `modelo/cifras_citadas.py` §8 (nuevo, aportado
  por el operador), que las regenera con la agregación correcta de 8 semillas: `modelo/cifras_citadas.
  json:tasas_evento_mes`. (4) **La entrega del informe se simplificó** a fichero Markdown en el
  repositorio, sin canal — cadencia diaria a disco + semanal destacado, con tres condiciones exactas de
  alerta roja fuera de ritmo (pata colgada, degradación, `friccion_realista` > 4,50). Esto vivía en §6,
  que la revisión 3 (abajo) sustituyó por completo — el contenido de la revisión 2 sobrevive como §6.5,
  histórico. §11 (entonces §10) se depuró de las decisiones que estas correcciones cerraron. **Nada de
  esto necesitó tocar `tests/` ni el resto de `modelo/`** — solo `modelo/cifras_citadas.py`, sustituido
  por instrucción explícita del operador (ver cabecera del propio fichero).
- **19-08-2026, revisión 3** — `DATOS_Y_DASHBOARD.md` (el operador), dos partes:
  - **Origen del dato de mercado (§1.1), cerrado.** Se adopta Rama B (indicador NinjaScript mínimo,
    solo-escritura, enganchado al flujo de ticks) directamente, sin esperar al resultado empírico de
    D-A1.2 — Rama A (ATI) pasa a ser contraste, no fuente. Se añade `estado_feed` (`TIEMPO_REAL` /
    `RETRASADO` / `DESCONOCIDO`) como campo de primera clase del snapshot y de la cabecera de fichero,
    re-comprobado cada sesión, con `DESCONOCIDO` tratado como `RETRASADO` por defecto. **E1 (§3) deja de
    publicarse con feed `RETRASADO`/`DESCONOCIDO`** — antes de esta revisión, E1 no distinguía el estado
    del feed y habría publicado una fricción proyectada a partir de una horquilla vieja como si fuera
    fresca, la misma confirmación falsa que §0 prohíbe. E3/E4 (§4) anotados: con feed retrasado, E4 mide
    forma (se conserva) pero no tiempos. `da1_diagnostico.ps1` (D-A) se amplía con una comprobación
    explícita del tipo de feed — script entregado junto con esta revisión, salida pendiente de correrse
    contra NT8 real.
  - **El dashboard operativo, nuevo, entero.** §6 sustituida por completo (informe Markdown periódico
    degradado a §6.5, histórico): ocho bloques (AHORA, RIESGO, PENDIENTES, CUENTAS, MERCADO Y FRICCIÓN,
    MODELO vs REALIDAD, LABORATORIO, INCIDENCIAS), reglas de frescura/unidad/no-decide, estilo (oscuro
    por defecto, monoespaciada, densidad alta, paleta validada por script), construible ya contra
    `tests/replay_v10.json` sin esperar a NT8 ni a papel. Nueva §7, "Acciones del operador": tres clases
    (A siempre permitidas, B dejan marca, C prohibidas), cola de intención en fichero (`comandos/<id>.
    json`, caducidad e idempotencia obligatorias), la regla crítica de que "aplanar ambas" reutiliza el
    protocolo §5.3/§5.4 de `07_ADAPTADOR_NT8.md` en vez de abrir un atajo, y trazabilidad obligatoria de
    toda desviación de Clase B contra `estado.json` y E6. §8 gana las comprobaciones 6-12 (R3, `DATOS_Y_
    DASHBOARD.md` §4) — descritas, pendientes de construir D-C, la más crítica siendo la 11 (el botón de
    pánico no puede producir una pata sola). Nuevo delta **D-C** anotado en `05_ORDEN_DE_CONSTRUCCION.md`,
    entre la puerta de Fase 1 y Fase 2, junto al hueco ya reservado de `09_DESPLIEGUE.md`. **Nada de esto
    tocó `tests/` ni `modelo/`** (R6) — solo estos dos documentos y `da1_diagnostico.ps1`.
- **20-08-2026 — D-C construido y probado (mismo día, sesión de ingeniería continuada sin pausas
  intermedias por instrucción del operador).** Código nuevo: `bot/adaptador_falso.py` (simulador del
  puerto de `07_ADAPTADOR_NT8.md` §1, con carreras cancelar-vs-fill fabricables a propósito),
  `bot/protocolo_dos_patas.py` (transcripción literal de §5.3/§5.4, reusable cuando exista el adaptador
  NT8 real), `bot/comandos.py` (la cola de comandos de §7.3, con `valor_efectivo()` para las palancas de
  Clase B), `bot/dashboard.py` + `bot/contexto_dashboard.py` (el HTML autocontenido de los 8 bloques),
  `bot/paleta.py` (validador de contraste WCAG + separación de daltonismo), `IndicadorLaboratorioMercado.cs`
  (Rama B, sin compilar/verificar contra NT8 real — mismo aviso de confianza que `da1_diagnostico.ps1`).
  `bot/estado.py` gana el bloque `desviaciones_activas` y su invariante D-C.1-4 (§7.5). `03_CONFIG.yaml`
  gana `adaptador.timeout_prop_s`/`timeout_hedge_s` (N/N_hedge de `07_ADAPTADOR_NT8.md`, transcritos, no
  inventados), `dashboard.rancio_seg` (elegido y razonado en esta revisión, tal como §11 pedía) y
  `alertas.bloqueada_escalada_dias` (con una discrepancia anotada, en este momento del pase, entre
  `07_ADAPTADOR_NT8.md` P3, 5 días, y `DATOS_Y_DASHBOARD.md` bloque 3, "~7" de forma aproximada — resuelta
  aquí usando solo el valor preciso, 5. **Corregido en la revisión 4 (ver más abajo): no era una
  discrepancia que resolver a una sola cifra — eran dos relojes distintos, y los dos hacían falta.**).
  **Dos bugs reales cazados por la propia suite de pruebas de este pase** (R3, ambos corregidos antes de
  entregar): (1) las ramas de aborto de `abre_las_dos_patas()` llamaban `aplanar()` una vez sin confirmar
  el resultado — corregido con `_aplana_hasta_confirmar()`, reusado también en el cierre; (2) `dashboard.py`
  calculaba la frescura de un snapshot pero nunca la pintaba — corregido, el bloque 5 ahora lleva el badge
  vivo/rancio. Las 7 comprobaciones de §8 (6-12) se ejecutaron de verdad, sin NT8, contra el adaptador
  falso y contra `tests/replay_v10.json`: las 7 pasan, incluida la 11 (no negociable). El validador de
  `bot/paleta.py` cazó una paleta de estado real (aviso/grave demasiado próximos en matiz Y luminosidad),
  corregida y reverificada en verde. El dashboard se generó y se miró (Playwright + Chromium, no solo "no
  lanza excepción") contra 504/504 días del replay, incluidos el bloqueo del día 210 y la fase 5 (días
  255-258) de la entrega de D2-D7, sin un solo fallo. **Límite honesto, no cerrado en este pase:**
  `valor_efectivo()` (comprobación 12) no está todavía cableado dentro de `ciclo_vida.py` — ver §11 y las
  recomendaciones del zip entregado. **Nada de esto tocó `tests/` ni el resto de `modelo/`** (R6).
- **20-08-2026, revisión 4 — el operador revisó la entrega de D-C** (`REVISION_ENTREGA_20260820.md`),
  reproduciendo de forma independiente las tres puertas de arriba (todas verdes) y dando veredicto sobre
  las 7 recomendaciones del zip. Además, encontró **tres defectos reales** en el camino crítico del
  protocolo de las dos patas, no cubiertos por las 7 comprobaciones de §8 hasta ese momento:
  1. **`_poll_hasta` solo esperaba `LLENA`** en las fases de apertura de `bot/protocolo_dos_patas.py` —
     un `RECHAZADA`/`CANCELADA` limpio e inmediato del bróker (información cierta, no ambigua) se trataba
     igual que "el timeout expira", agotando `N`/`N_hedge` sin necesidad y, en el caso de la prop, dejando
     el hedge desnudo ese tiempo de más. Corregido: se poll-ea contra el conjunto completo de estados
     terminales desde el primer instante, con una rama nueva sin alerta para el rechazo limpio — ver
     `07_ADAPTADOR_NT8.md` §5.3 revisión 4 (ramas 2b'/4b').
  2. **`hay_conexion()` nunca se llamaba** en `bot/protocolo_dos_patas.py`, pese a que el contrato del
     puerto (`07_ADAPTADOR_NT8.md` §1) lo exige "antes de cada operación". Corregido: comprobación de
     ambas cuentas al principio de `abre_las_dos_patas()` (exclusiva de la apertura, por la asimetría de
     §7 — el cierre nunca aborta por conexión caída, solo reintenta).
  3. **El reintento de cierre decidía si había terminado mirando el estado de la última orden, no la
     posición real de la cuenta** — si el bróker rechaza una orden de cantidad cero (posición ya plana)
     en vez de aceptarla, el reintento podía no converger. Corregido: la condición de salida de
     `_aplana_hasta_confirmar()` pasa a ser siempre `leer_posicion()`, comprobada también antes de
     intentar aplanar. `bot/adaptador_falso.py` gana `rechaza_aplanar_cantidad_cero` para poder fabricar
     este escenario a propósito ("un simulador que solo simula el caso amable no sirve de red").

  Los tres, corregidos con comprobación R3 nueva (`verificacion_R3/prueba_protocolo_dos_patas.py`
  §§8-10, 40/40 verde). En la misma pasada, siguiendo el veredicto del operador sobre las recomendaciones:
  **cerrado el límite honesto de la revisión anterior** — `valor_efectivo()` (recomendación #1) ya está
  cableado en `bot/ciclo_vida.py` y `bot/calendario.py`, las cuatro palancas de Clase B ya pasan por él;
  añadido el contador `muertes_eval` (recomendación #2), ya visible en el diario y en el bloque 6 del
  dashboard; persistidos `k`/`m` por día en `estado.json` (recomendación #5), el dashboard ya no
  recalcula. **Aceptación de las tres, según lo pedido explícitamente por el operador:** el replay de 504
  días con `desviaciones_activas=[]` tiene que seguir siendo bit-idéntico — re-corrido y confirmado
  **504 días · 0 fallos · caja final 29.134,87 $**, sin cambio. **Recomendación #3 (las alertas de cuenta
  bloqueada) resuelta, no como se pensaba en la revisión anterior:** no es una discrepancia entre 5 y ~7
  días que resolver a un solo número — son **dos relojes distintos** (el del bot, escalada de la alerta a
  los 5 días; el del proveedor, MyFundedFutures mata la cuenta por inactividad a los ~7) — `03_CONFIG.
  yaml` §10 reescrita con los dos por separado, y el bloque 3 del dashboard (`bot/contexto_dashboard.py` +
  `bot/dashboard.py`) ahora pinta los dos, cada uno con su propio semáforo. Recomendación #4 (NT8) sigue
  sin acción posible (pendiente de máquina real); recomendación #6 (`09_DESPLIEGUE.md`) es el siguiente
  paso tras esta revisión; recomendación #7 (bucle de comandos en producción) confirmada como alcance de
  D8, sin acción aquí. Re-verificada también la batería completa (D0, D1 14/14, `romper_mi_orquestador.py`
  5/5 — con el ancla del caso 5 reconstruida contra el texto actual de `ciclo_vida.py`, que había dejado
  de coincidir literal tras el cableado y se saltaba en silencio en vez de cazar el bug: exactamente el
  hueco que R3 existe para cerrar —, `d2_mata_el_proceso.py` 10/10, paleta validada) y `prueba_comandos.py`
  (15/15) / `prueba_dashboard.py` (14/14), ambas sin regresión tras el cambio de firma de `valor_efectivo`.
  **Nada de esto tocó `tests/` ni el resto de `modelo/`** (R6).
