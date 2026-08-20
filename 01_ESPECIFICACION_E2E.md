# 01 · ESPECIFICACIÓN E2E · circuito cubierto v10
### **LA NORMA.** Manda sobre el código, sobre los tests y sobre tu intuición.
Congelada el 19-08-2026. Núcleo ejecutable equivalente: `tests/nucleo_referencia_v10.py`.

> **Cómo usar este documento.** Cada regla tiene un identificador (`R-x.y`). Cuando pidas
> un delta a la sesión de ingeniería, **pega la sección entera**, no la resumas. Si una
> regla te parece rara, no la "arregles": está así porque se midió. Si crees que hay un
> error en la norma, **para y pregunta** — no la cambies tú.
>
> **Precedencia.** Esta norma manda sobre **tu** código y sobre los tests que tú escribas.
> Pero entre esta norma, `tests/nucleo_referencia_v10.py` y `modelo/pipeline3.py` **no hay
> jerarquía**: son tres expresiones de la misma cosa y hoy coinciden en 60.000 estados
> (`tests/prueba_nucleo_vs_motor.py`). Si algún día divergen, **para y pregunta**; no elijas
> tú a cuál obedecer.

---

## 0 · Notación

| símbolo | qué es | unidad |
|---|---|---|
| `k` | contratos abiertos en la cuenta de la prop | contratos |
| `m` | micros MES abiertos en el bróker real, dirección **contraria** | micros |
| `bal` | balance de la cuenta prop (empieza en 0 cada ciclo) | USD ficticios |
| `pk` | pico histórico de `bal` en el ciclo | USD ficticios |
| `s₀` | coste hundido vivo del linaje (lo que se lleva pagado y no recuperado) | USD reales |
| `H` | P&L acumulado del hedge de **este** linaje | USD reales |
| `B` | buffer (dial de sala diaria), distinto en eval y en funded | USD reales |
| `G` | objetivo de recuperación del hedge | USD reales |
| `fric` | fricción del hedge por sesión = `SPR · m` | USD reales |
| `MLL/DLL/LOCK` | límites del proveedor: 2000 / 1000 / 100 | USD ficticios |
| `Mm` | margen vivo: cuánto puede perder la cuenta hoy antes de morir | USD ficticios |
| `nu` / `ndn` | distancia al objetivo / al suelo, en **puntos** del índice | puntos |
| `pv` | valor del punto de la posición prop = `5·k` | USD/punto |

Todos los números concretos están en `03_CONFIG.yaml`. **En esta especificación no hay
literales de negocio**: donde aparece uno es como ejemplo y va marcado.

---

## 1 · QUÉ ES EL SISTEMA (y qué NO es)

**R-1.1 · El mecanismo.** Se compran suscripciones de evaluación a una prop firm. El
capital de esas cuentas es **ficticio**. Sobre cada cuenta se abren `k` contratos y, en un
bróker real, `m` micros MES en **dirección contraria**. La dirección diaria **se sortea**:
el sistema **no predice nada**.

**R-1.2 · De dónde sale el dinero.** De dos sitios, y solo de dos:
1. **El buffer cosechado en cada muerte.** Cuando la cuenta prop muere, el hedge —que iba
   al contrario— ha ganado `h = m·DLL/k − fric`. El sizing está calculado para que ese
   `h` cubra el coste hundido del linaje **más** `B`.
2. **Los payouts del proveedor** cuando una cuenta fondeada sobrevive y cobra.

**R-1.3 · Lo que NO es (y se dijo mal durante semanas).**
- El libro del hedge marca **negativo** y eso **no es una pérdida**: es el **precio de
  compra** de los payouts. Medido sobre v10 (`modelo/cifras_citadas.py`, $/mes, el cuadre
  cierra con residuo 0,0000):

  | flujo | $/mes |
  |---|---|
  | payouts cobrados | **+2.408** |
  | cuotas de suscripción pagadas | **−947** |
  | **P&L del hedge** | **−262** |
  | **caja del sistema** | **+1.198** |

  El hedge financia 2.408 $ de payouts y su libro solo marca −262: la diferencia es lo que
  recupera en las muertes. *(La descomposición por linajes que se publicaba antes —
  2.099 / 1.983 / buffer 752 — era de la config v9.1. Bajo v10 no está regenerada: sigue en
  la lista de pendientes.)*
- Los dos flujos **no son paralelos**: la cuenta prop solo sube si el hedge baja. Es el
  mismo dinero en direcciones opuestas.
- **El EV entero está condicionado a que el proveedor pague.** Quitando los payouts y
  dejando todo lo demás igual, el sistema pasa de **+1.198 a −1.203 $/mes** con 99 % de
  probabilidad de degradar. El buffer no es un flujo independiente.

**R-1.4 · No hay ninguna señal, indicador, filtro ni modelo de mercado.** Si en algún
momento el código que construyes contiene algo que decide *cuándo* entrar en función del
*precio*, has salido de la especificación. La única decisión de calendario está en R-6.

---

## 2 · SIZING · la identidad de cobertura

Esta es la única matemática que de verdad importa. Se resuelve **una vez por cuenta y
sesión**, antes de abrir nada.

**R-2.1 · Suelo vivo y margen del día.**
```
fl = min(pk − MLL, LOCK)          # el trailing se congela en LOCK
Mm = bal − fl                     # lo que la cuenta puede perder hoy antes de morir
Ms = min(DLL, Mm)                 # el tope diario efectivo
```

**R-2.2 · El objetivo de recuperación.**
```
G   = max(s₀, 0) + B
den = G − H + fric
```
`den` es **lo que el hedge todavía tiene que ganar** para cerrar el linaje en `B`.

**R-2.3 · El número de contratos (dos pasadas — la cuña de comisión).**
```
k₀ = floor( min( m·Mm / den , kcap ) )
k₁ = max(k₀, 1)
k  = floor( min( m·(Mm − CMS·k₁) / den , kcap ) )        # ← el k que se usa
si den ≤ 0:  k = kcap
```
**La segunda pasada NO es un refinamiento opcional.** Sin ella la comisión se come el
margen y la salida EOD dispara la muerte un tick antes de lo previsto. `tests/goldens_v10.json`
tiene casos que lo discriminan.

**R-2.4 · Regla del bloqueo (antes «Regla 4.3»).**
```
si k < 1  →  la cuenta NO OPERA hoy:  dx = 0, comisión = 0, hedge = 0,
             no muere, no pausa, no alcanza objetivo.
```
La condición exacta, con la cuña de comisión de R-2.3 aplicada, es:
```
den > m·(Mm − CMS·k₁)
```
Es decir, el linaje ha acumulado tanta deuda que **ya no puede morir con beneficio**.

El **techo de recuperabilidad** se enuncia a menudo como `den ≤ m·DLL`; eso vale
**solo mientras `Mm ≤ DLL`**, que es la situación al borde de la muerte. En general el techo
es `den ≤ m·(Mm − CMS·k₁)`. Con `m=3` sale ≈ 3.000 $ de deuda máxima por linaje.

**El bloqueo es ABSORBENTE, y esto hay que entenderlo bien.** Si la cuenta no opera, `bal`
no se mueve, `Mm` no se mueve, `H` no se mueve y `s₀` no se mueve: **mañana el bloqueo se
repite exactamente igual**. No hay salida por sí sola. Y a los ~7 días la **regla de
inactividad del proveedor** mata la cuenta — **sin hedge abierto**, es decir **sin cosechar
el buffer**. El carry del linaje se pierde entero.

Medido (auditoría del 18-08, config v8): ocurre en fondeadas de los ciclos 2-4, en
~**0,5 % de los linajes**, con `den` mediana 6.287 $, y cuesta **375 / 395 / 735 $** de
carry perdido por réplica-año (iid / crono / pesimista). En la traza de referencia de 504
días ocurre **1 vez**.

**Rescates ya probados y RECHAZADOS** (crono, EV / p5 / P(degradar), base = 1.910 / 975 / 2,80 %):

| rescate | EV | p5 | P(degradar) |
|---|---|---|---|
| forzar `k = 1` | 1.882 | 772 | 5,67 % |
| subir `m` al bloquear | 1.870 | 511 | 7,87 % |
| `m` estructural `⌈den/DLL⌉ ≤ 6` | 1.928 | 751 | 7,37 % |

Causa: el coste por punto de avance es `m/k`; subir `m` con `k ≈ 1` **duplica el precio del
progreso** y el margen extra solo pesa 0,27 pp.

> **Ojo de ingeniería:** el bloqueo es un **estado planificado**, no un error. No lo
> conviertas en parada del bot ni lo loguees como excepción — pero **sí tiene que alertar**,
> porque la disposición de una cuenta bloqueada **es una decisión del operador que todavía
> no está tomada** (ver §8). Si tu bot lo dispara a menudo, tienes un bug en `s₀` o en `H`.

**R-2.5 · Distancias.**
```
pv  = 5·k
cst = CMS·k                                     # comisión round trip de la prop
top = min( T − bal + cst , dcap + cst )
nu  = min( max(top, 1e−9)/pv , EXP/(5·m) )      # distancia al objetivo, en puntos
ndn = DLL·fsuelo / pv                           # distancia al suelo, en puntos (modo EOD)
```
`EXP` es el tope de exposición del hedge: acota la pérdida real máxima del día por cuenta.

**R-2.6 · El buffer NO es un colchón.** Estructuralmente `ndn = DLL/(5k)` y
`k ≈ m·Mm/(s₀+B)`, luego **`ndn ∝ (s₀+B)/Mm`**. `B` fija literalmente **a qué distancia
está la parada diaria**. Consecuencias medidas:
- Soltar `B` en los días en que la muerte es "imposible" parece gratis y es **ruinoso**.
  Medido sobre la config v10 (8 semillas, crono, R=3000 — `modelo/cifras_citadas.py`):

  | | EV $/mes | p5 | P(degradar) |
  |---|---|---|---|
  | base | 1.198,5 | 797,2 | 1,10 % |
  | soltando `B` los días "seguros" | **1.069,2** | **88,5** | **17,19 %** |

  Al soltar `B`, `k` se dispara, el suelo se pega al precio y la cuenta muere en dos
  sesiones sin acercarse al objetivo. *(La cifra que se publicaba antes — 1.194 → 946,
  P 24,53 % — era de la config v9.1 y no aplica a v10.)*
- Lo que sí funciona es **separarlo por fase**: la eval quiere `B` pequeño (velocidad),
  la fondeada lo quiere grande (supervivencia).

---

## 3 · LA SESIÓN · qué pasa dentro de un día

**R-3.1 · Entrada.** Se entra **al cierre de la barra `b0`** y se vigila **desde `b0+1`**.
**Nunca se evalúa la propia barra `b0`.**

> Esto no es un detalle. Evaluar `b0` (look-ahead) costaba el **13,6 % del titular** y fue
> uno de los dos bugs que un auditor externo encontró y los tests no. `tests/goldens_v10.json`
> tiene tres casos `LOOKAHEAD_*` que **fallan** si lo implementas mal.

**R-3.2 · Barrido.** Recorriendo `b` desde `b0+1` hasta `NB−1`:
```
iD = primera barra con  (pl[b] − p0) ≤ −ndn          # toca el suelo
iU = primera barra con  (ph[b] − p0) ≥  nu           # toca el objetivo
```
Si ninguna dispara, el día cierra al último `pc`.

**R-3.3 · Resolución y desempate.**
```
low = (iD ≤ NB) y (iD ≤ iU)        # ← EL SUELO GANA EL EMPATE
tgt = (iU ≤ NB) y (iU <  iD)
dx  = −ndn      si low
       nu       si tgt
       pc[NB−1] − p0   en otro caso
```
**El suelo gana el empate.** Si en la misma barra se tocan los dos, se resuelve como suelo.
Es la hipótesis conservadora y es la que está medida.

**R-3.4 · Muerte (regla EOD).**
```
muere = ( dx·pv − cst ≤ −(Mm − 1e−9) )
pausa = low y no muere
```
La salida de suelo es **siempre al DLL**. La cuenta **solo muere** si la pérdida
**realizada** (la pausa diaria, o el cierre del día) perfora el suelo vivo. Un día de
suelo con `Mm > DLL` **no mata la cuenta**: la pausa y sigue mañana.

**R-3.5 · P&L del hedge.**
```
h = −5·m·dx − fric
si muere:  h = h − deslizamiento          # deslizamiento = slip_micro · m
```
El deslizamiento **solo** se aplica en la salida de muerte, que es la que se ejecuta con
prisa. `slip_usd_micro` es un **SUPUESTO, no un dato**: nadie lo ha medido nunca (R-9.6).

**Cómo se lee esto — importa, porque es fácil leerlo mal.** Lo que absorbe el deslizamiento
es la **holgura** que deja el `floor()` de `k`: `holgura = m·DLL/k − den`. Como `k` es
entero, esa holgura está **cuantizada**, y en la evaluación toma prácticamente dos valores:

| | holgura mediana antes del deslizamiento |
|---|---|
| muerte de evaluación (`m=2`) | **8,45 $** |
| muerte de fondeada (`m=4`) | **24,07 $** |

Por eso el indicador «% de muertes con déficit» es una **función escalón** que salta de 0 a
47 a 82 % en cuanto el deslizamiento cruza esos dos valores. **No tiene contenido económico:
mide si se cruzó un escalón, no cuánto se pierde.** Lo que sí lo tiene:

| deslizamiento | % cierra bajo `B` | déficit **medio** | como % de `B` | **% cierra en NEGATIVO** |
|---|---|---|---|---|
| 0 (identidad pura) | 0,00 % | 0,00 $ | 0,0 % | **0 %** |
| 2,50 (VERDE, adoptado) | 0,03 % | 0,00 $ | 0,0 % | **0 %** |
| 5,00 | 46,79 % | 0,80 $ | 1,4 % | **0 %** |
| 6,25 (ÁMBAR) | **82,09 %** | **2,79 $** | **4,7 %** | **0 %** |
| 12,50 (ROJO) | 94,00 % | 17,44 $ | 29,4 % | **0 %** |
| 25,00 (el doble del rojo) | 97,95 % | 49,84 $ | 83,9 % | **6,98 %** |

> **El titular correcto no es «el 82 % de las muertes cierra con déficit».** Es: **en banda
> ámbar el buffer conserva el 95 % de su valor, y ningún linaje cierra en negativo hasta que
> el deslizamiento llega a 25 $/micro — diez veces el valor adoptado.**
>
> *(La cifra que se publicaba antes — 0,65 % en verde, 2,27 % en ámbar — no reproduce. Pero
> el indicador en sí estaba mal elegido, así que corregirlo no cambia nada material.)*

**Y el coste real del deslizamiento no sale de aquí, sale de una multiplicación.** El
deslizamiento se paga **entero en cada muerte**, tenga o no déficit:

```
coste = Δslip · (muertes_eval/mes · m_eval  +  muertes_funded/mes · m_fun)
      = 3,75 · (7,10 · 2 + 4,26 · 4)  =  117,1 $/mes      (verde → ámbar)
```
La tabla de estrés, medida por otro camino, da **116,0**. Y para verde → rojo: predicho
312,2 frente a **313,6** medidos. **El coste del deslizamiento es lineal en el número de
muertes y no tiene nada que ver con el porcentaje de déficits.**

**R-3.6 · La identidad, enunciada honestamente.** Todo linaje cierra en
**`B` menos el deslizamiento del evento** — no en `B` exacto.

Sin deslizamiento la identidad es **exacta**: `modelo/cifras_citadas.py` la comprueba en
**0 fallos sobre 68.413 muertes** (239.708 estados de sesión), y es reproducible desde el
paquete. Es una consecuencia de R-2.3: al morir, `Mm ≤ DLL + cst`, luego
`k ≤ m·DLL/den`, luego `h = m·DLL/k − fric ≥ den − fric = G − H`.

**R-3.7 · Una cuenta opera COMO MUCHO UNA VEZ POR DÍA.** Dos sesiones el mismo día solo
pueden ser **cuentas distintas** (la que murió y su empalme).

> Este es el otro bug histórico: en v8 el 92,3 % de las segundas sesiones eran la cuenta
> **superviviente** volviendo a operar. Costó el 34 % del titular. El invariante
> `sesiones_de_eval ≤ 1 + empalmes` del replay pack lo caza (275 disparos desde el día 2
> en el orquestador roto de contraste).

---

## 4 · CICLO DE VIDA DE UNA EVALUACIÓN

**R-4.1 · Compra.** Una suscripción cuesta `cuota_sub_usd`. Se mantiene un **pool** de
suscripciones compradas. Al arrancar un intento se toma una **fresca** del pool y se le
imputa `s₀ = cuota_sub_usd`.

**R-4.2 · Aprobación.** La eval aprueba cuando toca el objetivo **y** `bal ≥ objetivo_eval_usd`.
Al aprobar:
- El coste hundido restante `sunk = s₀ − H` pasa a la **recámara** (cuenta fondeada dormida).
- La suscripción aprobada se **cancela** (gratis) y se **recompra** una nueva para mantener
  el pool (`rebuy`), pagando `cuota_sub_usd`.

**R-4.3 · Muerte y empalme.** Si la eval muere **intradía** y la muerte ocurre antes de las
últimas `empalme_barra_limite` barras, el bot **empalma el mismo día** con una eval fresca
del pool, entrando en la barra del evento y **heredando el hedge** (misma dirección). El
intento empalmado paga **media fricción**.
- **Máximo 1 empalme por día.** Después del empalme no hay tercer intento.
- Si la muerte ocurre en las últimas barras, **no se empalma**: se espera a mañana.

**R-4.4 · Reset gratis.** Una suscripción **rota** espera el reset gratuito de su día de
facturación. En el modelo esto es una probabilidad diaria `reset_prob_diaria`. Al llegar,
la rota vuelve a **fresca**.

**R-4.5 · Emergencia.** Si el pool no tiene frescas y hay que arrancar un intento, se
**cancela una rota y se recompra** (`cuota_sub_usd`) para no dejar el slot vacío.

**R-4.6 · Tope de recámara (`qcap`).** No se abren intentos nuevos de eval si ya hay
`qcap` fondeadas dormidas. **Excepción:** el tope se levanta si la tesorería viva
(`caja − retirado`) alcanza `qcap_tes_usd`.

> **`qcap`, `qcap_tes` y la retención `C` están ACOPLADOS.** `qcap_tes` se compara contra
> la tesorería viva, que la retención `C` recorta cada mes. Subir `C` sin mover `qcap_tes`
> cambia el comportamiento del tope. **No toques uno sin los otros y sin re-optimizar.**

**R-4.7 · El modelo automatiza lo que en la realidad es manual.** Comprar, recomprar,
cancelar una suscripción, confirmar una aprobación y pedir un payout **no tienen API**: los
hace el operador en la web del proveedor. En el modelo ocurren solos y al instante; **en el
bot no**. El bot **alerta y espera**. Ver `02_ARQUITECTURA.md` §8.

> **Esto sesga el bot POR DEBAJO del modelo, no por encima.** Cada retraso humano es un día
> de slot vacío que el modelo no contabiliza. Si tu bot rinde **por encima** del modelo,
> asume que es un bug hasta demostrar lo contrario.

---

## 5 · CICLO DE VIDA DE UNA FONDEADA

**R-5.1 · Activación (relevo).** Hay **como mucho una fondeada activa**. Una dormida se
activa cuando: no hay activa, la espera de relevo ha vencido, y hay dormidas en recámara.
Al activarse hereda `s₀ = sunk_total / n_dormidas` (reparto del coste hundido).

**R-5.2 · La regla de espera del proveedor.** Regla escrita de MFF: si la cuenta activa se
suspende por romper una regla, la cuenta en reserva **solo puede activarse a partir del
siguiente día de negociación**. Como el bot activa en la apertura del día siguiente, la
espera **adicional** en el modelo es `relevo_dias = 0`.

> **`relevo = 0` NO significa "activa el mismo día".** Significa "activa mañana". Si lo
> implementas como D+2 (`relevo=1`), el replay pack te da **2.296 divergencias de estado**.

**R-5.3 · Días mínimos.** Una fondeada no puede cobrar antes de `dias_min_eval` días de
negociación en el ciclo (`f_nd ≥ 2`).

**R-5.4 · La escalera de cobros.** Cinco ciclos. En cada ciclo `c`:
```
T_c = buf + w_bruto   si c = 1
      w_bruto         si c > 1
W_c = split · w_bruto            # lo que se cobra
D_c = T_c · cons                 # tope de avance POR DÍA (dcap): limita cuánto
                                 # puede subir la cuenta en una sola sesión
```
Al cobrar: `caja += W_c`, `s₀ ← s₀ − H − W_c`, y se reinician `bal`, `pk`, `H`, `f_nd`.
Terminados los 5 ciclos la cuenta se cierra y arranca la espera de relevo.

**R-5.5 · Muerte de la fondeada.** Igual que R-3.4. Al morir: se desactiva, y arranca la
espera de relevo (R-5.2). El hedge cobra su `h` y con él el buffer.

---

## 6 · CALENDARIO Y DIRECCIÓN

**R-6.1 · Dirección.** Se sortea **50/50 CADA DÍA**, una sola vez para todo el sistema.
**Todas las cuentas comparten la dirección del día** (evita cruces internos).

**Regla CONTRA:** tras un día en el que murió alguna cuenta, la dirección del día anterior
**se mantiene** durante `contra_dias` días en lugar de re-sortearse. Es decir: hay sorteo
diario, y el contador CONTRA lo vetoa mientras está vivo.

> **No es "un sorteo al arrancar y ya".** Implementarlo así convierte el sistema en una
> apuesta direccional única mantenida durante meses, que es exactamente lo contrario de lo
> que hace. En la traza de referencia la dirección cambia 20 veces en los primeros 20 días
> y el reparto final es 225 cortos de 504. La puerta D3 lo caza.

**R-6.2 · Ventana.** Por defecto se opera la sesión completa de 22 h (`b0 = 0`). En los
días con dato macro relevante (fracción `frac_dias_dato`) se opera **RTH**: se entra
después del dato, en la barra `b0_rth`. **Nunca se duerme en víspera de dato**, así el
margen comprometido nunca supera `margen_usd`.

**R-6.3 · Campana.** El día operativo son `barras_por_dia` barras de 15 min: **se cierra en
T−20** (14:30 CT). No se lleva posición al cierre oficial.

---

## 7 · TESORERÍA Y PARADA

**R-7.1 · Muro dinámico.** Solo cuenta el capital **realmente comprometido hoy**:
```
muro = capital_usd − (m_fun·margen + exp_fun) − (micros_eval_hoy·margen + exp_eval_hoy)
```

**R-7.2 · Degradación.** Se declara **degradación** el primer día en que
`caja − retirado < −muro`. Es la métrica de riesgo del proyecto: `P(degradar)`.

**R-7.3 · Retiro mensual.** Cada `dias_por_mes` días de negociación se retira
`max(0, caja − retencion_c_usd − retirado)`. Lo retirado **sale del sistema**: no vuelve a
financiar operaciones.

**R-7.4 · Orden de activación de las dormidas — OJO, AQUÍ HAY QUE PREGUNTAR.**
El modelo **agrega** la recámara: al activar una dormida le imputa el coste hundido
**medio** (`sunk_total / n_dormidas`). Es decir, **el modelo no distingue una dormida cara
de una barata**, y por tanto **no ha medido** ninguna política de orden.

Se discutió un criterio de desempate («la más cara primero», porque es la que más
urgentemente necesita el payout que amortiza `s₀`).

**Lo que sí hay medido** (auditoría del 18-08, sobre la config **v8**, 112.585 aprobaciones):
el coste hundido por cuenta es **406 $ de media con desviación 34 $**. Con esa dispersión
tan pequeña, **el orden de activación es prácticamente indiferente** y ninguna dormida puede
bloquearse al activarse. Pero: (a) es una medida de v8, **no se ha rehecho en v10**, y (b) el
simulador de v10 agrega la recámara, así que la política **no se puede medir hoy**.

**Para el bot:** implementa la recámara **desagregada** (una lista de dormidas, cada una
con su `s₀` real) porque es lo correcto y lo que permitirá medirlo, pero **la política de
selección la decide el operador, no tú**. Hasta que se decida, usa **FIFO** y déjalo
detrás de una constante de configuración explícita.

---

## 8 · LO QUE ESTÁ FUERA DE LA NORMA (y hay que PREGUNTAR)

Estas cosas **no están especificadas** porque no están medidas. Si tu implementación
necesita decidir alguna, **para y pregunta**. No elijas tú.

| tema | estado |
|---|---|
| Latencia real de la orden del hedge | absorbida en `slip_usd_micro`; sin medida propia |
| Retardo de entrada el día 1 de una fondeada nueva (`b0_nuevo`) | **NO MEDIDO** — la conclusión anterior fue retractada |
| Fecha exacta de facturación de cada suscripción | el modelo usa tasa 1/30, no fechas |
| Comportamiento del trailing MLL en el instante exacto del cierre EOD | el modelo asume el cierre de la barra |
| Qué hacer con una cuenta **bloqueada** (R-2.4): dejarla morir por inactividad, o cerrarla deliberadamente | **DECISIÓN ABIERTA del operador.** Los tres rescates automáticos están medidos y rechazados |
| Qué hacer si el bróker rechaza la orden del hedge | **sin especificar** |
| Cuánto tarda de verdad el paso humano (recompra, confirmación de aprobación) | **no medido**: el modelo lo supone instantáneo (R-4.7) |
| Qué hacer si la prop y el bróker discrepan en el precio de referencia | **sin especificar** |
| Orden de activación de las dormidas (FIFO vs «la más cara primero») | medido en **v8** (dispersión 34 $ ⇒ indiferente), **no rehecho en v10**; el modelo agrega la recámara. Ver R-7.4 |

---

## 9 · LO QUE HACE FALTA QUE SEA CIERTO

La norma anterior asume estas cosas. Si alguna se cae, la cifra se cae con ella.
Base: `modelo/estres_v10.json`, contra `base` = 1.198,5 · p5 797,2 · P 1,10 %.

**R-9.1 · El proveedor paga.** Sin payouts el sistema es −1.203 $/mes con 99 % de
probabilidad de degradar. Es la dependencia dura y no tiene mitigación.

**R-9.2 · El proveedor no cambia las reglas.** Aquí hay que ser preciso, porque la
generalización cómoda es falsa. Los cinco ejes medidos:

| cambio del proveedor | familia | EV | Δ | P(degradar) |
|---|---|---|---|---|
| retiro → 1.000 | recorte de payout | 688,8 | **−509,7 (−43 %)** | 1,00 % |
| primer retiro → 1.000 | recorte de payout | 908,2 | −290,3 (−24 %) | **2,54 %** |
| split 70/30 | recorte de payout | 944,6 | −253,9 (−21 %) | **3,38 %** |
| MLL 2.000 → 1.500 | endurecimiento de drawdown | 847,9 | **−350,6 (−29 %)** | **43,32 %** |
| DLL 1.000 → 750 | endurecimiento de drawdown | 839,0 | **−359,5 (−30 %)** | **9,45 %** |

Lo que **sí** se puede decir: los endurecimientos de drawdown son los únicos que mueven el
riesgo de forma catastrófica (MLL→1500 multiplica P(degradar) por **39**). Lo que **NO** se
puede decir —y se decía— es que los recortes de payout «no muevan el riesgo» (dos de los
tres lo triplican o lo duplican) ni que los endurecimientos «apenas toquen el EV» (los dos
se llevan ~30 % de la cifra titular).

**R-9.3 · La fricción real del hedge se queda en 3 $/micro/round-trip.** Es el eje que más
riesgo mueve por unidad de error plausible, y `spr_usd` es un **SUPUESTO**, no un dato:
3,00 supone un solo cruce de horquilla para el round trip entero; si cada pata cruza la
suya, el valor físico es ~4,10.

| SPR | EV | Δ | p5 | P(degradar) |
|---|---|---|---|---|
| **3,00 (adoptado)** | 1.198,5 | — | 797,2 | 1,10 % |
| 4,00 | 1.112,3 | −86,2 | 652,5 | 2,72 % |
| **4,10 (un cruce por pata)** | **1.094,6** | **−103,9 (−8,7 %)** | 629,4 | **3,00 %** |
| 5,00 | 985,6 | −212,9 (−17,8 %) | 199,3 | **7,65 %** |
| 6,00 | 858,4 | −340,1 | −0,0 | **14,43 %** |

Un desvío de 1,1 $ triplica P(degradar); uno de 2 $ la multiplica por 7. **La puerta F3.1 de
`05_ORDEN` existe para medir este número, y hasta que se mida la cifra titular está
condicionada a él.**

**R-9.4 · El deslizamiento real se queda en banda verde** (`slip_usd_micro` = 2,50). También
es un SUPUESTO no medido, pero **es el menos peligroso de los dos**: su coste es lineal y
**apenas mueve el riesgo**. Ámbar (6,25) cuesta −116,0 $/mes con P(degradar) 1,32 %; rojo
(12,50), −313,6 con P 1,38 %. Compárese con la fricción, que en 4,75 ya rompe el criterio.

**Ojo con las unidades:** las bandas son **por micro**, y el deslizamiento por *muerte*
depende de `m` (2 en la evaluación, 4 en la fondeada). Ver la puerta F3.1 de `05_ORDEN`.

**R-9.5 · El descuento de la suscripción sigue vigente y sin límite de uso** (confirmado con
soporte el 18-08). Sin él: `cuota_100` y `cuota_153` acotan el coste.

**R-9.6 · La serie de precios usada para calibrar es representativa.** Split-half:
correlación **+0,971** — el paisaje de optimización es real, no ruido.

> **Los dos supuestos de R-9.3 y R-9.4 son los únicos números del proyecto que nadie ha
> medido nunca**, y son precisamente los dos que la Fase 3.1 mide. No se escala capital
> hasta tenerlos.

---

## 10 · TRAZABILIDAD DE LAS CIFRAS

Toda cifra que aparece en esta norma sale de uno de estos tres sitios, y se puede
regenerar desde el paquete:

| cifra | de dónde | cómo regenerarla |
|---|---|---|
| titular (1.198,5 · 797,2 · 1,10 %) y toda la tabla de estrés | `modelo/estres_v10.json` | `python modelo/estres_v10.py` (~20 min) |
| identidad de cobertura · déficit por deslizamiento · libro del hedge · experimento `b_cond` · coste de los dos bugs · campana | `modelo/cifras_citadas.json` | `python modelo/cifras_citadas.py` (~3 min) |
| aritmética de una sesión | `tests/goldens_v10.json` | `python tests/runner_goldens_v10.py` |
| comportamiento del orquestador | `tests/replay_v10.json` | `python tests/replay_v10.py` (bit-idéntico) |

**Cifras que NO son reproducibles desde este paquete** y por qué:

| cifra | estado |
|---|---|
| descomposición por linajes (buffer 752 $/mes = 64 % del EV) | medida sobre la config **v9.1**. Bajo v10 el libro agregado sí está medido (R-1.3); la descomposición por linajes **no se ha regenerado** |
| «−32,5 % / −13,6 %» del coste de los dos bugs históricos | medidas sobre la config **v8**. La re-medida sobre v10 está en `cifras_citadas.json` y da otra cosa — ver `04_GUARDARRAILES` §1 |
| coste hundido medio de la recámara (406 $, sd 34) | medido sobre **v8**; el simulador de v10 agrega la recámara (R-7.4) |

Si una cifra no está en ninguna de las dos listas, **no debería estar en la norma**.
Dígalo y se retira.
