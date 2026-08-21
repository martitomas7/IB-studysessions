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
| Bloqueo de eval | 0 | NUNCA -- cobertura 0, objeto de D8 §5 |
| Pool agotado sin sub disponible | 0 | NUNCA -- cobertura 0, objeto de D8 §5 |
| Degradación (degradado/dia_degradacion) | 0 | NUNCA -- cobertura 0, objeto de D8 §5 |
| Sorteo 50/50 + veto CONTRA decidiendo dirección | 0 | NUNCA, estructuralmente -- en replay la dirección la fuerza el pack (orquestador.py: "candidata" es relleno sin efecto). Objeto de D8 §5. |
