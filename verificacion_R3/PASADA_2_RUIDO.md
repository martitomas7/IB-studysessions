# Pasada 2 de LA PUERTA GRANDE -- ruido de ejecución (30 días)

Ancla: `slip_usd_micro`=2.5 $/micro ÷ `tick_usd`=1.25 $/tick = **2.0 ticks**. Censo de esta corrida: 11 muertes eval (m=2) + 6 muertes funded (m=4) = 46 micro-muertes.

## Barrido de sensibilidad de la salida por muerte (ruido_normal=0)

| ticks | $/micro | caja final | banda |
|---|---|---|---|
| 1.0 | 1.25 | 210.359371 |  |
| 2.0 | 2.5 | 152.859371 | verde |
| 5.0 | 6.25 | -19.640629 | ámbar |
| 10.0 | 12.5 | -307.140629 | rojo |

Pendiente medida: **-46.000000 $** por cada 1 $/micro de deslizamiento extra (predicha: -46).

## Barrido de fills normales -- entrada/objetivo/campana (muerte fija en el ancla)

Lo que hoy NO está modelado en `bot/` -- sin predicción pre-registrada (no hay dato análogo en `03_CONFIG.yaml` que anclarlo); se reporta la curva, no un gate numérico.

| ticks | caja final |
|---|---|
| 0.0 | 152.859371 |
| 0.25 | 116.609371 |
| 0.5 | 80.359371 |
| 1.0 | 7.859371 |
