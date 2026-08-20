# 10 · SEGURIDAD · contención de fallos
### Documento para el paquete. Entregable previo a Fase 2, junto con `09_DESPLIEGUE.md`.

**Incorporado 20-08-2026.** El marco (invariante único, clasificación CONOCIDO-SEGURO/INSEGURO/
DESCONOCIDO, escalera N0-N4) y el catálogo A-H se adoptan tal cual. Los cinco huecos concretos de
§7, la batería R3 de §6, y la nota de §1 sobre mover el intervalo del latido a `03_CONFIG.yaml` se
ejecutan en esta misma revisión — ver `05_ORDEN_DE_CONSTRUCCION.md` (nueva sección, junto a
`09_DESPLIEGUE.md`) para el estado de cada uno y `REVISION_REV5.md` (adjunto al paquete) para el
resto del plan de acción de esta revisión (D8, órdenes en reposo, residuo diario, capital por
circuito). Los valores que este documento marca explícitamente como decisión del operador (§8: `R`
y `M` del presupuesto de reinicios, días de instantáneas, banda del residuo diario, canal de alerta
de N3/N4) siguen sin fijar — se usa el punto de partida que el propio documento propone donde lo
propone (p. ej. `R=3, M=15 min`), marcado como provisional, nunca como decidido.

No es una lista de casos: es un **marco** que hace que los casos que nadie ha pensado caigan
igualmente en un sitio seguro. Un catálogo siempre está incompleto; un marco no.

---

## 1 · El invariante único

> **En todo instante el sistema está PLANO o CUBIERTO. Una sola pata solo es legal dentro de
> una ventana de transición acotada, con fecha de caducidad y una acción compensatoria ya
> decidida.**

Todo lo demás es una violación, y **todas las violaciones se tratan igual**, venga de donde
venga el fallo. Eso es lo que hace que el marco cubra lo imprevisto.

Tres estados legales, y solo tres:

| estado | qué significa | qué se permite |
|---|---|---|
| **PLANO** | cero posición en las dos cuentas | abrir, si todo lo demás lo permite |
| **CUBIERTO** | las dos patas abiertas y **con tamaños que se corresponden** | vigilar y cerrar |
| **TRANSICIÓN** | una pata, dentro de `N` / `N_hedge` | **solo** completar o revertir |

Fuera de la ventana de transición, "una pata" no es un estado: es una emergencia.

---

## 2 · La clasificación que de verdad importa: qué sabemos, no qué ha pasado

La mayoría de los sistemas fallan aquí. No importa tanto **qué** falló como **cuánto sabemos**:

| clase | ejemplo | regla |
|---|---|---|
| **CONOCIDO-SEGURO** | sé que estoy plano; sé que estoy cubierto y cuadra | seguir |
| **CONOCIDO-INSEGURO** | sé que tengo una pata sola | **cerrar la pata expuesta**, subir de nivel, alertar |
| **DESCONOCIDO** | no puedo determinar el estado de una o de las dos patas | **forzar a PLANO** (aplanar las dos, confirmando cada una) y **parar hasta intervención humana** |

> **La clase DESCONOCIDO es la peligrosa, y la regla es contraintuitiva: ante la duda NO se
> espera a saber más — se aplana.** Esperar información mientras hay exposición es la forma más
> común de convertir un susto en una pérdida. Es la misma lógica que ya tiene §5.3: *"si no se
> puede demostrar que es una, se fuerza a ninguna"*. Aquí se generaliza a todo el sistema.

---

## 3 · La escalera de degradación

Cinco niveles. **El sistema sube solo; solo baja con un humano.** Esa asimetría es la que impide
que un fallo se auto-perdone.

| nivel | nombre | qué hace | quién lo baja |
|---|---|---|---|
| **N0** | NORMAL | opera | — |
| **N1** | SIN APERTURAS | no abre nada nuevo; lo abierto sigue su curso normal | solo, al desaparecer la causa |
| **N2** | PLANO Y PARADO HOY | aplana todo confirmando, no vuelve a abrir hoy | solo, al día siguiente |
| **N3** | KILL | aplana, para, **y no reanuda aunque lo reinicien** | **humano, explícito** |
| **N4** | CONGELADO | **ni siquiera llama al bróker**; solo alerta | **humano, explícito** |

N4 existe para un caso concreto: cuando **no te puedes fiar ni de tu propio estado**. Llamar al
bróker con un estado corrupto es peor que no llamarlo.

---

## 4 · El catálogo, mapeado al marco

### A · El proceso muere

| momento de la muerte | qué queda expuesto | contención |
|---|---|---|
| antes de abrir nada | nada | reinicio normal (N0) |
| **tras confirmar el hedge, antes de mandar la prop** | **el hedge, desnudo** | al reiniciar, la reconciliación ve hedge sin prop → CONOCIDO-INSEGURO → aplanar el hedge → **N2** |
| con las dos patas | nada (cubierto) | reconciliación cuadra → retomar la sesión (ya en §6 de `07`) |
| durante el cierre | la pata que faltara | reconciliación → aplanar → **N2** |
| escribiendo el estado | nada — escritura atómica | reinicio normal (verificado 10/10) |

> **El intervalo del latido del watchdog es un parámetro de RIESGO, no de operación.** Acota
> cuánto tiempo puede estar el hedge desnudo tras una caída. Hoy está en `09_DESPLIEGUE.md`
> como detalle de despliegue; **debería estar en `03_CONFIG.yaml` con su justificación**, junto
> a `N` y `N_hedge`, porque cumple exactamente la misma función.

### B · Una sola pata

| caso | contención |
|---|---|
| rechazo de una orden | ya corregido en la revisión 5: salida limpia inmediata |
| **fill parcial que no completa** | tamaños que no se corresponden → **DESCONOCIDO** → aplanar las dos → N2 |
| **el proveedor liquida la cuenta prop por su cuenta** | ver abajo — es el caso que más me preocupa |
| orden mandada sin `order_id` de vuelta | DESCONOCIDO → aplanar las dos → N2 |

> **La liquidación forzosa merece párrafo propio.** El modelo supone que **el bot** sale al DLL.
> Pero el proveedor aplica el MLL **en tiempo real** y puede liquidar la cuenta antes de que el
> bot decida nada. Si eso pasa y el bot no se entera, **el hedge se queda corriendo desnudo el
> resto del día**.
>
> Contención: **la muerte de una cuenta se detecta leyendo la POSICIÓN, no prediciéndola.** Si
> `leer_posicion(prop)` pasa a cero sin que haya una orden nuestra que lo explique, es
> liquidación forzosa → **cerrar el hedge inmediatamente** y anotarlo como evento de
> laboratorio (es además un dato valiosísimo: dice que el proveedor liquida antes que nosotros).

### C · Conectividad

| caso | contención |
|---|---|
| una conexión caída al abrir | no se abre nada (el arreglo de `hay_conexion` de la revisión 5) → N1 |
| **conexión caída con posición abierta** | **las órdenes en reposo siguen en el bróker y siguen protegiendo** |
| las dos conexiones caídas | N2 + alerta máxima; al recuperar, reconciliación antes de nada |
| feed retrasado o desconocido | N1 (no abrir) + E1 no publica |

> **Éste es el segundo argumento fuerte para las órdenes en reposo**, además de la precisión del
> fill: si el stop del suelo y el límite del objetivo **ya están puestos en el bróker**, una
> caída de conexión no deja la posición sin protección. Un bot que sale "a mercado cuando
> detecta" pierde toda la protección justo cuando más falta hace.

### D · Pérdida o corrupción de datos

**Cada hecho tiene UNA fuente de verdad, y una vía de reconstrucción:**

| hecho | fuente de verdad | si se pierde |
|---|---|---|
| **posición abierta** | **el bróker, siempre** — nunca `estado.json` | se lee del bróker |
| linaje: `s₀`, `H`, fase, recámara | `estado.json` | se reconstruye del diario |
| historia, tesorería, caja | **el diario** (append-only) | no se pierde; es append-only |
| configuración | el fichero + su checksum | se restaura del paquete |

**Tres reglas:**

1. **`estado.json` NUNCA es la fuente de verdad de una posición.** Si discrepan, manda el bróker
   y se para (ya está en §6 de `07`).
2. **Instantánea diaria rotatoria de `estado.json`** (p. ej. 30 días). La escritura atómica
   protege contra el fichero roto a medias, **no contra un contenido válido pero equivocado**,
   que es peor porque no se nota.
3. **Estado corrupto o ausente → N4.** No se adivina, no se reconstruye a la brava y se sigue.
   Se reconstruye del diario, se compara con el bróker, y **un humano lo aprueba**.

**Hueco encontrado hoy:** cargar un `estado.json` truncado lanza `JSONDecodeError`, y uno con
campos ausentes lanza `KeyError` — **no** el `EstadoInvalidoError` propio del proyecto. Quien
llama no puede distinguir "el estado está corrupto" de "hay un bug en mi código", y son dos
respuestas distintas. **Debe ser una excepción tipada, y debe llevar a N4.**

**Salto de reloj.** Las duraciones ya usan reloj monótono. Pero la caducidad de los comandos usa
reloj de pared: **un salto hacia atrás podría resucitar un comando caducado.** Contención:
comprobar las dos — si el monótono dice que ha pasado más tiempo del que dice el de pared, se
cree al monótono y se marca `CADUCADO`.

### E · Divergencia silenciosa — la más peligrosa de todas

Un sistema parado hace ruido. Un sistema **equivocado pero funcionando** no hace ninguno.

| caso | contención |
|---|---|
| `estado.json` válido pero equivocado | **el residuo diario modelo-contra-realidad**: si el residuo se sale de banda, el estado o la ejecución están mal → N1 y avisar |
| ejecución duplicada tras reinicio | idempotencia por `order_id`, como ya hacen los comandos — **hay que extenderla a las órdenes** |
| el `k` del bot ≠ el tamaño realmente abierto | la reconciliación compara **tamaño**, no solo presencia (ya está en §6) |

> **El residuo diario (§4.1 de la revisión) no es solo instrumentación: es el detector de
> corrupción silenciosa.** Es la única comprobación del sistema que puede cazar "el estado es
> coherente consigo mismo pero no con la realidad".

### F · Contraparte

| caso | contención |
|---|---|
| cuenta cancelada por el proveedor | posición prop a cero sin orden nuestra → misma vía que la liquidación forzosa → cerrar el hedge |
| cuenta bloqueada muerta por inactividad | los **dos relojes** del dashboard (5 días alerta / ~7 días el proveedor) |
| cambio de reglas | **alerta, nunca reacción automática** — ya es doctrina del laboratorio |
| pago denegado | evento de laboratorio + alerta; no cambia el comportamiento del bot |

### G · Humano

| caso | contención |
|---|---|
| **dos instancias del bot a la vez** | **fichero de bloqueo con PID** — si otra instancia lo tiene, la segunda **no arranca** (N4). No existe hoy y es barato |
| palanca de Clase B olvidada encendida | ya caduca sola y sale en el dashboard |
| aprobación confirmada que no ocurrió | la cadena de invariantes de `estado.json` (7 y 8) |
| se olvida recomprar una suscripción | slot vacío, se anota como `idle` — degrada el EV, no la seguridad |

### H · Multicircuito (cuando llegue)

| caso | contención |
|---|---|
| **dos circuitos compartiendo el mismo colchón** | **capital dedicado por circuito** en su propia config. Sin fondo común |
| dos circuitos escribiendo el mismo `estado.json` | el fichero de bloqueo de G, por ruta de estado |
| fallo correlado en las 5 cuentas | van todas en la misma dirección **por obligación**: un fallo operativo las toca todas a la vez. Es la razón real de subir un peldaño cada vez |

---

## 5 · El presupuesto de reinicios

**Hueco encontrado hoy: el watchdog no tiene tope de reinicios.** Un bot que revienta al cargar
se reinicia para siempre, y cada ciclo puede mandar órdenes.

> **Regla: `R` reinicios en `M` minutos → se deja de reiniciar y se sube a N3.** Los valores de
> `R` y `M` son decisión del operador, no míos; propongo 3 en 15 minutos como punto de partida y
> que se afine en papel.

Y el corolario: **un reinicio no es gratis**. Cada uno pasa por reconciliación, y una
reconciliación que no cuadra sube de nivel. Un bucle de reinicios acaba en N3 por sí solo si la
reconciliación es honesta — el presupuesto es el cinturón, la reconciliación es los tirantes.

---

## 6 · Cómo se demuestra que esto no es papel mojado (R3)

Cada contención tiene que **verse disparar**. Todas se pueden probar con `simulador_nt8/`, sin
NT8 y sin dinero — es exactamente para lo que sirve tener el simulador fuera de proceso:

| # | qué se rompe a propósito | qué tiene que pasar |
|---|---|---|
| 1 | matar el bot entre el fill del hedge y la orden de la prop | al reiniciar: aplana el hedge, N2 |
| 2 | fill parcial que nunca completa | DESCONOCIDO → aplana las dos → N2 |
| 3 | **poner la posición prop a cero desde el simulador, sin orden del bot** | detecta liquidación forzosa → cierra el hedge |
| 4 | tirar la conexión con posición abierta | las órdenes en reposo siguen puestas; alerta; N2 |
| 5 | corromper `estado.json` de tres formas | excepción tipada → **N4**, nunca N0 |
| 6 | arrancar una segunda instancia | la segunda no arranca |
| 7 | hacer reventar el bot al cargar, en bucle | tras `R` intentos deja de reiniciarse y sube a N3 |
| 8 | inyectar un fill peor que el del modelo | el residuo diario se sale de banda y avisa |
| 9 | mover el reloj de pared hacia atrás | un comando caducado **no** resucita |
| 10 | forzar tamaños que no se corresponden entre patas | reconciliación lo caza → N3 |

**Ninguna se da por buena sin la salida pegada.** Igual que las 40 del protocolo y las 83 de
integración.

---

## 7 · Los cinco huecos concretos que hay que cerrar

Ordenados por riesgo, todos comprobados hoy contra el código real:

1. **Detección de liquidación forzosa** (§B). Es el único caso del catálogo que deja el hedge
   desnudo **durante horas** sin que nada se entere. Requiere leer posición, no predecirla.
2. **Órdenes en reposo** (§C y el requisito de D8). Sin ellas, una caída de conexión deja la
   posición sin protección.
3. **Excepción tipada + N4 para estado corrupto** (§D). Hoy sale un `KeyError` indistinguible de
   un bug.
4. **Fichero de bloqueo por PID** (§G). Barato, y evita el fallo más tonto y más caro posible.
5. **Presupuesto de reinicios** (§5). El watchdog hoy reinicia sin límite.

Y dos que ya estaban anotados y encajan aquí: **instantánea diaria del estado** y **el intervalo
del latido movido a `03_CONFIG.yaml`** como el parámetro de riesgo que es.

---

## 8 · Lo que este documento NO decide

Coherente con el resto del paquete: los **valores** son del operador, no míos.

- `R` y `M` del presupuesto de reinicios.
- Cuántos días de instantáneas se guardan.
- La banda del residuo diario a partir de la cual se avisa — **hay que medirla en papel primero;
  fijarla a ojo la haría inútil o insufrible**.
- Si N3 y N4 avisan por un canal distinto del fichero de informe.

Lo que sí queda fijado, y no es negociable: **el sistema sube de nivel solo y solo baja con un
humano**, y **ante la duda se aplana**.
