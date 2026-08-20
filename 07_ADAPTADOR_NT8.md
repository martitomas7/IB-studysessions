# 07 · ADAPTADOR NT8 · el contrato con la plataforma
### D-A · documento, no código. Se aprueba antes de tocar nada de `adaptadores/`.
**revisión 3 · 19-08-2026** — **revisión 2 APROBADA por el operador.** Esta revisión resuelve las tres
preguntas que quedaban abiertas (`N_hedge`, simetría del cierre, dónde vive el watchdog) y aplica tres
retoques menores más antes de cerrar D-A: evento de divergencia de precio de fill en la rama 4b-LLENA,
alcance reducido de D-A1.5, y §8 empaquetado en un único script. Ver §12 para el detalle completo. La
revisión 1 no llegó a validarse contra NT8 real.

Fuentes: `PROMPT_INGENIERIA_NT8.md` (§1, §D-A) y el paquete de ingeniería (`02_ARQUITECTURA.md` §2 y §7,
`03_CONFIG.yaml`). Las respuestas del operador a P1/P2/P3 de la sesión de arranque están incorporadas
y marcadas donde aplican. **Todo lo que aquí se presenta como hipótesis de firma de función está sin
verificar contra la DLL real — D-A1 existe exactamente para eso, y ninguna se da por buena sin la
salida pegada.**

---

## 0 · Propósito, alcance y qué se cerró antes de escribir esto

**Propósito.** Este documento es, para la pata NT8, el contrato de la caja `adaptadores/` que
describe `02_ARQUITECTURA.md` §1-2: traduce intención del orquestador → órdenes reales, y traduce
fills/estado real → hechos que el orquestador consume. **No decide nada** (esa prohibición es del
propio módulo `adaptadores/`): no hay aquí sizing, ni sesión, ni `k`, ni `m` calculados — esos números
los produce `sizing.py` a partir de `estado.json` y se los entrega al adaptador ya resueltos.

**Alcance.** Cubre la pata prop (MFF vía Tradovate) y la pata hedge (AMP/CQG), ambas a través de la
Automated Trading Interface (ATI) de NT8, sin NinjaScript — la arquitectura de §1.3 del prompt de
arranque, que se sostiene (ver la respuesta a esa pregunta en la sesión anterior). No cubre el
laboratorio de papel (eso es `08_LABORATORIO.md`, D-B, pendiente de escribir) ni la lógica de negocio
de cuándo abrir qué (eso es la norma y `ciclo_vida.py`).

**Decisiones cerradas en la conversación previa, y dónde viven:**

| pregunta | resolución | dónde se aplica aquí |
|---|---|---|
| **P1** — quién ejecuta las comprobaciones empíricas contra NT8 real | El operador, en su máquina Windows. Yo no ejecuto nada contra NT8. Cada comprobación de §8 lleva comando exacto, salida esperada y tabla de qué significa cada fallo posible. | §8 (D-A1) |
| **P2** — timeout `N` de confirmación de la pata prop | Sin medida existente, no se inventa. Arranca en papel en **N = 5 s, provisional**. El valor definitivo se fija en Fase 2 como percentil alto (p99,9 con margen) de la latencia real medida — nunca a ojo. | §5.2 |
| **P3** — disposición de una cuenta bloqueada (R-2.4) | Alerta y espera **siempre**, sin política automática; escalada de la alerta (canal más ruidoso) a los 5 días sin respuesta, sin que el bot toque nada. **No es una decisión de este adaptador**: pertenece a `ciclo_vida.py` / `estado.json.pendientes_humano` (Arquitectura §8), se documentará en el delta D6. La pregunta de laboratorio que dejó abierta el operador — si liquidar deliberadamente un linaje ya bloqueado es mejor que dejarlo morir por inactividad, sin medir — pasa a la lista de decisiones abiertas de `08_LABORATORIO.md` cuando se escriba. | anotado aquí solo para que no se pierda; implementación en D6 |

---

## 1 · El puerto

Operaciones mínimas que el bot exige de un bróker, en lenguaje de dominio, **independientes de NT8**.
Cualquier camino (A/B/C, §2) tiene que poder implementar exactamente esto:

| operación | entradas | salidas | notas |
|---|---|---|---|
| `abrir(cuenta, instrumento, direccion, cantidad)` | cuenta, instrumento, dirección (+1/−1), cantidad (`k` o `m`, ya resueltos por `sizing.py`) | `order_id`, estado inicial | la dirección la decide `calendario.py`; el adaptador nunca decide cuándo ni cuánto, solo ejecuta |
| `aplanar(cuenta, instrumento)` | cuenta, instrumento | `order_id`, estado | usado en el cierre de campana (barra 85, Arquitectura §5) y en el aborto por timeout de la pata prop (§5) |
| `cancelar(order_id)` | `order_id` | confirmación | solo aplica a órdenes no llenas |
| `leer_posicion(cuenta, instrumento)` | cuenta, instrumento | cantidad neta, precio medio de entrada | insumo de la reconciliación de arranque (§6) |
| `leer_fill(order_id)` | `order_id` | lleno (bool), cantidad llenada, precio medio | por sondeo, no por evento — ver §4 |
| `leer_estado_orden(order_id)` | `order_id` | enviada / aceptada / parcial / llena / rechazada / cancelada | §4 |
| `hay_conexion(cuenta)` | cuenta | bool | se comprueba antes de cada operación; nunca se asume |
| `leer_cuenta(cuenta)` | cuenta | caja, PnL realizado, poder de compra | diagnóstico y alertas; el sizing real vive en `estado.json`, no aquí |
| `arrancar()` / `parar()` | — | — | ciclo de vida del propio puente (`SetUp`/`TearDown` de la ATI) |

**Regla de dependencias (Arquitectura §2):** `adaptadores/` no importa `ciclo_vida` ni `tesoreria`, y no
decide nada — solo traduce. Si en algún momento el código del adaptador contiene una condición sobre
`s₀`, `B`, o cualquier otro símbolo de la norma, está en el módulo equivocado.

> **El instrumento es MES en las DOS patas, sin excepción — escríbelo explícito, no lo dejes
> abstracto.** La norma calcula `pv = 5·k` (R-2.5) y `03_CONFIG.yaml → hedge_broker.valor_punto_usd`
> = 5,0 USD/punto/micro: los dos son el valor de punto del **Micro E-mini S&P 500 (MES)**, no del
> E-mini (ES, 50 $/punto — diez veces más). El parámetro `instrumento` de `abrir()` no es un campo
> libre: el adaptador debe **validar antes de cada orden** que resuelve al contrato MES vigente (con
> su vencimiento correcto) en ambas cuentas, y tratar cualquier otro símbolo como un fallo fatal de
> precondición (R7) — nunca como "el usuario sabrá lo que hace". Confundir el instrumento en una sola
> pata rompe la identidad de cobertura entera por un factor de 10, en silencio, hasta el primer cierre.

---

## 2 · Los tres caminos — comparación y propuesta

| | **A · Python + `pythonnet`** | **B · puente C# + socket local** | **C · OIF (ficheros)** |
|---|---|---|---|
| cierra el bucle sin F5 (requisito duro, §1.2 del prompt) | Sí | Sí — `dotnet build` desde CLI, headless | Sí, pero sin realimentación útil |
| aísla el riesgo de bitness/.NET del resto del bot | No — todo el proceso Python queda acoplado al CLR de NT8 | Sí — solo el puente pequeño depende de la plataforma; Python y sus dependencias (numpy, pyyaml…) quedan limpios | N/A |
| cumple el puerto de §1 (fills, estado de orden, posición) | Sí, si `pythonnet` carga limpio | Sí | **No** — la realimentación (fills, posición) es pobre; ya lo señala el prompt de arranque §1.3 |
| testeable sin NT8 corriendo | Parcial — mockear `pythonnet` es incómodo | Sí — el socket JSON se mockea trivialmente | N/A |
| riesgo nuevo que introduce | fragilidad de `pythonnet` ante versión de .NET y bitness — puede fallar en silencio o de forma difícil de diagnosticar | dos procesos + un protocolo propio que hay que validar, pero cada pieza es pequeña y autocontenida | — |
| encaja con la frontera de `02_ARQUITECTURA` §1-2 | el "adaptador" queda difuso dentro del mismo proceso Python | el socket JSON **es** literalmente la frontera intención↔hechos, explícita e inspeccionable | — |
| se decide con | D-A1.5 (empírico, §8) | D-A1.5 (empírico, §8) | descartado como canal principal; posible respaldo manual, **nunca** automatizado — el propio §D-A del prompt exige "las dos patas o ninguna" con realimentación fiable, que C no da |

**Propuesta de partida, a confirmar con D-A1.5: Camino B.** Motivo resumido (ya discutido con el
operador): B mantiene todo el riesgo de plataforma —bitness, versión de .NET, la propia
`NinjaTrader.Client.dll`— dentro de un único proceso pequeño y sustituible, mientras el resto del bot
(orquestador, tesorería, laboratorio) queda en Python puro sin dependencia de CLR. Dado que NinjaTrader
**no da soporte a código externo** (§1.3 del prompt), esa aislación es lo que hace diagnosticable un
fallo sin ayuda de nadie. **No se descarta A**: D-A1.5 lo prueba también, y si carga limpio y estable
sobre la instalación real, es la opción de menos piezas móviles. La elección final la decide la
evidencia de §8, no esta tabla.

---

## 3 · Mapeo puerto → ATI

> **AVISO DE CONFIANZA.** Los nombres de función de esta tabla son los que documenta la guía oficial de
> NT8 (`functions.htm`, citada en el prompt de arranque §1.3). **Las firmas exactas —nombre de la clase
> que las expone, orden de parámetros, tipos— no están verificadas contra la DLL real.** La
> documentación de NT8 ya se contradijo una vez en este mismo proyecto (la ruta 32 vs 64 bits, §1.3 del
> prompt). Por eso D-A1.1 (§8) empieza con un volcado por reflexión de los miembros públicos reales de
> la DLL **antes** de intentar llamar nada. Esta tabla se actualiza con la firma confirmada en cuanto
> exista, y hasta entonces "firma" es una hipótesis de trabajo, no un hecho.

| operación del puerto (§1) | función ATI (nombre documentado) | firma — hipótesis a verificar en D-A1.1 |
|---|---|---|
| `arrancar()` | `SetUp` | `int SetUp()` |
| `parar()` | `TearDown` | `int TearDown()` |
| `hay_conexion()` | `Connected` | `int Connected(int show)` — qué hace `show` está sin confirmar |
| `abrir()` / `aplanar()` / `cancelar()` | `Command` | firma "stringly-typed" (la interfaz DLL de NT8 es histórica, pensada para VBA/Excel): algo del tipo `int Command(string command, string account, string instrument, string action, string quantity, string orderType, string limitPrice, string stopPrice, string timeInForce, string oco, string orderId, string strategy, string strategyId)` — **verificar parámetro a parámetro**, no asumir tipos numéricos donde la firma real use texto |
| leer precio | `MarketData`, `SubscribeMarketData`, `Bid`, `Ask`, `Last` | — |
| `leer_posicion()` | `MarketPosition`, `AvgEntryPrice` | — |
| `leer_fill()` / `leer_estado_orden()` | `Filled`, `AvgFillPrice`, `OrderStatus`, `Orders` | por sondeo — sin confirmación de que la ATI ofrezca eventos/callbacks; se diseña §4 asumiendo sondeo puro hasta que D-A1 diga lo contrario |
| `leer_cuenta()` | `CashValue`, `RealizedPnL`, `BuyingPower` | — |

**Catálogo de códigos de error:** vacío hasta D-A1.1. Se rellena con los valores reales que devuelva
`SetUp`/`Connected`/`Command` contra la instalación del operador — no se inventan de antemano.

---

## 4 · Máquina de estados de una orden

```
ENVIADA ──► ACEPTADA ──┬──► LLENA
                        ├──► PARCIAL ──► LLENA
                        └──► CANCELADA
ENVIADA ──► RECHAZADA
```

**Detección de cada transición: por sondeo, no por evento** (hasta que D-A1.1 confirme si la ATI ofrece
callbacks — no hay indicio de ello en la documentación citada por el prompt). Cada transición se
detecta comparando `OrderStatus(order_id)` entre dos sondeos consecutivos. Reglas:

- Cada orden lleva un `order_id` propio generado por el adaptador (no reutilizar), para poder
  correlacionar con `estado.json` tras un reinicio del bot.
- La frecuencia de sondeo se fija con el resultado de D-A1.2 (§8) — no antes: no tiene sentido sondear
  más rápido de lo que la ATI realmente actualiza.
- **Nunca se reintenta una pata en bucle** (Arquitectura §7.4). Una orden `RECHAZADA` es un fallo del
  día, no una señal para reenviar con otros parámetros.
- `PARCIAL` es un estado transitorio, no terminal: el adaptador sigue sondeando hasta `LLENA` o hasta
  que expire el `N` de §5 si es la pata prop.

---

## 5 · Protocolo de las dos patas

### 5.1 · Lo que fija la norma (no se discute aquí)

`02_ARQUITECTURA.md` §7, textual:
1. **Apertura:** se manda primero la pata real (el hedge) y solo cuando está confirmada se manda la de
   la prop. Si la prop no confirma en `N` segundos → cerrar el hedge y no operar hoy.
2. **Cierre:** el orden inverso.
3. **Reconciliación al arrancar:** antes de nada, comparar posiciones reales en ambos lados contra
   `estado.json`. Si no cuadran, no operar: avisar y parar. (Desarrollado en §6.)
4. **Nunca se reintenta una pata en bucle.** Un fallo de pata es motivo de parada del día.

> **Resuelto en revisión 3 — mismo principio, sin caso nuevo.** El operador confirmó que el cierre sigue
> exactamente la misma regla que la apertura: nunca se toca la pata confirmada mientras la orden de la
> otra no esté en estado terminal. Formalizado en **§5.4**.

### 5.2 · El timeout `N` — resuelto en esta sesión, valor provisional

**No hay ninguna medida de latencia en el proyecto. No se inventa (R2).** Resolución acordada con el
operador:

- Durante la espera de confirmación de la pata prop, la posición real y abierta es **solo el hedge**
  (la norma manda el hedge primero) — `m` micros MES, sin la prop todavía delante. Por config
  (`sizing.m_eval` = 2, `sizing.m_fun` = 4, `hedge_broker.valor_punto_usd` = 5,0 USD/punto/micro), el
  valor por punto de esa exposición desnuda es **10 $/punto en evaluación, 20 $/punto en fondeada**.
  Tomando la lectura del operador en términos del lado prop (`pv = 5·k`, con `k≈15` como orden de
  magnitud ilustrativo, ~75 $/punto) el argumento es el mismo o más fuerte: en cualquiera de las dos
  lecturas, una espera prolongada acumula exposición direccional real sin techo.
- El coste de abortar el día es acotado y conocido: la EV de todo el sistema es
  `meta.cifra_objetivo_usd_mes / tesoreria.dias_por_mes` = 1.198,50 / 21 ≈ **57,07 $/día**, y abortar
  afecta como mucho a una cuenta, no al sistema entero.
- **Conclusión operativa: errar por corto es barato y con techo conocido (≤ 57 $, un día); errar por
  largo es una exposición real, sin techo, mientras dure la espera.** Por eso el valor de arranque
  favorece el corto.
- **Valor de arranque en Fase 2 (papel): `N = 5 s`, marcado explícitamente como PROVISIONAL.**
- **Valor definitivo:** se fija cuando la Fase 2 mida la latencia real del ciclo completo
  (decisión → orden → confirmación → fill, §2.2 del prompt de arranque NT8), como el **percentil alto
  (p99,9, con margen) de esa distribución** — nunca una media, nunca a ojo.
- Mientras `N` sea provisional: cada disparo del timeout (cierre de hedge por no-confirmación) es un
  evento que debe quedar registrado para alimentar esa medida — campo pendiente de nombrar en
  `08_LABORATORIO.md` (p. ej. `eventos.timeouts_pata_prop`) cuando se escriba D-B.

### 5.2b · `N_hedge` — el segundo timeout que faltaba, resuelto en revisión 3 con la asimetría INVERTIDA

El operador señaló correctamente que el paso 2 del flujo original (esperar el fill del hedge) no tenía
cota: un hedge que nunca confirma dejaba el bot colgado sin límite. **Se añade `N_hedge`, con el mismo
tratamiento mecánico que `N`** (timeout + manejo de la carrera cancelar-vs-fill de §5.3) **y el mismo
estatus de provisional.**

El análisis de la revisión 2 (por qué no copiar el valor de `N` sin más) era correcto, y el operador lo
llevó hasta su conclusión: durante la espera de `N`, hay una pata real **ya abierta y sin cubrir**
acumulando exposición por segundo — de ahí que corto sea barato. Durante la espera de `N_hedge`, en
cambio, **esperar no crea ninguna exposición nueva**: o el hedge no se ha enviado/ejecutado todavía (no
hay nada expuesto), o ya se ejecutó y el riesgo de precio existe **con o sin timeout** — el timeout no
lo evita. Lo único que cuesta esperar de más aquí es, en el peor caso, un rato de más antes de operar;
lo que cuesta **cortar de menos** es abortar un día que el hedge habría confirmado con un poco más de
margen. **La asimetría se invierte: en `N_hedge`, largo es barato y corto es lo caro.**

- **Valor de arranque en Fase 2 (papel): `N_hedge = 30 s`, marcado explícitamente como PROVISIONAL** —
  razonado (por la asimetría de arriba), no medido.
- **Valor definitivo:** sale de la misma distribución de latencia real medida en Fase 2 que fija `N`
  (§5.2). El operador no ha fijado con qué percentil se resume esa distribución para `N_hedge`
  específicamente — dado que aquí largo es barato, el percentil correcto podría no ser el mismo p99,9
  que usa `N` (podría no hacer falta ser tan agresivo, o al revés, podría convenir un margen aún mayor).
  **Eso se decide en Fase 2 con los datos delante, no aquí.**
- Igual que con `N`: mientras `N_hedge` sea provisional, cada disparo de su timeout es un evento que
  queda registrado (mismo campo pendiente de nombrar en `08_LABORATORIO.md`).

### 5.3 · Qué hace el adaptador exactamente — CORREGIDO (revisión 4)

> **Qué estaba mal en la revisión 1, y por qué era el fallo grave.** El paso 5b original mandaba
> `aplanar(cuenta_hedge)` en cuanto expiraba `N`, sin tocar antes la orden de la prop que seguía viva.
> Si esa orden de la prop se llenaba **mientras** se ejecutaba el aplanamiento del hedge (una carrera
> real: cancelar y llenar pueden cruzarse), el resultado era una posición prop abierta sin hedge — el
> "fallo operativo más caro posible" que el propio §6 nombra, producido por el propio código que debía
> evitarlo. Corregido: **la pata que se toca primero al abortar es siempre la que todavía tiene una
> orden viva y cancelable — nunca se aplana la pata confirmada hasta saber con certeza qué pasó con la
> otra.**

> **Qué añade la revisión 4 (revisión del operador, 20-08-2026 — "Defecto 1" de
> `REVISION_ENTREGA_20260820.md`).** Las revisiones 2-3 solo distinguían "confirma antes del timeout"
> (2a/4a) de "el timeout expira" (2b/4b) — y dentro de 2b/4b, solo miraban el estado terminal **después**
> de mandar `cancelar()`. Pero `RECHAZADA` y `CANCELADA` son también estados TERMINALES de §4, y el
> bróker puede devolverlos **de inmediato, sin que haga falta esperar a que expire `N`/`N_hedge` ni
> mandar `cancelar()`** — un rechazo instantáneo (p. ej. margen insuficiente, mercado cerrado, símbolo
> mal formado) es información **cierta y limpia**, no la ambigüedad que 2b/4b resuelven. Tratarlo igual
> que "pasa el timeout sin confirmar" desperdicia el `N`/`N_hedge` entero esperando algo que ya se sabe
> que no va a pasar — y en el caso de la prop, deja el hedge desnudo ese tiempo entero de más, que es
> exactamente la exposición que `N` existe para acotar. Por eso el sondeo de los pasos 2 y 4 ya no
> espera solo `LLENA`: espera **cualquier estado terminal de §4** (`LLENA`, `CANCELADA`, `RECHAZADA`)
> desde el primer instante, con una rama nueva para el rechazo/cancelación limpios que llegan antes de
> agotar el reloj. **Comprobación R3 de esta rama:** `verificacion_R3/prueba_protocolo_dos_patas.py`
> §8 (ambas fases, tiempo lógico consumido = 0, sin alerta).
>
> La revisión 4 añade también, delante de ambas fases, la comprobación de conexión de ambas cuentas que
> el propio contrato del puerto (§1) exige "antes de cada operación" y que la revisión 3 no llegaba a
> hacer explícita en este diagrama ("Defecto 2" de la misma revisión del operador) — ver el paso 0 y su
> nota. **Comprobación R3:** `verificacion_R3/prueba_protocolo_dos_patas.py` §9.

```
PASO 0 (apertura, antes de mandar NADA — Defecto 2)
   hay_conexion(cuenta_hedge) Y hay_conexion(cuenta_prop)
   ├─ las dos conectadas      → sigue a FASE HEDGE
   └─ cualquiera desconectada → NO se manda ninguna orden. NO se opera hoy.
                                 Alerta de máxima prioridad. (§7: una apertura que aún no
                                 confirmó nunca se reintenta con la conexión caída.)
                                 Nota: este paso 0 es EXCLUSIVO de la apertura — el cierre
                                 (§5.4) nunca aborta por conexión caída, solo reintenta
                                 (asimetría ya fijada en §7).

FASE HEDGE
1. abrir(cuenta_hedge, MES, -direccion, m)                       # el hedge va en contra
2. sondear leer_estado_orden(order_id_hedge) hasta un estado TERMINAL (LLENA, CANCELADA
   o RECHAZADA — revisión 4)
   o hasta que pase N_hedge = 30 s provisional (§5.2b)

   2a. LLENA antes de N_hedge  ──────────────────────►  ir a FASE PROP
   2b'. CANCELADA/RECHAZADA LIMPIA, antes de agotar N_hedge (revisión 4, Defecto 1)
                                → no se abrió nada. NO se opera hoy. Anotar evento
                                  (hedge_rechazado_limpio). CERO tiempo de espera adicional:
                                  no se llama a cancelar() (ya está en estado terminal) ni se
                                  espera el resto de N_hedge. SIN alerta de máxima prioridad
                                  — es información cierta, no ambigua, a diferencia de 2b.
   2b. pasa N_hedge sin confirmar (sigue vivo: ENVIADA/ACEPTADA):
         cancelar(order_id_hedge)
         sondear leer_estado_orden(order_id_hedge) hasta un estado TERMINAL
         ├─ CANCELADA           → no se abrió nada. NO se opera hoy. Anotar evento (N_hedge).
         ├─ LLENA (la cancelación llegó tarde: el hedge sí se ejecutó)
         │                      → tratar como 2a: ir a FASE PROP con el hedge ya confirmado.
         │                        Anotar el evento igual (dato útil para medir N_hedge) — INCLUYE
         │                        el precio de fill del hedge, ver nota de divergencia más abajo.
         └─ PARCIAL / error de cancelación / estado ambiguo
                                → aplanar(cuenta_hedge, MES) por la cantidad que exista.
                                  Alerta de máxima prioridad. NO se opera hoy.
                                  (mismatch de cantidad = no se puede seguir; R7)

FASE PROP  (solo se llega aquí con el hedge YA confirmado y en pie)
3. abrir(cuenta_prop, instrumento_prop, direccion, k)
4. sondear leer_estado_orden(order_id_prop) hasta un estado TERMINAL (LLENA, CANCELADA
   o RECHAZADA — revisión 4)
   o hasta que pase N (§5.2)

   4a. LLENA antes de N        ──► día abierto con las dos patas — sigue el flujo normal de sesión
   4b'. CANCELADA/RECHAZADA LIMPIA, antes de agotar N (revisión 4, Defecto 1)
                                → la prop nunca se abrió. SOLO AHORA: aplanar(cuenta_hedge, MES)
                                  — el hedge YA confirmado (paso 2) no se deja desnudo ni un
                                  instante más de lo necesario para esta única llamada. Anotar
                                  evento (prop_rechazada_limpio). CERO tiempo de espera adicional:
                                  no se llama a cancelar() ni se espera el resto de N. SIN alerta
                                  de máxima prioridad — es información cierta, no ambigua.
   4b. pasa N sin confirmar (sigue vivo: ENVIADA/ACEPTADA):
         cancelar(order_id_prop)                                  # SIEMPRE la prop primero, nunca el hedge
         sondear leer_estado_orden(order_id_prop) hasta un estado TERMINAL
         ├─ CANCELADA           → confirmado que la prop nunca se abrió.
         │                        SOLO AHORA: aplanar(cuenta_hedge, MES).
         │                        NO se reintenta la prop. Anotar evento (N). NO se opera hoy.
         ├─ LLENA (la cancelación llegó tarde: la prop sí se ejecutó)
         │                      → NO se toca el hedge. Las dos patas están puestas.
         │                        El día sigue con normalidad. Anotar el evento igual (dato de N)
         │                        — Y REGISTRAR AvgFillPrice(hedge), AvgFillPrice(prop) y su
         │                        diferencia (ver nota de divergencia justo debajo).
         └─ PARCIAL / error de cancelación / estado ambiguo
                                → NO se puede confirmar cuál es el estado real de ninguna de las dos
                                  patas con certeza. aplanar(cuenta_prop, instrumento_prop) Y
                                  aplanar(cuenta_hedge, MES) — las dos, en ese orden (Arquitectura
                                  §7.2, "el orden inverso"). Alerta de máxima prioridad. NO se opera
                                  hoy. Esto es la respuesta simétrica de "las dos patas o ninguna"
                                  ante ambigüedad: si no se puede demostrar que es "una", se fuerza a
                                  "ninguna".
```

**Por qué 2b'/4b' no llevan alerta y 2b/4b sí (cuando degeneran en PARCIAL/ambiguo).** Una
`RECHAZADA`/`CANCELADA` que llega como respuesta directa del bróker es la información más limpia que
existe en la máquina de estados de §4 — no hay nada que reconciliar, no hay carrera posible porque la
orden nunca estuvo viva el tiempo suficiente para cruzarse con nada. Reservar la alerta de máxima
prioridad para los casos donde de verdad hace falta que un humano mire (timeout agotado, estado
ambiguo tras cancelar) evita que la alerta pierda valor por sonar también en el caso más benigno
posible — "el bróker dijo que no" con educación, sin ambigüedad.

**Por qué el orden de la fase PROP importa (esto es la corrección):** cancelar antes de aplanar, y
esperar el estado terminal de la cancelación antes de tocar el hedge, es lo único que evita la carrera
que dejaba la posición prop desnuda en la revisión 1. El hedge **nunca** se toca mientras el estado de
la orden de la prop siga sin ser terminal.

> **Retoque de revisión 3 — divergencia de precio de fill entre las dos patas.** Las dos patas entran
> con una diferencia de tiempo (como mínimo el sondeo de confirmación; en la rama 4b-LLENA, hasta `N`
> segundos de más). Sus precios de entrada, por tanto, **no tienen por qué coincidir** — y esa
> diferencia **no la absorbe necesariamente `spr_usd`**, que modela la fricción de cruzar la horquilla,
> no el deslizamiento por el simple paso del tiempo entre las dos aperturas. Por eso, en **cualquier**
> apertura donde las dos patas confirmen (la 4a normal, y muy especialmente la 4b-LLENA y su análoga
> 2b-LLENA del lado hedge), el adaptador registra `AvgFillPrice` de las dos patas y su diferencia como
> **evento del laboratorio** — candidato a umbral de alerta cuando se escriba `08_LABORATORIO.md` (D-B).
> No se fija aquí ningún umbral: eso es un número que hace falta medir, no inventar.

### 5.4 · Cierre — mismo principio de §5.3, formalizado en revisión 3

**No es un caso nuevo.** El operador lo resolvió con una frase: *nunca se toca la pata confirmada
mientras la orden de la otra no esté en estado terminal* — el mismo principio de la apertura, aplicado
al cierre. Arquitectura §7.2 fija el orden: cierre en el orden inverso de la apertura, es decir,
**primero la prop, luego el hedge**.

```
CIERRE  (orden inverso de la apertura: primero la prop, luego el hedge)

FASE PROP (cierre)
1. aplanar(cuenta_prop, instrumento_prop)
2. sondear leer_estado_orden(order_id_cierre_prop) hasta un estado TERMINAL

   ├─ LLENA (el cierre de la prop se confirmó)
   │                      → ir a FASE HEDGE (cierre)
   └─ CANCELADA / rechazada (el cierre de la prop NO se confirmó — la prop
      sigue con posición viva)
                          → NO se toca el hedge todavía (sigue cubriendo).
                            SE REINTENTA el cierre de la prop (paso 1 de nuevo).
                            Esto NO es "reintentar una pata en bucle" en el
                            sentido de §5.1 regla 4 — esa regla prohíbe
                            insistir en un intento de APERTURA fallido, donde
                            el estado seguro es "no abrir nada". Al CERRAR no
                            hay ese estado seguro: abandonar el intento deja
                            una posición real abierta, que es estrictamente
                            peor que seguir intentando. Si los reintentos
                            siguen fallando de forma sostenida, es indistin-
                            guible de "conexión caída" (§7): se alerta con
                            prioridad creciente sin dejar de intentar, y el
                            operador interviene si no es transitorio.

FASE HEDGE (cierre)  (solo se llega aquí con el cierre de la prop YA confirmado)
3. aplanar(cuenta_hedge, MES)
4. sondear leer_estado_orden(order_id_cierre_hedge) hasta un estado TERMINAL

   ├─ LLENA               → día cerrado, las dos patas planas.
   └─ CANCELADA / rechazada / estado ambiguo
                          → la prop YA está cerrada y el hedge NO. Esto es
                            justo la asimetría peligrosa que la apertura
                            evita por diseño: una pata cerrada y la otra
                            abierta. SE REINTENTA el cierre del hedge (paso 3)
                            con la misma disciplina que el cierre de la prop.
                            Alerta de máxima prioridad de inmediato (no se
                            espera a que los reintentos se agoten: aquí el
                            riesgo es real desde el primer instante).
```

**Por qué el desenlace seguro es "ninguna pata" en los dos sentidos.** Al abrir, "ninguna pata" se logra
**no completando** la apertura (abortar es gratis y seguro). Al cerrar, "ninguna pata" se logra
**insistiendo hasta completar** el cierre (abandonar deja una posición real viva, que es lo peligroso).
Es el mismo objetivo — plano a los dos lados — alcanzado por el camino contrario según se abra o se
cierre. No hay pregunta pendiente aquí.

---

## 6 · Reconciliación de arranque

Antes de operar (Arquitectura §5, "antes de `b0`"), el adaptador compara:

- `leer_posicion(cuenta_prop, instrumento_prop)` y `leer_posicion(cuenta_hedge, MES)` — posición real
  de ambos lados.
- Lo que `estado.json` cree que debería haber, según `funded.activa`/`eval.activa` y sus tamaños
  vigentes.

**Casos de descuadre a cubrir explícitamente**, de más a menos grave:

| descuadre | qué significa | qué hace el bot |
|---|---|---|
| posición prop sin hedge, o hedge sin prop | el caso "una sola pata" — el fallo operativo más caro posible (Arquitectura §7, cabecera) | no opera, alerta con máxima prioridad, no se toca la posición hasta intervención humana explícita |
| posición residual en una cuenta que `estado.json` cree cerrada | un cierre anterior no se completó o no se registró | no opera esa cuenta, alerta, exige reconciliación manual |
| tamaño de posición que no coincide con `k`/`m` esperados | fill parcial no registrado, o intervención manual fuera del bot | no opera, alerta con el detalle del desajuste (esperado vs real) |
| todo cuadra, sin posición viva | día nuevo o reinicio entre sesiones | sigue el día normal (arranca antes de `b0`) |
| **todo cuadra Y hay posición viva de ambas patas, coincidente con `estado.json`** | **reinicio a media sesión** (crash del bot, del puente, o de NT8 durante el día — ver §7) — esto **no es un error**, es el caso esperado tras una caída con las dos patas ya abiertas | **NO se re-ejecuta la entrada de `b0`** (violaría R-3.7, "como mucho una vez por día") — el bot retoma el sondeo de la sesión (Arquitectura §5, barras `b0+1`…85) desde la barra que corresponda según `estado.json`/el diario, como si nunca se hubiera caído |

Esta reconciliación es **fatal**, no un warning (misma categoría que los 8 invariantes de
`estado.json`, Arquitectura §4): si no cuadra, el bot no "sigue con la mejor estimación" (R7 de los
guardarraíles) — para y avisa. La única excepción es la fila de "reinicio a media sesión": ahí "cuadra"
significa exactamente eso, cuadra, y el bot **debe** seguir — parar en ese caso sería tan incorrecto
como seguir en un caso que no cuadra.

---

## 7 · Modos degradados

| condición | cómo se detecta | comportamiento del bot |
|---|---|---|
| NT8 cerrado / no arrancado | `SetUp()` falla, o no hay proceso NT8 en ejecución | no arranca el día, alerta |
| ATI deshabilitada | `SetUp()`/`Connected()` devuelven el código de error que documente D-A1.2 | no arranca, alerta con la instrucción exacta: `Tools → Options → Automated Trading Interface → «AT Interface»` |
| conexión caída (Tradovate o AMP/CQG) | `Connected(cuenta)` = falso | **distingue apertura de cierre (§5.4).** Si afecta a una APERTURA que aún no confirmó: no se reintenta (§5.1 regla 4), se aborta el día, se alerta. Si afecta a un CIERRE con una posición real viva: sí se reintenta el cierre con alerta de prioridad creciente (§5.4) — dejar de intentar no es una opción cuando hay una pata abierta de verdad |
| cuenta no encontrada / nombre erróneo | `Command`/`MarketPosition` devuelven error de cuenta | no arranca, alerta — puede ser un cambio de nombre/enrutado de la cuenta MFF (pregunta del operador, §6.2 del prompt de arranque) |
| mercado cerrado | fuera de la ventana de sesión que decide `calendario.py` | el adaptador no decide esto; si NT8 rechaza una orden por mercado cerrado, lo reporta como rechazo de pata, no lo reinterpreta |
| **NT8, el puente o el proceso del bot se caen a media sesión, con una o las dos patas abiertas** | el propio proceso del bot deja de correr — no hay nada que el bot pueda "detectar" mientras está caído | **no hay acción posible durante la caída** (el proceso está muerto). La respuesta entera ocurre al reiniciar, vía la reconciliación de §6: si las dos patas coinciden con `estado.json`, se retoma la sesión (fila nueva de §6); si no coinciden, es el caso "una sola pata" y se para. **Esto exige un supervisor externo al propio bot** (watchdog de sistema operativo — Task Scheduler o equivalente — que note el proceso muerto y lo reinicie, o al menos alerte de inmediato): sin eso, una caída con una sola pata abierta puede quedar sin nadie enterado durante horas. **Resuelto dónde vive (revisión 3): NO es D9** (D9 son aserciones dentro de un proceso vivo; el watchdog existe justo para cuando el proceso está muerto) — **vive en `09_DESPLIEGUE.md`**, anotado como entregable previo a Fase 2 en `05_ORDEN_DE_CONSTRUCCION.md`. No escrito todavía |

---

## 8 · Comprobaciones empíricas (D-A1)

**Las ejecuta el operador, en la máquina Windows con NT8 real. Nada de esta sección se ejecuta desde la
sesión de ingeniería. Ninguna comprobación se da por buena sin la salida pegada literal.**

> **Nuevo, 20-08-2026 — `simulador_nt8/` NO sustituye nada de esta sección.** A petición del operador se
> construyó un simulador de NT8 **independiente y fuera de proceso** (`simulador_nt8/`, con su suite en
> `verificacion_R3/integracion_proceso_real/`): un proceso de sistema operativo aparte que implementa el
> contrato del puerto de §1 envolviendo `bot/adaptador_falso.py`, para poder probar el protocolo de las
> dos patas, el vigía de conexión, y la reconciliación de §6 bajo una frontera de proceso/red REAL —
> matando procesos con `kill -9`/`SIGSTOP`, con timeouts de reloj de pared reales (`N`=5,0s,
> `N_hedge`=30,0s cumplidos al milisegundo contra el propio `03_CONFIG.yaml`) — cosas que
> `AdaptadorFalso` en proceso, usado por `verificacion_R3/prueba_protocolo_dos_patas.py`, no puede
> demostrar por construcción. **No toca ni acerca nada a D-A1**: sigue sin haber ninguna verificación
> contra NT8 real, ningún dato sobre firmas/bitness/errores de la ATI, y nada de esto autoriza a saltarse
> ni una sola comprobación de esta sección cuando haya máquina disponible. Ver `simulador_nt8/LEEME.md`
> para el aviso completo de qué es y qué no es.

### D-A1.0 a D-A1.2 · empaquetadas en un único script (revisión 3)

> **Antes (revisión 2): tres bloques de PowerShell sueltos, tres idas y venidas.** El operador pidió
> algo distinto: **una sola ejecución que lo cubra todo y vuelque a un fichero**, para que cuando haya
> máquina disponible sea una ejecución y un pegado, no diez.

**`da1_diagnostico.ps1`** (fichero adjunto junto a este documento) fusiona D-A1.0 (localizar la DLL, su
arquitectura, su runtime .NET, y la versión de NT8), D-A1.1 (volcado por reflexión de los tipos y
métodos reales, identificación de la clase de la ATI, `SetUp()`/`Connected()`) y D-A1.2 (frecuencia real
de `MarketData` de MES durante 60 s) en una sola pasada. Es de **solo lectura**: no manda ninguna orden,
no toca ninguna cuenta.

**Uso:**
```powershell
powershell -ExecutionPolicy Bypass -File da1_diagnostico.ps1
```

**Diseño, para que se entienda qué hace y por qué:**
- Cada bloque va envuelto en `try/catch`: si un paso falla, el fallo se anota en el fichero y el script
  **sigue** con el siguiente bloque — no se pierde lo que ya se consiguió por un fallo posterior (mismo
  principio de "guarda todo lo que se pueda" que `08_LABORATORIO.md`).
- Cada línea se escribe en el fichero **en el momento**, no al final — si el script se interrumpe a
  media ejecución (el muestreo de `MarketData` dura 60 s), lo ya recogido queda guardado igual.
- La clase de la ATI se localiza **por reflexión** (busca la que expone un método estático `SetUp`), no
  por un nombre hipotético hardcodeado — coherente con el aviso de confianza de §3: no se asume la firma,
  se descubre.
- El código de contrato MES del bloque de `MarketData` (`"MES 12-26"`) es un **valor de ejemplo que hay
  que ajustar** al vencimiento vigente en el momento de ejecutar — está marcado en el propio script con
  un comentario `AJUSTAR`.

**Qué pegar de vuelta:** el contenido íntegro del fichero `da1_diagnostico_<fecha>_<hora>.txt` que el
script escribe junto a sí mismo — completo, con los errores incluidos si los hay. Cada línea de error es
una comprobación que D-A1 necesita ver fallar o pasar para poder darse por buena (R3); un resumen no
sirve.

**Aviso de honestidad:** este script se ha revisado a mano y se comprobó que sus llaves, paréntesis y
corchetes están balanceados, pero **no se ha podido ejecutar ni sintáctica-comprobar con un intérprete
PowerShell real** — este entorno de ingeniería es Linux y no tiene PowerShell instalado. Si al ejecutarlo
sale un error de sintaxis (no de lógica — de que PowerShell rechace el script antes de arrancar), pégalo
igual: es una comprobación más que hay que ver fallar antes de darse por buena, y se corrige de inmediato.

**Qué significa cada fallo del script, sección por sección** (igual que en la revisión 2, ahora todo
dentro del mismo fichero de salida):

| bloque | lo que sale | qué significa |
|---|---|---|
| D-A1.0 | ninguna ruta encontrada | NT8 no está instalado ahí — el propio script busca exhaustivamente en `C:\` como último recurso |
| D-A1.0 | `ProcessorArchitecture: X86` | **solo carga desde un proceso de 32 bits.** Python de 64 bits no podrá cargarla con `pythonnet` directamente — usar Python de 32 bits, o descartar el Camino A |
| D-A1.0 | `BadImageFormatException` | mismatch de bitness entre esta PowerShell y la DLL — repetir **todo el script** con la PowerShell de la otra arquitectura (`%windir%\SysWOW64\WindowsPowerShell\v1.0\powershell.exe` para 32 bits) |
| D-A1.0 | `ImageRuntimeVersion: v4.0.30319` | .NET **Framework** 4.x — para el Camino A, usar la rama de `pythonnet` compatible con Framework, no la de .NET Core/5+ |
| D-A1.1 | ninguna clase expone un método estático `SetUp` | revisar a mano la lista completa de tipos que el propio script ya volcó — el nombre real no está cubierto por ninguna fuente de este paquete |
| D-A1.1 | `SetUp()` funciona pero `Connected` da error de "ATI no habilitada" | falta marcar `Tools → Options → Automated Trading Interface → «AT Interface»` en NT8 |
| D-A1.1 | `Connected` devuelve falso/0 con la ATI ya habilitada | NT8 abierto pero sin ninguna cuenta conectada — comprobarlo en la interfaz de NT8 antes de repetir |
| D-A1.2 | cero cambios en 60 s | código de contrato mal formado (revisar el vencimiento vigente), o mercado cerrado en ese momento |
| D-A1.2 | cambia con cadencia de segundos | suficiente para el laboratorio de horquilla — no hace falta NinjaScript adicional |
| D-A1.2 | error al suscribir | puede ser falta de datos de mercado contratados para MES en esa cuenta |

### D-A1.3 · Ciclo completo de orden en `Sim101` — mandar, sondear, cancelar, comprobar `OrderStatus`/`Filled`/`AvgFillPrice`

> **Orden corregido (revisión 2).** Esta comprobación iba después de tocar la cuenta MFF real; el
> operador la movió delante: **primero se valida el ciclo entero en `Sim101`, sin arriesgar nada**, y
> solo si sale limpio se repite lo mínimo contra MFF (D-A1.4) con la misma técnica de no-llenado.

**Objetivo:** cerrar el ciclo completo de §4 contra la plataforma real (aunque sea en cuenta simulada),
con una orden de tamaño mínimo.

**Comando:** en `Sim101`, mandar una orden límite lejos del mercado (para poder cancelarla con margen —
elegir un precio claramente fuera del `bid`/`ask` actual, comprobado a ojo en NT8 antes de enviarla),
sondear `OrderStatus` cada segundo, cancelar, sondear de nuevo.

**Salida esperada:** secuencia `ENVIADA → ACEPTADA → CANCELADA` (o `→ LLENA` si por lo que sea se dejó
demasiado cerca del mercado), con `Filled`/`AvgFillPrice` devolviendo valores coherentes solo si hubo
llenado.

**Qué significa cada fallo:**

| lo que sale | qué significa |
|---|---|
| `OrderStatus` nunca cambia de "ENVIADA" | o el sondeo es demasiado lento, o la orden nunca llegó al bróker — revisar si aparece en el Control Center de NT8 |
| `Filled`/`AvgFillPrice` dan valores antes de que `OrderStatus` diga "LLENA" | las funciones no son consistentes entre sí — anotarlo, cambia el orden de lectura fijado en §4 |
| cancelar no cambia el estado | posible carrera cancelar-vs-fill — anotar cuánto tiempo pasó entre mandar y cancelar; **esto es exactamente lo que §5.3 (revisión 2) tiene que manejar**, así que si ocurre aquí es información valiosa, no solo un fallo |

**No seguir a D-A1.4 hasta que esta salga limpia.**

### D-A1.4 · `Command` funciona contra la cuenta de MFF vía Tradovate — mínimo, sin exponer capital

> **Corrección de seguridad (revisión 2), pedida explícitamente por el operador: NO se manda una orden
> real sin cobertura a la cuenta MFF solo para comprobar un nombre de cuenta.** Se usa la misma técnica
> que D-A1.3 — límite lejos del mercado, pensada para no llenar — y si por lo que sea llena de todos
> modos, se aplana esa misma posición de inmediato, a mano, en la propia interfaz de NT8, sin esperar a
> que el bot exista.

**Objetivo:** verificar la premisa de §1.1 del prompt — las dos patas conviven en la misma instancia,
MFF enrutado por Tradovate — y que `Command` opera contra la cuenta MFF real, no `Sim101`, **sin dejar
una posición prop desnuda sobre una cuenta de evaluación pagada**.

**Comando** (usar el nombre de cuenta MFF **copiado literal** del Control Center de NT8, nunca
adivinado; mismo precio-lejos-del-mercado que D-A1.3):
```powershell
$cuentaMFF = "<nombre exacto de la cuenta MFF en NT8 -> Control Center -> Accounts>"
$r = $tipo::Command("...", $cuentaMFF, "MES <contrato>", "...")   # firma real de D-A1.1; precio límite
                                                                    # lejos del mercado, igual que D-A1.3
# sondear OrderStatus; en cuanto se confirme ACEPTADA en la cuenta correcta, CANCELAR de inmediato.
```

**Salida esperada:** confirmación de orden aceptada por esa cuenta específica, visible también en el
Control Center de NT8 en la pestaña de esa cuenta — y luego cancelada limpiamente, sin llegar a llenar.

**Qué significa cada fallo:**

| lo que sale | qué significa |
|---|---|
| la orden aparece en `Sim101` en vez de en la cuenta MFF | el nombre de cuenta pasado no es el correcto, o el enrutado MFF/Tradovate no es el que asume §1.1 del prompt — **parar y preguntar antes de seguir**: es la premisa que sostiene toda la arquitectura de dos patas en una sola instancia |
| "cuenta no encontrada" | el nombre no coincide exactamente (mayúsculas, espacios) con el de NT8 |
| "trading no habilitado" / error de permisos | la cuenta puede estar en solo-lectura, o el plan de MFF contratado no enruta como se esperaba (pregunta al operador, §6.2 del prompt) |
| **la orden llena antes de poder cancelarla** | aplanar esa posición de inmediato a mano en NT8; anotar cuánto tardó en llenar (dato útil: significa que el margen de precio elegido no era suficientemente lejano) y repetir con un precio más alejado |

### D-A1.5 · Comparación empírica Camino A vs Camino B — alcance reducido (revisión 3)

> **Corrección de alcance, pedida por el operador.** La revisión 2 decía "repetir D-A1.1 a D-A1.4 dos
> veces". No: **no hay motivo para tocar la cuenta MFF dos veces solo para comparar A contra B** — D-A1.4
> ya es, de por sí, la comprobación mínima e imprescindible contra MFF; repetirla por partida doble
> (una por camino) dobla el riesgo sin añadir información nueva sobre cuál de los dos caminos es mejor.

**Objetivo:** decidir §2 con evidencia, no a priori. Repetir **solo D-A1.1** (reflexión + `SetUp`/
`Connected`) dos veces — una cargando la DLL con `pythonnet` desde Python, otra desde un
`dotnet new console` mínimo que referencia la DLL y compila con `dotnet build`. **Como mucho**, si D-A1.1
no basta para decidir, repetir también D-A1.3 (el ciclo completo de orden, pero en `Sim101`, nunca en
MFF) por cada camino. D-A1.4 (MFF) se corre **una sola vez**, con el camino que ya haya ganado — no una
vez por camino.

**Salida esperada:** para cada camino, si carga limpio, si `SetUp`/`Connected` funcionan igual, y
cuánto esfuerzo de configuración (versión de `pythonnet`, variables de entorno, `runtimeconfig.json`…)
hizo falta.

**Qué significa cada fallo:**

| lo que sale | qué significa |
|---|---|
| `pythonnet` no carga la DLL (bitness/.NET no coincide) | confirma el riesgo ya señalado en §2 — Camino B pasa a ser la propuesta firme, no solo la de partida |
| `pythonnet` carga limpio | Camino A queda como candidato serio; comparar esfuerzo de mantenimiento contra B antes de decidir |
| `dotnet build` falla al referenciar la DLL | anotar el error exacto — puede ser una cuestión de `<PlatformTarget>` en el `.csproj` que hay que fijar según D-A1.0 |

---

## 9 · Riesgo — sin soporte oficial

NinjaTrader lo dice explícitamente: *"Support for the API is limited from NinjaTrader Support. We are
not able to assist with any code in an application external to NinjaTrader."* Si el puente se rompe con
una actualización de NT8, no hay a quién preguntar. Mitigaciones concretas:

- **D-A1 (§8) es una suite de regresión reejecutable.** Tras cualquier actualización de NT8, se vuelve
  a correr entera (el script `da1_diagnostico.ps1`) antes de confiar en el puente — no se asume que
  "seguirá funcionando".
- **"Contra qué build de NT8 se validó por última vez el adaptador" tiene sitio ya: `09_DESPLIEGUE.md`**
  (nuevo, anotado como entregable previo a Fase 2 en `05_ORDEN_DE_CONSTRUCCION.md` — no escrito todavía).
  Ese documento reunirá el registro de build validado, el watchdog de proceso (§7), el arranque
  automático y los permisos de despliegue. No es un asunto de este documento (D-A cubre el contrato con
  la plataforma, no el despliegue de la propia caja del bot).
- El Camino B aísla el riesgo en un proceso pequeño e inspeccionable: si algo rompe, el radio de
  diagnóstico es ese proceso, no todo el bot.

---

## 10 · Glosario

| término | qué es |
|---|---|
| **ATI** | Automated Trading Interface de NT8: permite control externo sin escribir NinjaScript. Se habilita en `Tools → Options → Automated Trading Interface → «AT Interface»` |
| **`NinjaTrader.Client.dll`** | interfaz .NET gestionada de la ATI, en `…\NinjaTrader 8\bin\`. Es la que se usa |
| **`NtDirect.dll`** | interfaz nativa C/C++, herencia NT7, en `SysWOW64`. **No se usa** |
| **OIF** | interfaz de ficheros de la ATI — trivial pero sin realimentación útil de fills/posición; descartada como canal principal (§2) |
| **MSIL / x86 / Amd64** | arquitectura de un ensamblado .NET: agnóstica de bits, solo 32 bits, o solo 64 bits respectivamente |
| **reflection-only load** | cargar un ensamblado .NET solo para leer su metadata (tipos, firmas), sin ejecutar código ni resolver dependencias — evita fallos de bitness al inspeccionar |

---

## 11 · Decisiones abiertas

| tema | estado |
|---|---|
| Nombre real de la clase y firmas exactas de la ATI | pendiente de `da1_diagnostico.ps1` (§8) |
| Camino A vs B | propuesta de partida B; decisión firme pendiente de D-A1.5 (alcance reducido en revisión 3: solo D-A1.1, como mucho D-A1.3 en `Sim101`) |
| Valor definitivo de `N` (timeout pata prop) | provisional 5 s; definitivo = p99,9 de la latencia medida en Fase 2 |
| Valor definitivo de `N_hedge` (timeout confirmación del hedge) | **RESUELTO (revisión 3): provisional 30 s — asimetría invertida frente a `N` (§5.2b). El percentil exacto para el valor definitivo no está fijado; se decide en Fase 2 con los datos delante.** |
| Simetría en el cierre | **RESUELTO (revisión 3): formalizado en §5.4 — mismo principio que la apertura, sin caso nuevo.** |
| Supervisor externo (watchdog) para una caída del bot/puente a media sesión | **RESUELTO dónde vive (revisión 3): `09_DESPLIEGUE.md`, anotado como entregable previo a Fase 2 en `05_ORDEN_DE_CONSTRUCCION.md`. El documento en sí no está escrito todavía — no le toca aún.** |
| Umbral de alerta sobre la divergencia de precio de fill entre las dos patas (§5.3) | evento a registrar desde ya; el umbral en sí es un número que hace falta medir — candidato para `08_LABORATORIO.md` (D-B) |
| Disposición de cuenta bloqueada (R-2.4) | resuelta como alerta-y-espera-siempre con escalada a 5 días; implementación en D6, no aquí |
| ¿Liquidar deliberadamente un linaje bloqueado vs dejarlo morir por inactividad? | sin medir; pasa a decisiones abiertas de `08_LABORATORIO.md` |
| Catálogo de códigos de error de la ATI | vacío hasta `da1_diagnostico.ps1` + D-A1.3/D-A1.4; se rellena con valores reales, no se inventa |

---

## 12 · Historial de verificación

- **19-08-2026, revisión 1** — documento redactado contra `PROMPT_INGENIERIA_NT8.md` y el paquete de
  ingeniería v10 (`01_ESPECIFICACION_E2E.md`, `02_ARQUITECTURA.md`, `03_CONFIG.yaml`), con las seis
  comprobaciones de integridad del paquete ejecutadas y verdes. No llegó a validarse contra NT8 real.
- **19-08-2026, revisión 2** — el operador revisó la revisión 1 **antes de correr nada** contra NT8 y
  encontró un fallo grave: §5.3 podía aplanar el hedge mientras la orden de la prop seguía viva,
  produciendo justo el "una sola pata" que §6 llama el fallo más caro posible (carrera
  cancelar-vs-fill). Corregido: cancelar-y-confirmar-terminal antes de tocar la otra pata, en las dos
  direcciones (hedge→prop y prop→hedge), con el caso ambiguo resuelto aplanando ambas. Además: añadido
  `N_hedge` (§5.2b, sin valor, pregunta abierta); añadida la fila de reinicio a media sesión en §6 y la
  de caída del bot/puente en §7; añadido el aviso de instrumento MES-en-las-dos-patas (§1); invertido y
  corregido el orden de D-A1.3/D-A1.4 (§8) para no exponer capital de MFF sin cobertura solo para
  probar un nombre de cuenta. **Sigue sin validarse contra NT8 real.** D-A1.0, D-A1.1 y D-A1.2 (los que
  no dependen de las correcciones de arriba) están autorizados a correr ya; D-A1.3 en adelante espera a
  que esta revisión quede aprobada, porque ahora asumen el flujo corregido de §5.3.
- **19-08-2026, revisión 3** — **el operador aprobó la revisión 2** ("las cuatro correcciones son
  correctas") y resolvió las tres preguntas que quedaban abiertas: `N_hedge` = 30 s provisional, con la
  asimetría invertida frente a `N` razonada en §5.2b; la simetría del cierre formalizada en la nueva
  §5.4 (mismo principio que la apertura — nunca tocar la pata confirmada mientras la otra no esté en
  estado terminal — sin caso nuevo); y el watchdog de proceso movido a un `09_DESPLIEGUE.md` nuevo
  (anotado en `05_ORDEN_DE_CONSTRUCCION.md` como entregable previo a Fase 2, no escrito todavía — no es
  D9, que son aserciones de un proceso vivo, no de uno muerto). Además, tres retoques: (1) la rama
  4b-LLENA de §5.3 (y su análoga 2b-LLENA) ahora registra los dos precios de fill y su diferencia como
  evento de laboratorio, candidato a umbral en `08_LABORATORIO.md`; (2) D-A1.5 reduce su alcance — solo
  D-A1.1 por camino, como mucho D-A1.3 en `Sim101`, D-A1.4 contra MFF una sola vez, no una por camino;
  (3) D-A1.0/D-A1.1/D-A1.2 se empaquetaron en un único script, `da1_diagnostico.ps1`, que vuelca todo a
  un fichero en una sola ejecución. **Sigue sin validarse contra NT8 real** — sigue siendo el próximo
  paso, en cuanto haya máquina disponible. Mientras tanto, el trabajo se reordenó para agotar el camino
  crítico sin plataforma: D0 (hecho, puerta verde) y D1 en curso, `08_LABORATORIO.md` después, y D2-D7
  con brókers simulados — nada de eso depende de NT8 real.
- **20-08-2026, revisión 4** — el operador revisó la entrega de D-C (`REVISION_ENTREGA_20260820.md`)
  reproduciendo todas las puertas (todas verdes) y, además, encontró **tres defectos reales** en el
  camino crítico del protocolo de las dos patas, no cubiertos por las pruebas existentes hasta ahora.
  Corregidos los tres en `bot/protocolo_dos_patas.py`, con comprobación R3 nueva
  (`verificacion_R3/prueba_protocolo_dos_patas.py` §§8-10, 40/40 verde) y reflejados aquí:
  **Defecto 1** — el sondeo de 2/4 solo esperaba `LLENA`, así que un `RECHAZADA`/`CANCELADA` limpio e
  inmediato del bróker (información cierta, no ambigua) se trataba igual que "el timeout expira",
  agotando `N`/`N_hedge` enteros sin necesidad y, en el caso de la prop, dejando el hedge desnudo ese
  tiempo de más — corregido con las ramas nuevas 2b'/4b' de §5.3, sin alerta (no hace falta: es
  información limpia). **Defecto 2** — `hay_conexion()`, exigido por el contrato del puerto (§1) "antes
  de cada operación", nunca se llamaba en la práctica antes de la primera orden de una apertura —
  corregido con el paso 0 nuevo de §5.3, exclusivo de la apertura (el cierre sigue sin abortar por
  conexión caída, por la asimetría ya fijada en §7). **Defecto 3** — el reintento de cierre de una pata
  (§5.4) decidía si había terminado mirando el estado de la ÚLTIMA orden mandada, no la posición real de
  la cuenta; si el bróker rechaza una orden de cantidad cero (posición ya plana) en vez de aceptarla como
  no-operación, el reintento podía no converger nunca — corregido para que la condición de salida sea
  siempre `leer_posicion()`, comprobada también ANTES de intentar aplanar (así una cuenta ya plana no
  manda ninguna orden). Ninguna de las tres correcciones cambia el orden de "las dos patas o ninguna" que
  fijan las revisiones 2-3 — son endurecimientos del mismo principio, no una revisión de él. **Sigue sin
  validarse contra NT8 real.**
- **20-08-2026, revisión 5** — a petición del operador ("un simulador de NT8 independiente que responda
  como él, para probar todos los mecanismos simulando sus respuestas"), se construyó
  `simulador_nt8/`: un proceso de sistema operativo APARTE del bot, que expone el mismo contrato de
  puerto de §1 sobre un socket `AF_UNIX` local, envolviendo `bot/adaptador_falso.py` sin reimplementar su
  máquina de estados. Ocho fases de construcción, cada una con su propia comprobación R3 en
  `verificacion_R3/integracion_proceso_real/`, cada pieza vista fallar contra una reconstrucción
  deliberadamente rota antes de aceptar la real (protocolo de framing, servidor mínimo, paridad
  método-a-método contra `AdaptadorFalso`, ganchos de congelación/retraso, servidor muerto a mitad de
  orden, bot muerto con posición real y reconciliación de §6 en las dos direcciones — caso feliz y
  descuadre —, timeouts `N`/`N_hedge` con reloj de pared real, vigía detectando un proceso realmente
  detenido con `SIGSTOP`). El proceso de construcción cazó varios bugs reales antes de entregar: (1) el
  canal de control no traducía el prefijo `test_` al nombre real de las fábricas de `AdaptadorFalso`
  (`desconecta`, `fuerza_fill`, etc., que no llevan ese prefijo); (2) reconstruir una excepción remota a
  partir de su `str()` en vez de sus `args` originales producía un `repr()` anidado en `KeyError` (su
  propio `__str__` ya aplica `repr()`); (3) el propio arnés de pruebas mínimo consultaba la posición del
  hedge bajo el literal `"MES"` en vez de `cfg.hedge_broker.instrumento` real
  (`'MES (Micro E-mini S&P 500)'`), lo que habría hecho que la reconciliación de §6 declarase "descuadre
  fatal" incluso con todo perfectamente cuadrado. **No toca `adaptadores/` (sigue bloqueado por D-A1) ni
  acerca nada a la validación contra NT8 real** — ver `simulador_nt8/LEEME.md` para el aviso completo y
  la nota nueva en §8.
- **20-08-2026, revisión 6** — el propio simulador se sometió a una revisión adversarial de cinco lentes
  independientes (fidelidad al puerto, concurrencia/estado, seguridad/robustez, calidad de la propia
  suite R3, salvaguarda anti-confusión), cada hallazgo re-verificado por un segundo revisor escéptico que
  reprodujo o refutó cada uno con código real, no de oídas. **Ocho hallazgos confirmados, los ocho
  corregidos y re-verificados:**
  1. Un argumento no serializable a JSON (p.ej. el hook `en_cancelar`, exclusivo del doble en proceso)
     dejaba escapar un `TypeError` crudo de `json` en vez de una excepción con tipo conocido — corregido
     (`simulador_nt8/errores.py::ArgumentoNoSerializable`, `protocolo.py::escribir_mensaje`) — y se cerró
     el hueco de cobertura real que esto señalaba: la carrera cancelar-vs-fill de §5.3 nunca se había
     fabricado cruzando la frontera de proceso — ahora sí, vía `test_retrasar_respuesta`+`test_fuerza_fill`
     desde otra conexión (`verificacion_R3/integracion_proceso_real/prueba_carrera_cancelar_vs_fill.py`).
  2. Reconstruir una excepción remota multi-argumento con tipos no serializables (p.ej.
     `UnicodeDecodeError`) podía lanzar un `TypeError` de aridad que sustituía el error real — corregido
     con una degradación segura en `cliente.py::_reconstruye_error` (no alcanzable hoy con
     `AdaptadorFalso`, pero el mecanismo es genérico y el defecto era real).
  3. **Sin ningún lock protegiendo `AdaptadorFalso`** frente a llamadas concurrentes del canal de datos y
     el canal de control — reproducido de forma determinista (interleaving forzado, 100% de pérdida) y
     probabilística (24 000 operaciones concurrentes, pérdidas reales) como corrupción silenciosa de
     `posiciones`. Corregido con `threading.RLock` en `motor.py` envolviendo todo acceso a `AdaptadorFalso`
     desde los dos canales, con `test_congelar`/`test_liberar_congelacion` explícitamente excluidos del
     lock para no introducir un interbloqueo con el propio mecanismo de congelación — re-verificado: 0
     pérdidas en 24 000 operaciones concurrentes tras el arreglo.
  4. **El canal de control exponía, sin lista blanca, cualquier atributo de `AdaptadorFalso` alcanzable
     con el prefijo `test_`** — incluidos los dunder: `test___init__` reseteaba todo el estado simulado en
     caliente, sin aviso, `ok:true`. Corregido con `MotorSimulado._FABRICAS_PERMITIDAS`, una lista cerrada
     de las cuatro fábricas reales — re-verificado en vivo que los cuatro dunder probados quedan
     rechazados y las fábricas legítimas siguen funcionando.
  5. `arnes_bot_minimo.py::reconcilia()` ignoraba `estado_previo["abierto"]` — una posición residual real
     con `abierto=False` (07_ADAPTADOR_NT8.md §6, fila 2: "un cierre anterior no se completó o no se
     registró") se declaraba "RECONCILIADO, todo cuadra" (fila 5) en vez de alertar. Corregido y cubierto
     con un escenario R3 nuevo (Fase 5e) que fabrica exactamente ese descuadre.
  6. Fuga de proceso zombi en `prueba_bot_muere_y_reconcilia.py` si la propia prueba fallaba a mitad
     (los `Popen` del bot nunca se referenciaban en el `finally`) — corregido.
  7. Dos aserciones de límite unilateral (`dt >= X`, sin cota superior) que no distinguían un retraso
     correcto de uno pegado — corregidas con banda de tolerancia, mismo patrón que
     `prueba_timeout_reloj_real.py`.
  8. Una condición de carrera real en `MotorSimulado._retraso_pendiente` (indexado solo por nombre de
     método, sin relación con qué petición lo armó) causaba que `prueba_ganchos_control.py` fallara de
     forma intermitente (~25% de las corridas) cuando un hilo servidor ya en vuelo se "robaba" un retraso
     armado para una petición nueva — corregido con una marca de tiempo de armado — re-verificado: 0
     fallos en 20 corridas consecutivas (antes, ~25% de fallo esperado en esa misma ventana).
  Batería completa de `verificacion_R3/integracion_proceso_real/` (ahora 9 ficheros, 83/83) y toda la
  batería original (D0, D1, Fase 1, D2, `romper_mi_orquestador.py`, `prueba_protocolo_dos_patas.py`,
  `prueba_comandos.py`, `prueba_dashboard.py`, paleta) re-verificadas en verde tras estos cambios. Ninguno
  toca `adaptadores/`, `tests/`, ni `modelo/`.
