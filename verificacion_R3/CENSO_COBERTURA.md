# Censo de cobertura -- 504 días de tests/replay_v10.json

Regenerado por `verificacion_R3/prueba_censo_cobertura.py` -- instrumentación directa
sobre `bot/ciclo_vida.py`/`bot/calendario.py`, nunca reconstrucción a mano (R2/R3).
Ver `ANALISIS_PUERTA_GRANDE.md` §3 para el porqué de esta tabla: "un gate en verde
sobre un camino con cobertura 0 no es información".

| Camino | Veces en el pack | Estado |
|---|---|---|
| Sesión base | 504 | machacado |
| Empalme (R-4.3) | 150 | machacado |
| Muertes de eval | 150 | machacado |
| Muertes de funded | 94 | machacado |
| Activaciones de funded (relevo R-5.1) | 96 | machacado |
| Aprobaciones | 98 | machacado |
| Recompras | 98 | machacado |
| Compras de emergencia (pool sin frescas) | 138 | machacado |
| CONTRA armada al cierre | 192 | contador sí, efecto no (dirección forzada por el pack en replay) |
| Bloqueo de funded (R-2.4) | 1 | tocado |
| Levantamiento del tope por tesorería | 1 | tocado |
| Bloqueo de eval | 0 | 0 en el pack -- existe pero el pack no lo toca; §5 aún sin cubrir aparte |
| Pool agotado sin sub disponible | 0 | 0 en el pack -- existe pero el pack no lo toca; cubierto aparte en verificacion_R3/prueba_pool_agotado.py (§5.3, 38/38) |
| Degradación (degradado/dia_degradacion) | 0 | 0 en el pack -- existe pero el pack no lo toca; cubierto aparte en verificacion_R3/prueba_degradacion.py (§5.4, 28/28) -- desde DECISION_DEGRADACION_N3.md, degradado=True escala a N3 (KILL) de verdad, cableado en bot/bucle_del_dia.py |
| Sorteo 50/50 + veto CONTRA decidiendo dirección | 0 | 0 en el pack, ESTRUCTURALMENTE -- en replay la dirección la fuerza el pack (orquestador.py: "candidata" es relleno sin efecto) -- pero existe y funciona: cubierto aparte en verificacion_R3/prueba_sorteo_direccion_contra.py (§5.1, 9/9) |
| Escalada N0-N4 / aviso humano por bloqueo sostenido de funded | 0 | 0 (MECANISMO INEXISTENTE, no "el pack no lo toca" -- distinción del operador, RESPUESTA_D8_ITEM2_BLOQUEO.md §3): ausencia CONFIRMADA y certificada en verificacion_R3/prueba_ausencia_escalada_bloqueo.py (§5.2, 10/10) -- ningún camino de bot/ escribe pendientes_humano[].dias_esperando ni conecta alertas.bloqueada_escalada_dias/proveedor_mata_cuenta_dias a la escalera N0-N4. Confirmado por el operador: conocido, aceptado, NO se cablea ahora. |

**Nota D-5** (`ORDEN_DE_TRABAJO_D9.md` §1.2): las 150 muertes de eval de esta tabla vienen del oráculo offline (`orquestador.corre_replay()`, qok del CONTRATO). La Pasada 2 de LA PUERTA GRANDE (`verificacion_R3/PASADA_2_RUIDO.md`) corre por el bucle en vivo con qok CAUSAL -- "Pasada B" en términos de la Puerta Grande -- y mide 149 muertes de eval, no 150 (94 de funded coincide en los dos caminos). La diferencia de 1 es exactamente el defecto D-5 ya documentado (`modelo/DEFECTOS_CONOCIDOS.md`, día 269: el `qok` causal diverge del `qok` del contrato justo ahí, y esa bifurcación se hereda en todo día posterior) -- no una segunda medición contradictoria de lo mismo, sino la misma tabla vista por dos caminos distintos, cada uno correcto para su propio contrato.

## Censo de "la documentación promete código que no existe todavía"

Pasada rápida (22-08-2026, `DECISION_CREDENCIALES_Y_FASE.md` punto 5: "si han
aparecido tres casos... probablemente haya un cuarto") sobre `*.md` en busca
del mismo patrón que motivó ese punto: un documento describiendo, en
presente, un comportamiento que el código todavía no tiene. **Solo se anota
-- no se corrige aquí ninguno de los dos.** (Esta sección vive en el generador,
`prueba_censo_cobertura.py`, no solo en el .md -- de lo contrario cada
regeneración de la tabla de arriba la borraría.)

| Documento | Qué promete | Qué hay de verdad hoy | Estado |
|---|---|---|---|
| `07_ADAPTADOR_NT8.md:92` (antes de esta pasada) | "el agregador del residuo... **ya** se niega a calcular `spr_usd` con registros `NO_VALIDA`" | No existe ningún agregador que rechace por `NO_VALIDA`; `papel_feed_retrasado` y el marcado `NO_VALIDA` por registro no existen en `bot/` (D9 §3.3, aún sin construir) | **Corregido en esta misma sesión** -- ver el bloque "PENDIENTE" añadido justo debajo de esa línea |
| `02_ARQUITECTURA.md` §9 (tabla de banderas) | Presenta `--modo simulado/papel/real`, `--replay <fichero>`, `--dry-run`, `--parar` como banderas de línea de comandos reales, con columna "qué hace" en presente | No existe ningún `main.py`/`cli.py`/`__main__.py` ni `argparse.ArgumentParser` en todo `bot/` (confirmado por grep exhaustivo) -- `bucle_del_dia()`/`corre_replay()` solo se invocan hoy directamente desde Python (scripts de `verificacion_R3/`, no desde una CLI). Coincide exactamente con D9 §5.4 ("--config/--estado/--fase obligatorios"), que sigue **pendiente** en el orden de trabajo -- la tabla describe la interfaz que §5.4 debe construir, no una que ya exista | **Anotado, sin tocar** -- corregirlo (marcarlo "pendiente" igual que el caso de arriba) le corresponde a quien construya D9 §5.4, no a esta pasada de censo |

No ha aparecido un tercer caso en esta pasada (se revisaron `09_DESPLIEGUE.md`, `11_MANUAL_OPERADOR.md`, `05_ORDEN_DE_CONSTRUCCION.md` y grep de `checksum_fijado`/`panel`/`formulario`/`probar_conexion` sobre todo el árbol de `*.md`, sin más coincidencias sospechosas). Si aparece un tercero más adelante, añadir una fila aquí, no una nueva sección.
