# 11 · MANUAL DEL OPERADOR · qué hacer, cada día, con el circuito ya corriendo

### Entregable de D8 §5.5 (`ORDEN_DE_TRABAJO_D8.md`), tras cerrar los cuatro días
adversarios de §5.1-§5.4 (sorteo de dirección, bloqueo de funded, pool agotado,
degradación) y la prueba de caos. Documento, no código — como `09_DESPLIEGUE.md`.

**Para quién es esto.** Para ti, operando el circuito en Fase 2 (papel) o más
adelante en real — no para quien lo programa. No repite la aritmética de negocio
(eso está en `01_ESPECIFICACION_E2E.md`) ni el diseño de seguridad (`10_SEGURIDAD.md`)
— es el manual de "qué miro cada día, qué hago cuando algo se pone en rojo, y qué
comando escribo para cada cosa".

---

## 1 · Arrancar y parar

El bot es **una llamada**: `bot/bucle_del_dia.py::bucle_del_dia(fuente_barras,
adaptador, ...)`. En producción se invoca **una vez por día de negociación**
(no es un proceso que corre para siempre sin parar — cada invocación procesa los
días que la fuente de barras tenga disponibles y devuelve). Cada invocación:

1. Toma un bloqueo de proceso (`bot/bloqueo_proceso.py`) — **una segunda instancia
   nunca arranca** mientras la primera siga viva (verificado con subprocesos
   reales, `verificacion_R3/prueba_bloqueo_proceso.py`).
2. Carga `estado.json`. Si está corrupto o ausente de forma anómala, sube a **N4**
   y **no arranca** — nunca adivina ni reconstruye a la brava.
3. Si el nivel de contención (ver §3) no es `N0`, **no opera** — devuelve el
   estado tal cual y no toca el bróker para nada más de lo que ya estuviera hecho.
4. Reconcilia contra el bróker real (`bot/reconciliacion.py`) — compara lo que el
   bróker reporta con lo que `estado.json` esperaba. Si no coincide, no arranca.
5. Procesa los días disponibles, uno a uno, con `bot/orquestador.py::procesa_dia()`
   (la MISMA función que valida el replay de 504 días — nunca una aritmética
   "equivalente" reimplementada para producción).
6. Al final de cada día: valida los 8 invariantes fatales, persiste
   `estado.json`/una instantánea rotatoria, añade una línea a `diario.jsonl`.

**Parar el bot** no es una acción tuya del día a día — el bot para solo, entre
días, cuando termina de procesar los que tenía disponibles, o de inmediato si el
nivel de contención deja de ser `N0` (§3). Para forzar una parada mientras algo
está corriendo, el comando de Clase A es `parada_total` (§6) — no matar el
proceso a mano salvo emergencia real (si lo haces, el bot se reconcilia solo al
reiniciar, pero es el camino menos limpio).

**Ficheros que necesita** (rutas configurables al invocar, ninguna es un
"secreto" fijo): `estado.json`, `nivel.json` (aparte, a propósito — un
`estado.json` corrupto no puede llevarse consigo la propia contención, ver
`bot/seguridad.py`), `diario.jsonl` (append-only, nunca se reescribe), un
directorio de instantáneas rotatorias, un directorio de comandos (§6), un
fichero de bloqueo de proceso.

---

## 2 · Los tres ficheros que gobiernan todo

| Fichero | Qué es | Con qué frecuencia cambia |
|---|---|---|
| `estado.json` | Todo el negocio: caja, funded, eval, recámara, pool, `degradado`, `desviaciones_activas` | Una vez por día procesado |
| `nivel.json` | El nivel de contención N0-N4 y su historial (motivo, **causa tipada**, quién) | Solo cuando algo escala o un humano baja |
| `diario.jsonl` | Una línea por día: dirección, ventana, eventos del día, fin de día | Una línea por día procesado |

**Nunca edites `diario.jsonl` a mano** (append-only, por diseño). `estado.json` y
`nivel.json` SÍ los edita un humano en casos concretos (§4, §5) — siempre con el
mismo patrón de escritura atómica que usa el propio bot (fichero temporal +
`fsync` + `os.replace`), nunca sobrescribiendo a medias.

---

## 3 · La escalera de contención N0-N4

*"El sistema sube solo; solo baja con un humano"* — pero **no todos los niveles
bajan igual**, y desde la revisión de degradación (`DECISION_DEGRADACION_N3.md`)
la escalera es **una sola**, para todas las causas (posición descuadrada,
estado corrupto, degradación de tesorería, reconciliación, presupuesto de
reinicios agotado — el vocabulario completo vive en `bot/seguridad.py::CAUSAS`).

| Nivel | Nombre | Qué significa | Quién lo baja |
|---|---|---|---|
| N0 | NORMAL | Opera con normalidad | — |
| N1 | SIN_APERTURAS | No abre posiciones nuevas; lo ya abierto sigue su curso | **Automático** — "al desaparecer la causa" (hoy sin cablear, ver §7) |
| N2 | PLANO_Y_PARADO_HOY | Se aplanó todo; no vuelve a abrir hoy | **Automático** — "al día siguiente" (hoy sin cablear, ver §7) |
| N3 | KILL | Parada dura — nunca reanuda solo | **Humano, explícito** (`baja_humana()`) |
| N4 | CONGELADO | Estado no fiable — ni se lee ni se adivina | **Humano, explícito** (`baja_humana()`) |

**Qué hacer al ver cada nivel en el panel** (bloque 1, "Nivel de contención" —
mira también la **causa** que se pinta al lado, nunca solo el nivel a secas):

- **N1/N2**: revisa la causa (`reconciliacion` casi siempre — conexión caída, o
  una liquidación forzosa ya resuelta). Si la causa ya no aplica (reconectado,
  liquidación ya cerrada), **hoy no hay un botón automático** que lo baje (§7) —
  usa tu propio criterio y, si corresponde, baja el nivel tú mismo con la misma
  función que usaría el mecanismo automático (`baja_humana()`, aunque N1/N2 no
  lo exijan por norma, es la única vía operativa disponible hoy).
- **N3 · causa `degradacion_tesoreria`**: **esto es serio.** Significa que la
  caja viva cruzó por debajo del muro dinámico — el capital ya no cubre lo que
  el circuito tiene comprometido. El bot ya está plano (la degradación se
  detecta DESPUÉS de cerrar el día). No lo reabras sin **reponer capital**
  (hasta que `caja - retirado ≥ -muro`) o **decidir reducir el tamaño del
  circuito** (el modelo no simula el régimen reducido — es una extensión, no
  un botón de hoy). Si bajas el nivel sin arreglar la causa real, el bot
  **vuelve a subir a N3 él solo, al día siguiente** — es la barrera funcionando,
  no un bug (verificado, `verificacion_R3/prueba_degradacion.py`).
- **N3 · otras causas** (`posicion_descuadrada`, `presupuesto_reinicios`): revisa
  `nivel.json`'s historial completo (motivo + causa) antes de nada — un tamaño
  que no corresponde entre las dos patas casi siempre significa un bug propio o
  una manipulación (catálogo G), no algo que se "reintenta" sin mirar.
- **N4 · causa `estado_corrupto`**: no reconstruyas `estado.json` a mano ni
  adivines. Localiza la última instantánea rotatoria buena (directorio de
  instantáneas) y decide desde ahí, con calma — nunca bajo presión de "que
  vuelva a andar ya".

**Cómo bajar el nivel, en la práctica** (Python, desde donde tengas el repo):
```python
from bot import seguridad as SEG
SEG.baja_humana("ruta/a/nivel.json", "N0", quien="tu_nombre_real",
                 motivo="capital repuesto, caja por encima del muro")
```
`quien` es obligatorio y **nunca** puede ser `"sistema"` (esa palabra está
reservada para las transiciones automáticas) — es la barrera que impide que
nada automatizado se haga pasar por tu autorización.

---

## 4 · Leer el dashboard

`bot/dashboard.py::genera_html(ctx)` sobre `bot/contexto_dashboard.py::construye(...)`
— un único HTML autocontenido, sin red, ocho bloques:

1. **AHORA** — dirección, ventana, patas abiertas, conexiones, semáforo global
   (ahora refleja el nivel N0-N4 completo, no solo si hay degradación), y el
   **nivel de contención con su causa tipada** (nunca el nivel solo).
2. **RIESGO** — caja, retirado, tesorería viva, muro dinámico, distancia a la
   degradación.
3. **PENDIENTES DEL HUMANO** — dos relojes distintos, nunca fundidos: el del
   bot (`bloqueada_escalada_dias`, 5 días) y el del proveedor
   (`proveedor_mata_cuenta_dias`, ~7 días, `SUPUESTO` con virgulilla — no
   `DADO`). **Hoy este bloque casi siempre aparece vacío** — ver el hueco de
   §7, nada lo rellena todavía automáticamente.
4. **CUENTAS** — eval, fondeada, recámara (dormidas + `sunk_total`), pool
   (frescas/rotas).
5. **MERCADO Y FRICCIÓN** — horquilla actual, proyecciones de fricción vs. las
   líneas ya medidas (verde/ámbar/rojo).
6. **MODELO vs REALIDAD** (E6) — tasas observadas vs. esperadas, con el aviso
   explícito de "todavía no concluye" mientras `n < 25`.
7. **LABORATORIO** — progreso de cada estimador (E1-E6) hacia su `n` mínimo.
8. **INCIDENCIAS** — el log crudo de incidencias recientes, con contadores.

Genera el dashboard leyendo `estado.json`/`diario.jsonl`/`nivel.json` **de
disco** (nunca reutilices estructuras en memoria de otro proceso — el pipeline
completo disco→panel está probado así,
`verificacion_R3/prueba_dashboard_corrida_real.py`).

---

## 5 · Comandos del operador

Dos clases, escritas como ficheros JSON en el directorio de comandos
(`bot/comandos.py`) — **nunca se editan ni se borran**, un `id` nuevo por
comando:

- **Clase A** (`aplanar_ambas`, `parada_dia`, `parada_total`, `cancelar_orden`):
  se sondean de forma continua durante la sesión — acción inmediata.
- **Clase B** (`empalme`, `contra`, `emergencia`, `pausa_eval`): palancas
  on/off que **desactivan** una regla certificada de `03_CONFIG.yaml` por un
  número de días explícito — solo se consultan en el punto de decisión del
  día siguiente. **Exigen `duracion_dias` explícito** en `parametros` — nunca
  hay un valor por defecto, para que no se te cuele una desactivación sin
  querer.

Ejemplo de un comando de Clase B (apagar CONTRA 5 días):
```python
from bot import comandos as CMD
CMD.escribe_comando("ruta/a/comandos", dict(
    id="2026-08-25-001", ts_pared=CMD.ahora_iso(), tipo="contra",
    parametros=dict(duracion_dias=5), caduca_en="2026-08-26T00:00:00+00:00",
    quien="tu_nombre_real"))
```
La palanca queda activa mientras el día actual caiga dentro de
`[desde_dia, hasta_dia)` en `estado.desviaciones_activas` — se ve reflejada en
el panel (bloque de desviaciones activas) y en el propio `estado.json`.

**No hay Clase C** desde el dashboard — cualquier `tipo` que no sea de A o B
se rechaza (`ComandoInvalidoError`), a propósito.

---

## 6 · Días adversarios ya probados — qué esperar de cada uno

(Cobertura por escenario, `verificacion_R3/CENSO_COBERTURA.md` es la fuente
regenerada; esto es el resumen operativo.)

- **Sorteo de dirección + veto CONTRA**: sorteo 50/50 diario; tras cualquier
  muerte, la dirección se mantiene `contra_dias` días (hoy: 1) salvo que
  apagues la palanca `contra`. No requiere ninguna acción tuya salvo que
  quieras desactivarla deliberadamente.
- **Bloqueo de funded (R-2.4)**: si funded queda bloqueada (tamaño exigido
  <1 contrato), se desactiva ese mismo día — el relevo intenta con la
  siguiente dormida al día siguiente sin esperar. **Si la recámara está
  vacía**, funded se queda esperando indefinidamente, sin abrir nada — esto es
  normal (no hay dormidas que activar), no una alarma. Ver el hueco de §7:
  hoy nada te avisa de cuántos días lleva esperando.
- **Pool agotado**: si el pool se queda sin subs (ni frescas ni rotas
  disponibles vía emergencia), eval simplemente no arranca ese día — sin
  romper nada, sin coste extra salvo el fijo de mantener el pool. Se recupera
  solo en cuanto un reset libera una sub.
- **Degradación**: ver §3 — para de verdad, en N3.

---

## 7 · Huecos conocidos, aceptados por el operador — qué hacer TÚ mientras tanto

Dos huecos reales, **decididos deliberadamente por el operador, no arreglados
todavía** (`RESPUESTA_D8_ITEM2_BLOQUEO.md`, `ORDEN_DE_TRABAJO_D8.md` §5):

1. **Bloqueo/espera sostenida de funded no genera ningún aviso automático.**
   Ni el bloque 3 del dashboard (depende de una clave que hoy nadie escribe)
   ni la escalera N0-N4 reaccionan a que funded lleve muchos días sin operar.
   **Qué hacer tú:** revisa el bloque 4 (CUENTAS) del dashboard tú mismo,
   cada vez que lo mires — si `funded.activa=false` y la recámara está vacía
   desde hace varios días, esa es tu única señal hoy. No hay número de días
   umbral certificado todavía (`alertas.bloqueada_escalada_dias`=5,
   `alertas.proveedor_mata_cuenta_dias`≈7, SUPUESTO) — son los que usarás tú
   mismo, a ojo, hasta que se cablee.
2. **N1/N2 no bajan solos** pese a que la norma dice que deberían. **Qué
   hacer tú:** cuando veas N1/N2 en el panel, revisa la causa; si ya no
   aplica, bájalo tú con `baja_humana()` (§3) — es la única vía operativa
   hasta que exista el mecanismo automático.

Un tercero, bloqueado por falta de acceso, no por decisión: **temporización
real** (confirmar `N`/`N_hedge`/`latido_intervalo_s`/`latido_rancio_umbral_s`
contra el proceso real de Fase 2) necesita datos reales de papel que solo tú
puedes generar operando — esta sesión no tiene acceso a esa máquina.

Tres preguntas abiertas, sin contestar todavía por nadie (ni el operador ni
esta sesión) — `ORDEN_DE_TRABAJO_D9.md` §8: son decisión del operador, esta
sesión solo las anota:

1. **¿La regla de inactividad de MyFundedFutures también mata dormidas en
   recámara** (no solo funded activa)? Verifícalo contra la normativa real
   del proveedor antes de dar por sentado que la recámara está a salvo
   mientras espera semanas sin operar. **No bloquea F3.1** (una evaluación
   sola, sin recámara todavía) — bloquea **F3.3**, que es cuando habrá
   dormidas esperando de verdad.
2. **Política de bots de Topstep**, por escrito — necesaria antes de
   considerar Topstep como segundo proveedor (multicuenta, fuera de alcance
   hasta después de F3.1).
3. **Carve-out de resets de Tradeify frente al tope de 15 evaluaciones**,
   por escrito — misma condición que el punto anterior.

---

## 8 · Checklist diario (Fase 2, papel)

- [ ] Nivel de contención en N0. Si no, ir a §3.
- [ ] Bloque RIESGO: distancia a la degradación con margen razonable.
- [ ] Bloque CUENTAS: si funded está inactiva, ¿cuántos días lleva la
      recámara vacía? (hueco de §7, vigilancia manual).
- [ ] Bloque PENDIENTES: si aparece algo, mirar los dos relojes por separado.
- [ ] Bloque INCIDENCIAS: nada inesperado desde la última revisión.
- [ ] `diario.jsonl` de hoy escrito (una línea nueva, `dia_negociacion`
      avanzó en 1).
