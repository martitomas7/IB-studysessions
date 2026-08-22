# ORDEN DE CONSTRUCCIÓN
### Diez deltas (D0–D9), cada uno con su puerta. No se salta ninguna.

---

## Cómo se pide un delta

En la sesión de ingeniería, uno cada vez:

> «Implementa el **delta Dn**. Contexto: [pegar la sección indicada de
> `01_ESPECIFICACION_E2E.md`]. Los números vienen de `03_CONFIG.yaml`. Aplican los
> guardarraíles de `04`. La puerta es [la de abajo]: no des el delta por terminado sin
> ejecutarla y pegar su salida.»

---

## FASE 0 · El núcleo (no toca brokers, no toca estado)

### D0 · Configuración
**Qué:** `config.py`: cargar `03_CONFIG.yaml`, exponerlo como objeto inmutable, calcular el
sha256 del fichero, y **fallar al arrancar** si algún DERIVADO no cuadra. Ni un solo número
de negocio fuera de ese YAML (regla R2).

**Puerta:** `python tests/comprueba_config.py` → `OK` **y** las seis auto-verificaciones
detectadas (incluida la que borra `fsuelo` del fichero: es el fallo real que encontró la
auditoría del 19-08). Además: un `grep` de literales numéricos en tu código de negocio que salga
limpio, y lo pegas.

### D1 · Aritmética de una sesión
**Qué:** las funciones puras de `sizing.py` y `sesion.py`: `plan(cuenta) → {k, nu, ndn, bloqueo}`
y la resolución del día. Norma **R-2 y R-3**; módulos en Arquitectura §2. Es lo único que **no
se vuelve a tocar nunca** (regla R6).

**Puerta:** `python tests/runner_goldens_v10.py <tu_adaptador>` → **14/14**.
Y `python tests/prueba_nucleo_vs_motor.py` → **0 discrepancias sobre 60.000 estados**, que
es lo que sostiene que `nucleo_referencia_v10.py` sea de verdad la especificación ejecutable
del motor (2.830 muertes, 20.597 bloqueos y 11.219 objetivos ejercitados).
Y además, obligatorio por R3: rompe **tu** implementación de tres maneras y comprueba que
los goldens lo cazan. La referencia de lo que debe salir está hecha:
`python tests/prueba_goldens_v10.py` rompe el núcleo de referencia y da

| rotura | goldens que caen |
|---|---|
| look-ahead en la barra de entrada | 3 — los tres `LOOKAHEAD_*` |
| sin la cuña de comisión (una sola pasada de `k`) | 6 |
| operar con `k < 1` (viola R-2.4) | 1 — `bloqueo_k_menor_1` |

Si tu versión rota cae en **otros** casos, tienes un segundo problema además del que
introdujiste a propósito.

---

## FASE 1 · El orquestador (brokers simulados)

### D2 · Estado persistente
**Qué:** `estado.json` con el esquema de **Arquitectura §4**, escritura atómica (temporal +
`rename`) y carga con validación de los **8 invariantes fatales** de Arquitectura §4.
**Puerta:** matar el proceso en 10 puntos distintos del día y comprobar que al arrancar
reconstruye o aborta, nunca sigue con estado ambiguo.

### D3 · Dirección diaria y regla CONTRA
**Qué:** un sorteo 50/50 para **todo el sistema**; si ayer hubo alguna muerte, se mantiene la
dirección de ayer. Norma **R-6.1**. La semilla del sorteo se registra en el diario.
**Puerta:** los primeros 20 días del replay pack reproducen la dirección exacta.

### D4 · Máquina de estados de las cuentas
**Qué:** las máquinas de estados de suscripción, fondeada y slot de eval. **Arquitectura §3**;
norma R-4 y R-5.
**Puerta:** los **8** invariantes de **Arquitectura §4** se comprueban en cada carga y cada
escritura, y son **fatales** (el bot no arranca / no opera), no warnings.

### D5 · Slot de evaluación + empalme
**Qué:** tomar una fresca, correr la sesión, y el rearranque el mismo día en la barra de la
muerte. Norma **R-3.7 y R-4.3**.
**Puerta:** el invariante `sesiones_de_eval ≤ 1 + empalmes` del replay pack. **Y construye tú
el orquestador que lo viola** (que la superviviente opere dos veces) y comprueba que salta.
Referencia: `tests/prueba_replay_v10.py` lo hace saltar 275 veces desde el día 2.

### D6 · Rotación de la funded y recámara
**Qué:** muerte o 5º ciclo → alerta de activación esa misma tarde → arranque al día
siguiente de negociación con el `sunk` individual (FIFO — y **solo** FIFO: la política de
orden no está medida, ver R-7.4). Norma **R-5.1 a R-5.5**.
**Puerta:** la traza del replay pack visita la **fase 5** (cierre del linaje sin muerte, por
rama distinta) — reprodúcela.

### D7 · Pool, qcap y tesorería
**Qué:** renovaciones, resets, emergencias, recompras; el tope de recámara; los muros y el
barrido. Norma **R-4.4 a R-4.6 y R-7**.
**Puerta:** las 504 jornadas del replay pack con `fin_de_dia` exacto (tolerancia 1e-3 $).

### PUERTA DE FASE 1 (la grande)
```
python tests/runner_replay_v10.py <tu_orquestador>
```
**504 días, 0 divergencias, 0 invariantes rotos.** Si hay una sola divergencia, la fase no
ha terminado. Contraste de referencia: un relevo un día tarde produce **2.296** divergencias;
ignorar el qcap, **2.405**.

---

### D-C · el dashboard operativo — CONSTRUIDO, PUERTA VERDE (20-08-2026)
**Documento madre: `08_LABORATORIO.md` §6-§8 (revisión 4, `DATOS_Y_DASHBOARD.md`) — a diferencia de D-A
y D-B, este SÍ es código, con puerta, y esa puerta ya pasó.** Sustituye al informe Markdown como
superficie principal de lectura del laboratorio, y es la vía por la que el operador actúa sobre el bot
sin tocar `03_CONFIG.yaml` ni el bróker a mano.

**Qué:** el script que regenera el HTML autocontenido (ocho bloques: AHORA, RIESGO, PENDIENTES,
CUENTAS, MERCADO Y FRICCIÓN, MODELO vs REALIDAD, LABORATORIO, INCIDENCIAS — `08_LABORATORIO.md` §6.2),
el validador de paleta, y el mecanismo de acciones del operador (cola `comandos/<id>.json`, clases
A/B/C, caducidad, idempotencia, trazabilidad de Clase B contra `estado.json` — `08_LABORATORIO.md` §7).
Norma: `PROMPT_INGENIERIA_NT8.md` (el dashboard no decide, ejecuta lo que se le pide), R-2.4 y
`07_ADAPTADOR_NT8.md` §5.3/§5.4 (el botón de pánico reutiliza el protocolo de cierre, no abre uno nuevo).

**Puerta (los tres puntos, verificados y en verde):**
1. ✅ Los ocho bloques pintan correctamente 504/504 días de `tests/replay_v10.json` — incluidos el
   bloqueo del día 210 y la fase 5 (días 255-258) de la entrega de D2-D7 — sin depender de NT8 ni de
   papel corriendo. Verificado además por render real (Playwright + Chromium), no solo "no lanza
   excepción".
2. ✅ El validador de paleta pasa. Cazó un fallo real en el primer intento (aviso/grave demasiado
   próximos en matiz y luminosidad); corregido y reverificado.
3. ✅ Las 7 roturas de `08_LABORATORIO.md` §8 (comprobaciones 6-12) saltan, cada una con su
   implementación rota ejecutada — **la comprobación 11 (el botón de pánico produce una pata sola)
   saltó, no negociable, D-C se entrega con ella en verde.** El proceso de construir estas pruebas cazó
   dos bugs reales en el propio código de D-C antes de entregarlo (ver `08_LABORATORIO.md` §12, historial
   de la revisión 4) — R3 funcionando como se pretende, no solo como comentario.

**CERRADO 20-08-2026 (revisión 4 — revisión del operador sobre esta misma entrega):** el operador
reprodujo las tres puertas de arriba de forma independiente (todas verdes) y, además, encontró **tres
defectos reales** en el camino crítico del protocolo de las dos patas, no cubiertos por las pruebas de
D-C hasta ese momento — ver `07_ADAPTADOR_NT8.md` §5.3 (revisión 4) y `08_LABORATORIO.md` §12 para el
detalle de los tres. Corregidos, con comprobación R3 nueva
(`verificacion_R3/prueba_protocolo_dos_patas.py` §§8-10, 40/40 verde) y re-verificados contra el mismo
replay de 504 días. En la misma pasada se cerró el "límite honesto" que citaba esta sección: `bot/
comandos.py::valor_efectivo()` (recomendación #1 del zip original) **ya está cableado** dentro de
`bot/ciclo_vida.py` y `bot/calendario.py` — las cuatro palancas de Clase B (`empalme`, `contra`,
`emergencia`, `pausa_eval`) ya pasan por él, con la red de seguridad explícita del propio operador como
aceptación: `desviaciones_activas=[]` en el replay hace que `valor_efectivo()` devuelva siempre el valor
certificado, así que el cableado es **demostrablemente un no-op** sobre el resultado numérico del replay
— confirmado re-corriendo `tests/runner_replay_v10.py` tras el cableado: **sigue dando exactamente 504
días · 0 fallos · caja final 29.134,87 $**. Junto con esto, recomendación #2 (contador `muertes_eval`,
ahora en el diario y en el bloque 6 del dashboard) y #5 (persistencia de `k`/`m` por día en `estado.json`,
el dashboard ya no recalcula) — las tres, cableadas a la vez por tocar el mismo fichero, con el mismo
re-verificado bit-idéntico como aceptación única. Y recomendación #3 (los "dos relojes" de una cuenta
bloqueada) resuelta como dos relojes DISTINTOS, no una discrepancia a corregir — ver `03_CONFIG.yaml` §10
y el bloque 3 del dashboard, que ahora pinta los dos por separado.

**Sitio en el orden:** después de la puerta de Fase 1, antes de Fase 2 — igual que `09_DESPLIEGUE.md`
(abajo), pero D-C sí tiene puerta de test propia y sí se puede construir ya, sin esperar a NT8.

---

## Herramienta de pruebas adicional (no un delta, no gatea nada): `simulador_nt8/`

**20-08-2026, a petición del operador.** Un simulador de NT8 fuera de proceso — proceso de sistema
operativo aparte del bot, mismo contrato de puerto que `07_ADAPTADOR_NT8.md` §1, envolviendo
`bot/adaptador_falso.py` sobre un socket `AF_UNIX` — para probar el protocolo de las dos patas, el vigía
de conexión, y la reconciliación de arranque (§6) bajo una frontera de proceso/red REAL: matando
procesos, con timeouts de reloj de pared reales. Suite completa en
`verificacion_R3/integracion_proceso_real/` (ocho fases, R3 en cada una). **No es un delta con puerta que
gatee ninguna fase** — es infraestructura de pruebas adicional, construible y corrida ya, que no acerca
ni sustituye nada de D-A1 (sigue bloqueado por falta de máquina Windows con NT8 real). Ver
`simulador_nt8/LEEME.md` para el aviso completo de qué es y qué no es, y `07_ADAPTADOR_NT8.md` §8/§12
(revisión 5) para el detalle técnico.

---

## Entregable previo a FASE 2 (no un delta con puerta de test): `09_DESPLIEGUE.md`

**Documento, no código — como D-A y D-B.** Fase 1 corre entera con brókers simulados, en esta sesión de
ingeniería, sin ninguna máquina Windows ni NT8 real de por medio. Fase 2 es la primera vez que el bot
queda corriendo, sin supervisión constante, contra una plataforma real — y ahí aparece un requisito que
ningún delta de arriba cubre: **¿qué pasa si el proceso del bot (o NT8, o el puente) se cae a media
sesión, con una posición real abierta?** `07_ADAPTADOR_NT8.md` §7 identifica el problema (el bot no
puede detectar su propia caída) y concluye que hace falta un **supervisor externo** — no es una
aserción de runtime de D9 (esas corren dentro de un proceso vivo; esto es para cuando el proceso está
muerto).

`09_DESPLIEGUE.md` recoge:
- El watchdog de proceso (Task Scheduler o equivalente): qué lo dispara, qué hace al notar el bot
  caído — reiniciar, o solo alertar, o las dos cosas en escalada.
- Arranque automático del bot al reiniciar la máquina.
- Permisos y cuenta de servicio bajo la que corre.
- El registro de **contra qué build de NT8 se validó por última vez el adaptador** (`07_ADAPTADOR_NT8.md`
  §9) — para saber, tras una actualización de NT8, si hace falta re-correr `da1_diagnostico.ps1` antes
  de confiar en el puente.

**Se escribe antes de D8, no antes de D0.** Fase 0 y Fase 1 (D0-D7) no lo necesitan: son brókers
simulados, sin proceso que pueda quedarse con una posición real colgada. No se escribe todavía — se dice
aquí para que no se pierda y para que quede claro en qué momento del orden de construcción hace falta.

---

## Entregable previo a FASE 2 (no un delta con puerta de test): `10_SEGURIDAD.md`

**20-08-2026, mismo sitio en el orden que `09_DESPLIEGUE.md` — documento, no código.** El marco de
contención de fallos (invariante único PLANO/CUBIERTO/TRANSICIÓN, clasificación CONOCIDO-SEGURO/
CONOCIDO-INSEGURO/DESCONOCIDO, escalera de degradación N0-N4) que gobierna cómo D8 y D9 reaccionan
ante cualquier fallo, catalogado o no. Sus cinco huecos concretos (§7) y su batería R3 (§6, 10
escenarios, todos probables con `simulador_nt8/` sin NT8) se ejecutan como parte de este mismo pase
— ver el historial de `07_ADAPTADOR_NT8.md` y `10_SEGURIDAD.md` §1 para el detalle de qué se cerró.

**CERRADO 20-08-2026 (`ORDEN_DE_TRABAJO_D8.md`).** El marco en sí: `bot/seguridad.py`
(`clasifica_posicion`/`clasifica_conocimiento`/la escalera `sube_a`/`baja_automatica`/`baja_humana`,
nivel persistido en su propio `nivel.json`, nunca dentro de `estado.json`) — R3 en
`verificacion_R3/prueba_seguridad_n0_n4.py` (35/35). Los cinco huecos de §7: detección de
liquidación forzosa (`bot/deteccion_liquidacion.py`, D8.3 — R3 en proceso y end-to-end contra el
socket real), excepción tipada + N4 para estado corrupto (`bot/estado.py::cargar` +
`seguridad.reacciona_a_estado_invalido`), fichero de bloqueo por PID (`bot/bloqueo_proceso.py`),
presupuesto de reinicios (ya vivía en `watchdog_bot.ps1`, lado Python listo para cablear en
`seguridad.reacciona_a_presupuesto_reinicios_agotado`), y órdenes en reposo (D8.2, ver más abajo).
Más el hueco nuevo del pedido de trabajo (salto de reloj en la caducidad de comandos,
`bot/comandos.py::_avanza_reloj_max_visto`). Batería completa de la tabla de §6 (10 escenarios) en
`verificacion_R3/prueba_bateria_10_seguridad.py` — 9/10 demostrados, 1 (#8, residuo diario fuera de
banda) bloqueado en D8.4 + Fase 3.1, documentado como tal, no fingido.

---

## FASE 2 · Ejecución en papel

### D8 · Ejecutores y detección de eventos
**Qué:** traducir el plan a órdenes reales en cuenta de papel, con la regla de **las dos patas
o ninguna**. **Arquitectura §7**; el día minuto a minuto en **Arquitectura §5**. Gobernado por el
marco de `10_SEGURIDAD.md` (N0-N4) para cualquier fallo, catalogado o no.
**Puerta:** 5 días limpios en papel + kill-switch probado de verdad (no revisado: probado) — bloqueada
por falta de cuenta `Sim101`/NT8 real, igual que D-A1. **Lo que sí se puede construir y probar sin
papel ni NT8** se está construyendo por piezas siguiendo `ORDEN_DE_TRABAJO_D8.md` (20-08-2026):

- **D8.1 (detector incremental) — CERRADO.** `bot/detector_en_vivo.py::DetectorEnVivo`, verificado
  contra `sesion.resolver_dia` como oráculo: 0 discrepancias sobre los 902 estados reales del pack de
  504 días (`verificacion_R3/prueba_detector_en_vivo.py`) + 0 sobre 1.500 estados sintéticos de borde
  (`verificacion_R3/prueba_detector_en_vivo_sintetico.py`) — la puerta exacta de
  `ORDEN_DE_TRABAJO_D8.md` §1.
- **D8.2 (órdenes en reposo) — CERRADO.** `coloca_bracket()` nuevo en el puerto
  (`07_ADAPTADOR_NT8.md` §1 y §5.4, revisión 5), implementado en `bot/adaptador_falso.py` y cableado
  en `simulador_nt8/`. R3 en proceso (`verificacion_R3/prueba_bracket_ordenes_reposo.py`, 19/19) y
  end-to-end contra el socket real
  (`integracion_proceso_real/prueba_bracket_ordenes_reposo.py`, 7/7).
- **D8.3 (detección de liquidación forzosa) — CERRADO.** Ver la entrada de `10_SEGURIDAD.md` arriba.
- **D8.4 (el bucle del día) — EN DISEÑO.** La pieza que ensambla todo lo demás — diseño arquitectónico
  fundamentado (grounded contra el código real, no especulativo) en curso vía panel de ángulos +
  síntesis, siguiendo la restricción dura de `ORDEN_DE_TRABAJO_D8.md` §0 ("un solo bucle, la fuente de
  barras como puerto") y sin tocar `bot/sesion.py` (R6) ni cambiar el comportamiento observable de
  `bot/orquestador.py`.
- **D8.5 (idempotencia de órdenes) — pendiente**, junto con D8.4 (mismo patrón que
  `bot/comandos.py::procesa_comando`, aplicado a `order_id`).
- **Instrumentación (§3 del pedido):** lector de JSONL del laboratorio — CERRADO
  (`bot/lector_laboratorio.py`, `verificacion_R3/prueba_lector_laboratorio.py`, 15/15; cazó y corrigió
  un bug real preexistente en `bot/dashboard.py::_bloque_incidencias`). Residuo diario
  modelo-contra-realidad y entradas de sizing en el diario: pendientes de D8.4 (necesitan un resultado
  real que comparar).
- **La Puerta Grande (§4) y todo lo que va después (§5): pendiente**, detrás de D8.4.

### D9 · Reconciliación y aserciones de runtime
**Qué:** la reconciliación de posiciones al arrancar, las aserciones pre-orden, el cuadre de
cierre y el kill-switch. **Arquitectura §7**.
**Puerta:** por R3, **cada aserción que escribas debe verse disparar** con una entrada
construida para violarla — una demostración por aserción, y se pegan todas las salidas.
El paquete **no fija cuántas son**: eso lo determina tu implementación. Como mínimo tienen
que existir las que cubren los 4 requisitos de Arquitectura §7 (orden de apertura, orden de
cierre, reconciliación al arrancar, prohibición de reintentar una pata) y los 8 invariantes
de Arquitectura §4.

---

## FASE 3 · Dinero real, por escalones

| escalón | qué | criterio para pasar al siguiente |
|---|---|---|
| **F3.1** | 1 evaluación real, sola, 10 sesiones | mide los **dos números que el modelo no tiene** (`spr_usd`, con dos formas de medirse -- por round-trip o por fill, ver detalle abajo -- y `slip_usd_micro`). Criterio abajo |
| **F3.2** | funded + evaluación | verificar la regla de dirección única contra posiciones **reales** del bróker |
| **F3.3** | pool completo, 1 mes | cuadre mensual dentro de ±10 % del modelo |

### La puerta F3.1, en detalle

**Lo que sale de F3.1 decide si las cifras publicadas valen.** Es el único escalón que puede
tumbar el proyecto entero, así que su criterio está escrito con cuidado.

#### Las unidades: SIEMPRE por micro, nunca por muerte

> **Ésta es la trampa, y ya se cayó en ella una vez.** El deslizamiento por **muerte** no es
> comparable entre fases, porque depende de `m`: una evaluación lleva 2 micros y una fondeada
> 4. **F3.1 opera una evaluación sola, con `m = 2`.** Un criterio escrito en $/muerte se lee
> mal por un factor de 2:

| banda | $/micro | $/muerte en una **eval** (m=2) | $/muerte en una **fondeada** (m=4) |
|---|---|---|---|
| VERDE (el valor adoptado) | **2,50** | 5,00 | 10,00 |
| ÁMBAR | **6,25** | 12,50 | 25,00 |
| ROJO | **12,50** | 25,00 | 50,00 |

**25 $/muerte medidos en F3.1 son 12,50 $/micro, es decir la banda ROJA.** Anota siempre el
número **por micro**, y deja escrito con qué `m` operaba la cuenta.

Lo mismo con la fricción: `spr_usd` es **por micro y round trip**, no por sesión ni por
cuenta.

#### La desviación de fill rutinario NO es un tercer número -- es `spr_usd` en otra unidad

La Pasada 2 de LA PUERTA GRANDE (`verificacion_R3/PASADA_2_RUIDO.md`) midió, en los
intentos **normales** (entrada, objetivo, campana -- distintos de la salida por muerte,
que ya cubre `slip_usd_micro`), una desviación de fill que en un primer análisis se
llamó "un tercer número que el modelo no tiene". **Eso era un error, corregido en
`REVISION_D8_S5_PASADA2.md` §2:** `spr_usd` ya carga "cruzar la horquilla" sobre **todo**
micro-round-trip, muerte o no (`bot/detector_en_vivo.py`, `fric` se resta siempre, no solo
si `muere`). El eje de fills normales de la Pasada 2 mide **la misma desviación física**,
solo que expresada por fill en vez de por round-trip fijo, y por el mismo canal aislado.

Censo directo del pack de 504 días (verificación independiente, no solo la cifra de la
Pasada 2): de 2.742 micro-sesiones totales, 2.068 son sin muerte. De ahí sale el factor de
conversión, **medido, nunca inventado**:

> **1 tick de desviación de fill rutinario ≡ Δ`spr_usd` de 0,9427 $/micro.**

**Consecuencia práctica: F3.1 no mide dos ejes con dos bandas -- mide UNA desviación real
de fill (en ticks), y la convierte a $/micro round-trip con el factor de arriba para entrar
en la tabla de la puerta F3.1 que ya existe (abajo).** No hacen falta bandas nuevas --
`spr_usd` ya tiene las suyas, y esta es la misma variable.

**Regla de no doble cobro** (mismo principio que `slip_usd_micro` en la Pasada 2, §4a de
`ANALISIS_PUERTA_GRANDE.md`): `spr_usd` y `hedge_broker.desviacion_fill_normal_usd_tick`
(`03_CONFIG.yaml`) nunca suben los dos a la vez. Mientras `spr_usd` cargue la fricción
(como hoy), el eje de ticks se queda en `valor: 0.0`.

#### Las dos líneas del gate -- no son la misma, y llamarlas igual fue el error

Un primer intento de ubicar "la línea de fallo del gate" en ticks del eje nuevo dio dos
cifras que no cuadraban entre sí. La causa no era imprecisión de la rejilla: **son dos
líneas distintas**, y confundirlas fue el error (`REVISION_D8_S5_PASADA2.md` §2 lo señaló;
`ORDEN_DE_TRABAJO_D9.md` §1.1 lo corrige con nombre para cada una):

| nombre | valor | qué es |
|---|---|---|
| **línea de política** | `spr = 4,50` ≡ **1,59 ticks** | lo que la norma **manda hacer** (arriba: *"> 4,50 → NO se escala"*). **Es la que se acciona.** |
| **línea estadística** | `spr ≈ 4,68` ≡ ~1,78 ticks | donde `P(degradar)` cruza el 5 %, interpolando linealmente los dos puntos de `modelo/cifras_citadas.json:puerta_f31` que rodean ese cruce (4,50 y 4,75 -- la rejilla es gruesa y con ruido de Monte Carlo entre puntos contiguos, así que esta cifra es SOLO informativa, nunca operativa). |

**Los 0,18 $/micro entre ellas (4,68 − 4,50) son margen puesto a propósito, no ruido de
rejilla** -- la norma ya decide en 4,50, antes de llegar a donde el riesgo estadístico
realmente cruza el 5 %. (Corrección aritmética sobre un borrador anterior de esta sección:
1,59 ticks equivale a `spr` 4,50, no 4,51 -- el 4,51 salía de evaluar la conversión en
n = 1,6 en vez de 1,59.)

#### Expectativa previa del operador -- anotada como expectativa, NUNCA como medida

De la operativa manual previa del operador (no de F3.1, no instrumentada): la desviación
entre el precio pedido y el obtenido **en la entrada** rondaba 0 a 0,5. Convertido con el
factor medido de arriba (1 tick ≈ 0,9427 $/micro de `spr_usd`):

| lectura | `spr` equivalente | margen hasta la línea de política (4,50) |
|---|---|---|
| 0-0,5 **puntos** (0-2 ticks, media ~1) | 3,94 | 0,59 ticks |
| 0-0,5 **ticks** (media ~0,25) | 3,24 | 1,34 ticks |

Las dos caen del lado bueno de la línea de política. **Tres avisos obligatorios cada vez
que se cite esto, para que no se confunda con un dato:**

1. Describe la **entrada** -- una orden límite, la salida seguridad. La que decide la
   puerta es el **stop**, a mercado y en movimiento rápido, no la entrada.
2. Casi seguro no era con el tamaño de posición que usa este circuito.
3. Es un recuerdo del operador, no un registro instrumentado.

Sirve para tener una expectativa razonable de que F3.1 probablemente pase -- nunca para
sustituir la medida real de F3.1.

#### El criterio de paso: el protocolo pre-registrado, no un número inventado

No hay un umbral nuevo. **Se aplica el criterio que este proyecto lleva usando desde la
reoptimización: `P(degradar)` pesimista ≤ 5 %.** Se re-corre la tabla con los dos valores
medidos y se mira si sigue pasando.

Medido de antemano (`modelo/cifras_citadas.json` → `puerta_f31`, 8 semillas × 3.000 réplicas):

| fricción medida | EV $/mes | p5 | P(degradar) | ¿pasa? |
|---|---|---|---|---|
| 3,00 (el supuesto) | 1.198,5 | 797,2 | 1,10 % | ✅ |
| 4,00 | 1.112,3 | 652,5 | 2,72 % | ✅ |
| **4,10** (un cruce por pata) | 1.094,6 | 629,4 | 3,00 % | ✅ |
| 4,25 | 1.077,8 | 544,6 | 3,97 % | ✅ |
| **4,50** | 1.049,5 | 402,0 | 4,69 % | ✅ **último que pasa** |
| **4,75** | 1.021,8 | 343,3 | **5,12 %** | ❌ |
| 5,00 | 985,6 | 199,3 | 7,65 % | ❌ |

**El criterio pre-registrado se rompe entre 4,50 y 4,75.** Ésa es la línea, y está medida,
no elegida.

Y las combinaciones que F3.1 puede devolver de verdad:

| resultado | EV | p5 | P(degradar) | ¿pasa? |
|---|---|---|---|---|
| fricción 4,10 + deslizamiento ÁMBAR | 981,1 | 522,4 | 3,41 % | ✅ |
| fricción 3,00 + deslizamiento ROJO | 884,9 | 495,0 | 1,38 % | ✅ |
| fricción 4,10 + deslizamiento ROJO | 790,4 | 350,0 | 4,14 % | ✅ |

**Léelo bien: el deslizamiento casi no mueve el riesgo — mueve el EV.** Incluso en rojo,
`P(degradar)` se queda en 1,38 %. **La variable que decide la puerta es la fricción.**

#### Qué hacer con cada resultado

| fricción medida | qué se hace |
|---|---|
| ≤ 4,10 | **Se escala.** La cifra baja hasta ~1.095 $/mes; el riesgo sigue en un tercio del límite |
| 4,10 – 4,50 | **Se escala, pero se publica la cifra corregida** (1.050–1.095) y se vigila el p5, que cae rápido: de 629 a 402 |
| **> 4,50** | **NO se escala. Se vuelve al laboratorio a reoptimizar con la fricción real.** Es una decisión de modelo, no de ingeniería |

| deslizamiento medido | qué se hace |
|---|---|
| ≤ 6,25 $/micro (verde/ámbar) | Se escala; el coste es lineal y conocido (−116 $/mes en ámbar) |
| 6,25 – 12,50 (rojo) | Se escala **solo si la fricción pasó holgada**; el coste llega a −314 $/mes |
| > 12,50 | **Parar y preguntar.** Fuera de todo lo medido |

> **La decisión de arriesgar capital más allá de F3.1 es del operador, no de la sesión de
> ingeniería.** Lo que esta tabla hace es quitarle la ambigüedad: dice qué pasa con cada
> resultado, con números medidos.

---

## Resumen de puertas

| fase | puerta | referencia de contraste |
|---|---|---|
| 0 | `comprueba_config` OK · 14/14 goldens · tus 3 roturas cazadas | los goldens de v8 detectaban **0** de los dos bugs caros |
| 1 | 504 días · 0 divergencias · 0 invariantes rotos | relevo D+2 da 2.296 divergencias |
| D-C | 8 bloques sobre los 504 días del replay + paleta validada + 7/7 roturas cazadas (la del botón de pánico, no negociable) + revisión 4: 3 defectos del operador corregidos, 40/40 en `prueba_protocolo_dos_patas.py` | la versión ingenua de "aplanar ambas" deja una pata sola |
| 2 | 5 días limpios + kill-switch probado + **todas** tus aserciones vistas disparar | — |
| 3 | fricción y deslizamiento medidos **en $/micro**; P(degradar) ≤ 5 % re-corrida con esos valores | la fricción se rompe entre 4,50 y 4,75 |
