# Contrafactual de dirección -- REVISION_REV5.md §4.2

Medición, no una puerta (AUTORIZACION_3_6_CERRADA.md §6: "es medición, no producción").
`504` días del pack (`tests/replay_v10.json`), cada uno resuelto DOS VECES sobre el MISMO
camino crudo real -- reflejado LARGO y reflejado CORTO (`calendario.refleja_camino`, sin
reimplementar) -- con un `plan_resultado` FIJO (cuenta eval recién abierta, día 1) igual en
las dos direcciones, para aislar la dirección como única variable.

## Resultado

| desenlace | largo | corto | discordantes (largo-solo / corto-solo) | McNemar (chi2, corrección continuidad) |
|---|---|---|---|---|
| muere | 0/504 (0.0%) | 0/504 (0.0%) | 0 / 0 | 0.000 |
| objetivo | 110/504 (21.8%) | 126/504 (25.0%) | 110 / 126 | 0.953 |
| pausa | 394/504 (78.2%) | 378/504 (75.0%) | -- | -- |

`dx_puntos` pareado (largo − corto): media = -0.8586, error estándar = 0.8243
(media/SE = -1.04).

**Umbral de referencia (McNemar, 1 grado de libertad, 95%): chi2 = 3.84 -- valor de libro de
texto, no una cifra del proyecto.**

## Lectura

Ninguno de los dos McNemar (muerte, objetivo) cruza el umbral de 3.84, y la diferencia media pareada de dx_puntos es pequeña frente a su propio error estándar -- la moneda 50/50 de R-6.1 se comporta como neutral sobre el camino real de HG22 con esta cuenta de referencia. No hay evidencia, en esta medición, de que la dirección por sí sola sesgue el desenlace.

**Limitación reconocida:** se usó un `plan_resultado` FIJO (cuenta día 1) igual en las dos
direcciones, en vez del `plan` real que cada cuenta tuvo cada día del replay -- deliberado,
para aislar la dirección del efecto acumulado del estado de cuenta (que a su vez depende de
qué dirección salió en días anteriores). Esto mide "¿la dirección importa, dado un punto de
partida idéntico?", no "¿el histórico real de 504 días habría sido distinto con la moneda al
revés?" -- son preguntas relacionadas pero no idénticas.
