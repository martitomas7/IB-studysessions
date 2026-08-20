# 09 · DESPLIEGUE · el proceso del bot en una máquina real

### Entregable previo a Fase 2. Documento, no código — como D-A y D-B.
**revisión 1 · 20-08-2026** — escrito tras cerrar la revisión 4 de D-C (`07_ADAPTADOR_NT8.md`,
`08_LABORATORIO.md`), siguiendo la confirmación explícita del operador: *"Sí, pero después de la pasada
de arriba"* — y su propia aclaración de que **nada de esto necesita NT8**. Anotado como hueco desde la
revisión 3 de `07_ADAPTADOR_NT8.md` (19-08-2026) y reservado en `05_ORDEN_DE_CONSTRUCCION.md`, "Entregable
previo a FASE 2" — no escrito hasta ahora porque no le tocaba: Fase 0 y Fase 1 (D0-D7) corren con brókers
simulados, sin proceso que pueda quedarse con una posición real colgada, así que no lo necesitaban.

---

## 0 · Por qué existe este documento y por qué no antes

`07_ADAPTADOR_NT8.md` §7 identifica el problema exacto: *"NT8, el puente o el proceso del bot se caen a
media sesión, con una o las dos patas abiertas"* — y concluye que **no hay nada que el bot pueda hacer
al respecto mientras está caído**, porque el propio proceso que debería detectarlo y actuar es el que
está muerto. La respuesta entera ocurre al reiniciar, vía la reconciliación de §6 de ese documento — pero
"reiniciar" no pasa solo porque sí: hace falta algo **externo al proceso del bot** que note que está
muerto y lo reinicie (o al menos alerte de inmediato). Eso es un **watchdog de sistema operativo**, no
una aserción de runtime de D9 — D9 vive dentro de un proceso vivo; esto es exactamente para cuando no
hay proceso vivo.

Se escribe **antes de D8, no antes de D0**: D0-D7 corren en esta sesión de ingeniería con brókers
simulados y sin ningún proceso de larga duración que pueda quedarse a medias — no hay nada que
supervisar todavía. D8 es la primera vez que existe un proceso que corre sin supervisión constante
contra una plataforma real (aunque sea en papel, D8 ya manda órdenes reales a `Sim101`) — y por eso este
documento tiene que existir **antes** de que D8 empiece a correr sin nadie mirando, no después.

**Nada de lo que sigue depende de NT8 real.** El watchdog no habla con NT8 ni con la ATI — habla con el
proceso del bot (¿sigue vivo?) y con el sistema operativo (Task Scheduler). Es exactamente lo que el
operador confirmó al aprobar este documento como el paso siguiente.

---

## 1 · El watchdog de proceso

### 1.1 · Qué detecta y cómo (el mecanismo, no solo la herramienta)

Un watchdog que solo comprueba "¿el proceso `python.exe` sigue en la lista de procesos?" no basta: un
proceso puede seguir vivo (el intérprete no ha muerto) pero **colgado** — bloqueado en una llamada de red
que nunca vuelve, en un deadlock, en un bucle que ya no avanza. Eso es indistinguible de "vivo y
funcionando" para cualquier comprobación que solo mire la lista de procesos. Hace falta una señal que el
propio bot escriba **mientras avanza de verdad**, no solo mientras existe.

**Mecanismo: fichero de latido (`latido.json`), escrito por el bot cada `latido_intervalo_s` segundos**
(número nuevo, sin medir todavía — candidato de `03_CONFIG.yaml`, sección de despliegue, cuando D8
exista; provisional 30 s, mismo orden de magnitud que `dashboard.rancio_seg` de §9 de `03_CONFIG.yaml`,
mismo principio: "un dato viejo tiene que parecer viejo"). Contenido mínimo:

```json
{"ts_iso": "2026-08-20T15:30:00+00:00", "pid": 12345, "fase": "sondeo_sesion",
 "dia_negociacion": 210, "patas_abiertas": ["hedge", "prop"]}
```

Escrito con el mismo patrón que `bot/estado.py::guardar()` ya usa para `estado.json` (fichero temporal +
`fsync` + `os.replace` — nunca se deja un `latido.json` a medio escribir que un watchdog pueda leer
corrupto). **No es el mismo fichero que `estado.json`**: `estado.json` se escribe en las transiciones de
estado (una vez por día o menos), demasiado espaciado para detectar un cuelgue en minutos; `latido.json`
se escribe con cadencia fija, exista o no una transición de estado ese instante — es una señal de "sigo
vivo y avanzando", no una señal de negocio.

**Esto es un requisito nuevo para el bucle principal de D8, no construido en esta sesión** (D8 no existe
todavía — ver `05_ORDEN_DE_CONSTRUCCION.md`, Fase 2). Se documenta aquí, en el entregable de despliegue,
para que quien construya D8 sepa que el watchdog lo espera desde el primer día, no como un añadido a
posteriori.

### 1.2 · Qué hace el watchdog al detectar un `latido.json` rancio o ausente

| lo que observa | qué significa | qué hace |
|---|---|---|
| `latido.json` no existe todavía | el bot no ha arrancado, o arrancó hace menos de un ciclo de comprobación | espera al siguiente ciclo — no es una alarma en sí misma en el primer minuto tras el arranque |
| `latido.json` existe pero su edad supera `latido_rancio_umbral_s` (provisional: 3× `latido_intervalo_s`, mismo principio de margen que `N_hedge` frente a `N` en `07_ADAPTADOR_NT8.md` §5.2b — varias veces el intervalo esperado, no el intervalo exacto) | el proceso está muerto, colgado, o la máquina no puede escribir a disco | **alerta inmediata de máxima prioridad** (mismo canal que las alertas del propio bot, §7 de `07_ADAPTADOR_NT8.md`) y **reinicio del proceso** — Task Scheduler relanza el bot, que al arrancar sigue la reconciliación de `07_ADAPTADOR_NT8.md` §6 (si las dos patas coinciden con `estado.json`, retoma la sesión; si no coinciden, es "una sola pata" y para) |
| el proceso se reinicia pero vuelve a quedar rancio en menos de `latido_reinicios_ventana` (provisional: 3 reinicios en 15 minutos) | el reinicio no está arreglando nada — algo estructural está roto (no un cuelgue transitorio) | **deja de reintentar reinicios automáticos**, escalada a la máxima prioridad de alerta y espera intervención humana explícita — reiniciar en bucle contra un fallo estructural es peor que pararse: puede mandar la misma orden rota una y otra vez si el fallo está en el propio arranque |

**Por qué "reiniciar" es seguro incluso con una posición real abierta.** La reconciliación de
`07_ADAPTADOR_NT8.md` §6 existe exactamente para esto — "reinicio a media sesión" con las dos patas
coincidiendo con `estado.json` es un caso ya cubierto y ya no re-ejecuta la entrada de `b0` (violaría
R-3.7). El watchdog no necesita saber nada de patas ni de posiciones: reiniciar el proceso es seguro
**porque** el propio proceso, al arrancar, sabe reconciliarse solo. Si algún día esa reconciliación deja
de ser fiable, el problema está en `07_ADAPTADOR_NT8.md` §6, no en el watchdog.

### 1.3 · Implementación: Task Scheduler, con el script adjunto

**`watchdog_bot.ps1`** (fichero adjunto junto a este documento) implementa el mecanismo de arriba:
lee `latido.json`, calcula su edad, decide si reinicia o solo alerta, y lleva la cuenta de reinicios en
una ventana deslizante (fichero `watchdog_reinicios.json` junto al propio watchdog, mismo patrón de
escritura atómica). Se programa como una tarea de **Task Scheduler** que se dispara cada
`latido_intervalo_s` (o un poco más frecuente — comprobar más a menudo que se escribe el latido no hace
daño, comprobar menos sí).

```powershell
# Registro de la tarea (ejecutar una vez, como administrador):
$accion = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File C:\ruta\al\bot\watchdog_bot.ps1"
$disparador = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Seconds 30) -RepetitionDuration ([TimeSpan]::MaxValue)
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "CircuitoCubierto-Watchdog" -Action $accion `
    -Trigger $disparador -Settings $config -RunLevel Highest
```

**Aviso de honestidad (mismo que `da1_diagnostico.ps1`, `07_ADAPTADOR_NT8.md` §8):** `watchdog_bot.ps1`
se ha revisado a mano (llaves/paréntesis balanceados, lógica trazada línea por línea contra la tabla de
§1.2), pero **no se ha podido ejecutar contra un Task Scheduler real** — este entorno de ingeniería es
Linux. La primera vez que se registre en una máquina Windows real es una comprobación más que R3 exige
ver pasar (o fallar y corregir) con la salida pegada, no darse por buena a priori: forzar un latido
rancio a mano (parar el bot, o simplemente no escribir `latido.json`) y confirmar que el watchdog lo
detecta, alerta, y reinicia — antes de confiar en él con dinero real.

**Complemento probado de verdad, 20-08-2026:** aunque `watchdog_bot.ps1` en sí sigue sin poder correrse
en este entorno Linux, su LÓGICA DE DECISIÓN (edad de `latido.json` contra un umbral, §1.2) sí se portó a
Python únicamente para poder probarla aquí —
`verificacion_R3/integracion_proceso_real/logica_watchdog.py`, ejercitada en
`prueba_watchdog_latido_rancio.py` contra un proceso real detenido con `SIGSTOP` (no cooperativo: el
proceso sigue en la tabla de procesos pero no ejecuta nada, exactamente el caso que un simple "¿sigue en
`ps`?" no distinguiría de estar sano) — confirmado que no dispara en falso mientras el proceso late, y
que sí dispara pasado el umbral con el proceso genuinamente detenido. Esto NO sustituye la comprobación
contra Task Scheduler real de arriba — es la mitad que sí se pudo verificar sin Windows.

---

## 2 · Arranque automático al reiniciar la máquina

Una caída de la máquina entera (no solo del proceso del bot) es un caso más del mismo problema: nadie
puede reiniciar el bot a mano si nadie se ha dado cuenta de que la máquina se reinició. Task Scheduler
cubre esto de forma directa con un disparador adicional en la misma tarea:

```powershell
$disparador_arranque = New-ScheduledTaskTrigger -AtStartup
```

(añadido a la definición de §1.3 — la tarea del watchdog dispara tanto en el ciclo periódico como al
arrancar Windows). **El propio bot** también necesita un disparador equivalente para arrancarse a sí
mismo (el watchdog reinicia un proceso que ya existía; si la máquina se acaba de reiniciar, no hay
proceso que reiniciar — hay que arrancarlo de cero). Misma técnica, tarea separada, disparador
`-AtStartup`, sin repetición.

**Decisión abierta, para cuando exista D8:** si el arranque automático debe ser incondicional (arranca
siempre que la máquina arranca) o si debe exigir una confirmación humana explícita el primer día tras
cualquier reinicio no planificado — el operador no ha decidido esto todavía. Provisional, conservador:
**exige confirmación** (una bandera en disco, `arranque_confirmado.flag`, que el operador borra tras cada
intervención suya, y que el arranque automático comprueba antes de operar — si no está, el bot arranca en
modo "sondeo y reconciliación, sin operar" y alerta pidiendo confirmación explícita). Se decide con el
operador antes de que D8 dependa de esto de verdad.

---

## 3 · Permisos y cuenta de servicio

| qué | recomendación | por qué |
|---|---|---|
| cuenta bajo la que corre el bot y el watchdog | cuenta de usuario dedicada, no la cuenta personal del operador ni una cuenta de administrador de dominio | el bot manda órdenes reales de dinero — el radio de lo que puede salir mal si esa cuenta se ve comprometida debe limitarse a "esta máquina, este bot", nunca a todo lo demás a lo que la cuenta personal del operador tenga acceso |
| permisos de esa cuenta sobre la carpeta del bot | lectura/escritura sobre `estado.json`, `latido.json`, `comandos/`, `laboratorio/` — nada fuera de esa carpeta | mismo principio de mínimo privilegio; un bug que escriba donde no debe queda contenido a la propia carpeta |
| `Register-ScheduledTask -RunLevel Highest` (§1.3) | necesario para que Task Scheduler pueda reiniciar un proceso de otra sesión de usuario si NT8 corre con privilegios elevados | **decisión abierta:** depende de si NT8 en la máquina del operador corre elevado o no — se confirma la primera vez que se instale de verdad, no se asume aquí |
| credenciales de MFF/Tradovate/AMP-CQG | nunca en texto plano en ningún fichero de este repositorio ni en `03_CONFIG.yaml` — viven en NT8 (Control Center → Accounts) o, si el bot algún día las necesita fuera de NT8, en el almacén de credenciales de Windows (`cmdkey` / Credential Manager), nunca en disco sin cifrar | mismo principio de `04_GUARDARRAILES_CONSTRUCCION.md`: ningún número ni secreto sale de la cabeza de nadie ni queda expuesto por descuido |

---

## 4 · Registro de build de NT8 validado

`07_ADAPTADOR_NT8.md` §9 lo señala como un riesgo sin mitigar del todo: *"si el puente se rompe con una
actualización de NT8, no hay a quién preguntar"* — y anota que este documento es donde vive el registro
de contra qué build se validó por última vez. **D-A1 (`07_ADAPTADOR_NT8.md` §8) es una suite de
regresión reejecutable** — la respuesta a una actualización de NT8 no es "confiar en que seguirá
funcionando", es volver a correr `da1_diagnostico.ps1` entero y comparar contra el registro de abajo.

**Formato del registro** (`registro_build_nt8.jsonl`, un objeto JSON por línea, append-only — mismo
principio que el diario de `bot/orquestador.py`, nunca se reescribe una línea vieja):

```json
{"fecha": "2026-08-20", "build_nt8": "8.1.x.x (rellenar con Help -> About tras D-A1.0)",
 "resultado_da1": "PENDIENTE -- sin maquina Windows todavia",
 "resultado_da1_3": "PENDIENTE", "resultado_da1_4": "PENDIENTE",
 "operador": "(nombre/usuario que lo corrio)", "notas": ""}
```

**Cuándo se añade una línea nueva:**
- Cada vez que se corre `da1_diagnostico.ps1` de verdad contra una máquina (primera vez, o tras una
  actualización de NT8) — con el resultado real, no "PENDIENTE".
- Antes de escalar capital en Fase 3 (`05_ORDEN_DE_CONSTRUCCION.md`) — para que la decisión de arriesgar
  más dinero tenga a la vista contra qué build está validado el puente, no una suposición.

**Antes de la primera vez que haya máquina Windows disponible, este registro solo tiene la línea
`PENDIENTE` de arriba** — es la plantilla, no un resultado. R3 aplica exactamente igual aquí que en
cualquier otro sitio: no se rellena con un valor inventado solo por completar la tabla.

---

## 5 · Qué NO cubre este documento (dicho explícito)

- **Alta disponibilidad / redundancia** (una segunda máquina en espera) — fuera de alcance mientras el
  capital en juego sea el de Fase 3.1/3.2 (`05_ORDEN_DE_CONSTRUCCION.md`); se revisita si el capital
  escala lo suficiente para justificar el coste operativo.
- **El propio `latido.json` y su escritura periódica** — es responsabilidad del bucle principal de D8,
  no de este documento (documento, no código). Documentado en §1.1 para que D8 lo construya desde el
  principio.
- **Qué hace el bot al reiniciar tras una caída** — eso ya está resuelto, y en otro documento:
  `07_ADAPTADOR_NT8.md` §6 (reconciliación). Este documento solo cubre cómo se nota que hace falta
  reiniciar y quién lo dispara.

---

## 6 · Historial de verificación

- **20-08-2026, revisión 1** — documento redactado tras el cierre de la revisión 4 de D-C
  (`07_ADAPTADOR_NT8.md`, `08_LABORATORIO.md`), siguiendo la confirmación explícita del operador de que
  este era el siguiente paso y que no depende de NT8 real. Cubre los cuatro puntos que
  `05_ORDEN_DE_CONSTRUCCION.md` fijaba como su alcance (watchdog, arranque automático, permisos, registro
  de build validado). `watchdog_bot.ps1` adjunto, revisado a mano, **sin ejecutar contra un Task
  Scheduler real** — mismo aviso de confianza que `da1_diagnostico.ps1`, misma razón (este entorno de
  ingeniería es Linux). Dos decisiones quedan abiertas a propósito, para el operador, en vez de
  inventadas: si el arranque automático debe exigir confirmación humana tras un reinicio no planificado
  (§2), y si la tarea de Task Scheduler necesita `-RunLevel Highest` (depende de cómo corra NT8 en la
  máquina real, §3). **Sigue sin validarse contra una máquina Windows real.**
