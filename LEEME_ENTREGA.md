# LEEME · entrega de la sesión de ingeniería (D2-D7 + D-C + simulador_nt8), 20-08-2026

Este fichero es el índice de ESTA entrega — `00_LEEME_PRIMERO.md` es del paquete original v10 y sigue
siendo válido para el contexto de fondo (norma, arquitectura, guardarraíles). Empieza por aquí si vienes
directo al zip sin haber leído la conversación.

**Esta es la TERCERA vuelta.** La primera entregó D-C (7 comprobaciones en verde). El operador la revisó
de forma independiente y encontró **tres defectos reales** en el protocolo de las dos patas — la segunda
vuelta los corrigió, cableó las recomendaciones pendientes, resolvió las alertas de cuenta bloqueada como
dos relojes distintos, y añadió `09_DESPLIEGUE.md`. **Esta tercera vuelta añade `simulador_nt8/`**: a
petición del operador, un simulador de NT8 **independiente y fuera de proceso** — proceso de sistema
operativo aparte del bot, mismo contrato de puerto que `07_ADAPTADOR_NT8.md` §1, para probar el protocolo
de las dos patas, el vigía de conexión, y la reconciliación de arranque (§6) bajo una frontera de
proceso/red REAL: matando procesos con `kill -9`/`SIGSTOP`, con timeouts de reloj de pared reales. El
propio simulador se sometió después a una revisión adversarial de cinco lentes independientes (cada
hallazgo re-verificado por un segundo revisor escéptico con código real, no de oídas) — **ocho hallazgos
confirmados, los ocho corregidos y re-verificados**, incluida una condición de carrera real (reproducida
de forma determinista) y una vía de reflexión sin filtrar en el canal de control. Detalle completo:
`07_ADAPTADOR_NT8.md` §12, revisiones 5 y 6.

## Qué hay dentro

- **`00`-`09_*.md`, `03_CONFIG.yaml`** — la norma y el contrato. Los que cambiaron en esta entrega:
  `05_ORDEN_DE_CONSTRUCCION.md` (delta D-C, revisión 4 anotada), `07_ADAPTADOR_NT8.md` (protocolo de las
  dos patas, **revisión 4** — los tres defectos y sus correcciones, documentados rama por rama en §5.3),
  `08_LABORATORIO.md` (revisión 4 en el historial §12), y **`09_DESPLIEGUE.md`, nuevo** (watchdog de
  proceso, arranque automático, permisos, registro de build de NT8 validado — documento, no código, no
  necesita NT8 para escribirse). `03_CONFIG.yaml` §10 reescrita: dos claves separadas para las alertas de
  cuenta bloqueada (`bloqueada_escalada_dias` del bot, `proveedor_mata_cuenta_dias` del proveedor), no una.
- **`bot/`** — el código. D0-D7 (config, sizing, sesión, calendario, ciclo de vida, tesorería,
  orquestador) siguen verdes tras los cambios de hoy — 504/504 días, 0 divergencias, bit-idéntico incluso
  después de cablear las recomendaciones 1/2/5. Cambios de esta revisión: `protocolo_dos_patas.py`
  (los tres defectos), `adaptador_falso.py` (modo `rechaza_aplanar_cantidad_cero` para poder fabricar el
  defecto 3 a propósito), `comandos.py` (`valor_efectivo` ya cableado, no solo construido), `ciclo_vida.py`
  + `calendario.py` + `orquestador.py` + `estado.py` (el cableado de las recomendaciones 1/2/5),
  `dashboard.py` + `contexto_dashboard.py` (los dos relojes de cuenta bloqueada, bloque 3; `muertes_eval`
  ya no dice "no trackeado", bloque 6).
- **`verificacion_R3/`** — los scripts de autorruptura (R3, 04_GUARDARRAILES): cada uno rompe algo a
  propósito y pega la salida real. `romper_mi_orquestador.py` (5 patrones de D2-D7 — el caso 5 reconstruido
  en esta revisión: su ancla de texto había dejado de coincidir tras cablear las recomendaciones y se
  saltaba en silencio en vez de cazar el bug; ahora vuelve a cazarlo de verdad), `d2_mata_el_proceso.py`
  + `_d2_escritor.py` (kill -9 real, 10 puntos), `prueba_protocolo_dos_patas.py` (**40 comprobaciones**,
  las 7 originales más las secciones 8/9/10 de los tres defectos de esta revisión), `prueba_comandos.py`
  (15, caducidad/idempotencia/Clase B silenciosa — sin regresión tras el cambio de firma de
  `valor_efectivo`), `prueba_dashboard.py` (14, dato rancio/n insuficiente/E1 bloqueado + paleta). **Se
  pueden correr tal cual, desde dentro de esta carpeta** (`python3 verificacion_R3/<script>.py`) — no
  hace falta reconstruir nada, todas las rutas ya están resueltas para la estructura de este zip.
- **`dashboard_ejemplos/`** — HTML autocontenidos ya generados, incluido uno nuevo con una cuenta
  bloqueada mostrando los dos relojes por separado. Ábrelos con dos clics, cualquier navegador — son
  ficheros locales, sin servidor, sin red.
- **`IndicadorLaboratorioMercado.cs`** — el indicador NinjaScript de la Rama B (§1.1). **Sin compilar ni
  verificar contra NT8 real** — ver `RECOMENDACIONES.md` §4, sin cambios en esta revisión.
- **`da1_diagnostico.ps1`** — sin cambios en esta revisión, sigue pendiente de una máquina Windows con NT8.
- **`RECOMENDACIONES.md`** — las siete originales, cada una con su estado real actualizado (1, 2 y 5
  hechas; 3 resuelta como dos relojes; 4 sigue bloqueada por falta de máquina; 6 era este mismo
  `09_DESPLIEGUE.md`, ya escrito; 7 confirmada como alcance de D8).
- **`REVISION_ENTREGA_20260820.md`** — la revisión del operador que motivó esta segunda vuelta, incluida
  tal cual para que el rastro quede completo.
- **`DEMOSTRACIONES_R3_DEFECTOS_20260820.md`** — punto 7 del plan de acción del operador: los tres
  defectos, vistos fallar de verdad con el código de antes de esta revisión (reconstruido literal, nunca
  narrado) y confirmados corregidos con el código real — salida pegada, no una afirmación. Script fuente:
  `verificacion_R3/demuestra_defectos_operador_20260820.py`.
- **`watchdog_bot.ps1`** — el script de `09_DESPLIEGUE.md` §1.3 (watchdog de proceso vía Task Scheduler).
  Igual de sin verificar contra una máquina Windows real que `da1_diagnostico.ps1` — mismo aviso de
  honestidad, dicho explícito en el propio fichero.
- **`tests/`, `modelo/`, `core/`** — el paquete original, R6 (nunca tocados por esta sesión salvo
  `modelo/cifras_citadas.py`, sustituido por instrucción explícita tuya en una sesión anterior).
- **`simulador_nt8/`, nuevo** — el simulador de NT8 independiente y fuera de proceso (protocolo.py,
  errores.py, motor.py, servidor.py, cliente.py, cliente_control.py, `LEEME.md`). **Empieza por
  `simulador_nt8/LEEME.md`** — el aviso de qué es y qué NO es esto (no sustituye D-A1 contra NT8 real).
  Sometido a una revisión adversarial de cinco lentes tras construirse: 8 hallazgos confirmados, los 8
  corregidos (incluida una condición de carrera real en el acceso concurrente a `AdaptadorFalso`, y una
  vía de reflexión sin filtrar en el canal de control que exponía los métodos dunder de `AdaptadorFalso`)
  — detalle en `07_ADAPTADOR_NT8.md` §12, revisión 6.
- **`verificacion_R3/integracion_proceso_real/`, nuevo** — la suite de `simulador_nt8/`: 9 ficheros,
  **83/83 comprobaciones**, incluidos `arnes_bot_minimo.py` (doble MÍNIMO de "D8" — **no es D8**, solo
  para tener un proceso real que matar/reiniciar) y `logica_watchdog.py` (puerto a Python, solo para
  poder probar aquí la lógica de decisión de `watchdog_bot.ps1` sin Windows).

## Puertas verificadas en esta entrega (todas, de una sentada, antes de empaquetar)

```
D0  · tests/comprueba_config.py              -> OK + 6 auto-verificaciones
D1  · tests/runner_goldens_v10.py            -> 14/14 goldens OK
Fase 1 · tests/runner_replay_v10.py          -> 504 dias · 0 fallos (caja final 29.134,87 $)
                                                 -- RE-VERIFICADO tras cablear valor_efectivo()/
                                                    muertes_eval/k,m: BIT-IDENTICO, sin cambio.
D2  · verificacion_R3/d2_mata_el_proceso.py  -> 10/10 (kill -9 real)
D2-D7 (self-breaks) · romper_mi_orquestador.py -> 5/5 roturas detectadas (las 5 cazando de verdad,
                                                 incluido el caso 5 reconstruido en esta revisión)
D-C  · prueba_protocolo_dos_patas.py         -> 40/40 (7 originales + 3 defectos de esta revisión)
D-C  · prueba_comandos.py                    -> 15/15 (caducidad, idempotencia, Clase B)
D-C  · prueba_dashboard.py                   -> 14/14 (rancio, n insuficiente, E1 bloqueado, paleta)
D-C  · bot/paleta.py                         -> PALETA OK
simulador_nt8 · integracion_proceso_real/*.py -> 83/83 (9 ficheros, tras la revision adversarial)
                                                 -- Fase 1 re-verificada BIT-IDENTICA tras estos cambios
```

**Dos bugs cazados en la primera vuelta** (`08_LABORATORIO.md` §12, historial): un `aplanar()` sin
confirmar en las ramas de aborto de `protocolo_dos_patas.py`, y `dashboard.py` calculando la frescura de
un snapshot sin llegar a pintarla.

**Tres defectos reales encontrados por el operador y corregidos en esta revisión** (detalle completo en
`07_ADAPTADOR_NT8.md` §5.3 revisión 4 y `08_LABORATORIO.md` §12):
1. Un `RECHAZADA`/`CANCELADA` limpio e inmediato del bróker se trataba igual que "el timeout expira" —
   desperdiciaba `N`/`N_hedge` sin necesidad y, en el caso de la prop, dejaba el hedge desnudo ese tiempo
   de más.
2. `hay_conexion()` nunca se llamaba antes de abrir la primera pata, pese a que el contrato del puerto lo
   exige.
3. El reintento de cierre decidía si había terminado mirando el estado de la última orden, no la posición
   real de la cuenta — un bróker que rechaza órdenes de cantidad cero podía dejarlo sin converger.

## Lo que NO se hizo, dicho explícito (no escondido en ningún sitio)

Ver `RECOMENDACIONES.md` entero, con el estado real de cada punto. El único hueco real que queda: la
recomendación #4 — `da1_diagnostico.ps1` e `IndicadorLaboratorioMercado.cs` siguen sin validar contra NT8
real, porque este entorno no tiene la máquina Windows que hace falta. Todo lo demás que estaba pendiente
en la primera vuelta (cablear `valor_efectivo()`, el contador `muertes_eval`, la persistencia de `k`/`m`,
los dos relojes de cuenta bloqueada, y `09_DESPLIEGUE.md`) está hecho en esta revisión.
