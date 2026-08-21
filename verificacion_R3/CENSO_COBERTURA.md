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
| Degradación (degradado/dia_degradacion) | 0 | 0 en el pack -- existe pero el pack no lo toca; cubierto aparte en verificacion_R3/prueba_degradacion.py (§5.4, 10/10) |
| Sorteo 50/50 + veto CONTRA decidiendo dirección | 0 | 0 en el pack, ESTRUCTURALMENTE -- en replay la dirección la fuerza el pack (orquestador.py: "candidata" es relleno sin efecto) -- pero existe y funciona: cubierto aparte en verificacion_R3/prueba_sorteo_direccion_contra.py (§5.1, 9/9) |
| Escalada N0-N4 / aviso humano por bloqueo sostenido de funded | 0 | 0 (MECANISMO INEXISTENTE, no "el pack no lo toca" -- distinción del operador, RESPUESTA_D8_ITEM2_BLOQUEO.md §3): ausencia CONFIRMADA y certificada en verificacion_R3/prueba_ausencia_escalada_bloqueo.py (§5.2, 10/10) -- ningún camino de bot/ escribe pendientes_humano[].dias_esperando ni conecta alertas.bloqueada_escalada_dias/proveedor_mata_cuenta_dias a la escalera N0-N4. Confirmado por el operador: conocido, aceptado, NO se cablea ahora. |
