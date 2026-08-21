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

Lo que hoy NO está modelado en `bot/` -- sin banda verde/ámbar/rojo hasta que F3.1 dé el primer dato real (`05_ORDEN_DE_CONSTRUCCION.md`); se reporta la curva, registrada en `03_CONFIG.yaml → hedge_broker.desviacion_fill_normal_usd_tick` como eje de barrido, no como valor de operación.

| ticks | caja final |
|---|---|
| 0.0 | 152.859371 |
| 0.25 | 116.609371 |
| 0.5 | 80.359371 |
| 1.0 | 7.859371 |

Pendiente medida: **-145.0000 $/tick**.

## Coste por tick -- los dos ejes lado a lado

| eje | $/tick | sobre cuántas unidades |
|---|---|---|
| Salida por muerte | -57.50 | 46 micro-muertes |
| Fills normales | -145.00 | micro-días sin muerte |

El deslizamiento rutinario cuesta **2.52×** más por tick que el de muerte -- pasa todos los días, la muerte no. El gate F3.1 mide hoy solo el eje de muerte (`slip_usd_micro`); el eje rutinario no tiene banda todavía.

## Falsación de aditividad (ORDEN_PASADA2_CIERRE.md §3.1)

Los dos ejes actúan sobre días disjuntos (con muerte / sin muerte) y ninguno toca `eval.bal`/`funded.bal` -- deben ser exactamente aditivos:

`caja(n, d) = caja(0, ancla) + coste_muerte_tick·(d-ancla) + coste_normal_tick·n`

| escenario | n (ticks normal) | d (ticks muerte) | caja predicha (fórmula) | caja medida | diferencia |
|---|---|---|---|---|---|
| pesimista realista (ámbar) | 0.5 | 5.0 | -92.140629 | ver corrida | -- |
| rojo | 1.0 | 10.0 | -452.140629 | ver corrida | -- |

(la tabla anterior recalcula la fórmula al escribir el informe; los valores medidos exactos y las diferencias quedan en la salida de la corrida -- ambos escenarios coincidieron al céntimo con la predicción pre-registrada del operador el 21-08-2026.)
