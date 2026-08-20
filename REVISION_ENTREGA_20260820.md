# Revisión de la entrega del 20-08 · veredicto

**Reproduje todas las puertas por mi cuenta, desde el zip, sin fiarme del informe.** Todas
salen verdes, incluida la que importa: tu orquestador contra el pack.

```
PYTHONPATH=. python3 bot/orquestador.py tests/replay_v10.json /tmp/estados.json
  -> 504 dias · caja final 29.134,87 $   (= resultado_global.caja_final del pack, exacto)
python3 tests/runner_replay_v10.py /tmp/estados.json
  -> replay v10: 504 dias · 0 fallos
```

Y las de discriminación también, que es lo que de verdad las hace valer: `romper_mi_orquestador`
5/5 (el bloqueo del día 210 da 296 divergencias, idéntico a mi referencia independiente),
`prueba_protocolo_dos_patas` 25/25 con el botón de pánico ingenuo produciendo la pata sola,
`prueba_comandos` 15/15, `prueba_dashboard` 14/14, `d2_mata_el_proceso` 10/10 con `kill -9`
real, y la paleta pasando el validador.

**Muy buen trabajo.** Los dos bugs que cazaste tú solo —el `aplanar()` sin confirmar y la
frescura calculada pero no pintada— son exactamente el tipo de cosa que R3 existe para
encontrar, y encontrarlos tú antes de entregar es la señal de que el método funciona.

**Dicho eso: he encontrado dos defectos que las pruebas no cubren, los dos en el camino
crítico.** Ninguno es culpa de una prueba mal hecha — son huecos de la propia norma que yo
escribí, así que hay que arreglar el documento además del código.

---

## DEFECTO 1 · Una orden RECHAZADA no se trata como terminal — se consume el timeout entero

**Prueba, ejecutada contra tu propio adaptador falso con reloj virtual:**

```
--- hedge RECHAZADO de inmediato ---
  abierto: False | motivo: hedge_ambiguo_tras_cancelar_aplanado
  TIEMPO LÓGICO consumido: 30,00 s          <- N_hedge entero
  eventos: [('timeout_hedge', alerta='MAXIMA')]

--- prop RECHAZADA de inmediato ---
  abierto: False | motivo: prop_ambiguo_tras_cancelar_aplanadas_las_dos
  TIEMPO LÓGICO consumido: 5,01 s           <- N entero, CON EL HEDGE ABIERTO Y DESNUDO
  eventos: [('timeout_prop', alerta='MAXIMA')]
```

**Causa raíz:** `_poll_hasta(..., {'LLENA'}, N, ...)` espera **solo** `LLENA`. `RECHAZADA` no
está en el conjunto, así que el bucle gira hasta agotar el timeout y cae por la rama de
"agotó" → cancela una orden ya rechazada → estado final `RECHAZADA` → rama `else` (ambiguo).

**Por qué importa, y no es cosmético:**

1. **El caso de la prop es el grave.** Un rechazo es información **instantánea y cierta**: no
   se abrió nada. Pero el código se queda **5 segundos con el hedge abierto sin cubrir** —
   justo la exposición que `N` existe para acotar. El razonamiento entero de §5.2 ("errar por
   corto es barato, errar por largo es exposición real sin techo") queda anulado por un rechazo.
2. **Se etiqueta como ambiguo algo que es limpio.** `RECHAZADA` significa "no se abrió, con
   certeza" — el desenlace más claro que existe. Emitir `ALERTA_MAXIMA` por eso es la forma más
   rápida de que las alertas máximas dejen de mirarse.
3. En el hedge, 30 s tirados y una alerta máxima por lo mismo.

**Arreglo (pequeño y quirúrgico):** sondear contra `ESTADOS_TERMINALES` y ramificar según qué
estado terminal llegó. `LLENA` → seguir. `RECHAZADA`/`CANCELADA` **antes** del timeout → salida
limpia inmediata: en el hedge, no operar hoy sin alerta máxima; en la prop, aplanar el hedge ya
—confirmado— y no operar hoy, evento normal de laboratorio, **sin** ambigüedad. `PARCIAL` o
timeout agotado → las ramas que ya tienes, que están bien.

**Y arregla también la norma:** `07_ADAPTADOR_NT8.md` §5.3 no contempla "la orden se rechaza
antes de que expire el timeout" en ninguna de sus dos fases. El diagrama solo tiene *confirma* o
*expira*. Añade la tercera salida en las dos fases, y una comprobación R3 por cada una.

---

## DEFECTO 2 · `hay_conexion()` no se llama nunca

**Prueba:**
```
'hay_conexion' aparece en protocolo_dos_patas.py: False
con la cuenta PROP DESCONECTADA -> abierto: True
  posiciones: {('HEDGE','MES'): -4, ('PROP','MESprop'): 15}
```

El puerto de `07_ADAPTADOR_NT8.md` §1 dice, literal, sobre `hay_conexion`: **«se comprueba
antes de cada operación; nunca se asume»**. Y §7 dice que con la conexión caída **no se abre
ninguna pata nueva**. El protocolo abre las dos alegremente contra una cuenta desconectada.

Con el falso no pasa nada porque es un simulador complaciente. Contra NT8 real, lo que ocurre es
que abres el hedge, descubres que la prop no responde, y te comes `N` entero con la pata
desnuda — o el adaptador lanza excepción a media secuencia y **el hedge se queda abierto sin que
nadie lo gestione**, que es el fallo más caro del sistema.

**Arreglo:** comprobar `hay_conexion` de **las dos** cuentas **antes** de mandar la primera
orden, y abortar sin abrir nada si alguna falla. Y una comprobación R3: con una cuenta
desconectada, el protocolo no debe abrir ni una pata.

---

## DEFECTO 3 (menor, de fidelidad del falso) · aplanar sobre una cuenta ya plana

En tu falso, `aplanar()` sobre posición cero devuelve `LLENA` y `_aplana_hasta_confirmar()`
termina en un intento. **Un bróker real es probable que rechace una orden de cantidad cero.** Si
lo hace, ese bucle gira hasta `max_reintentos` = 10.000 con alerta máxima en cada vuelta.

**Arreglo:** que la condición de salida sea **la posición, no el estado de la orden**: se
comprueba `leer_posicion()`; si ya es cero, está hecho, sin mandar nada. Y añade al falso el
modo "rechaza el aplanar de cantidad cero" para poder probarlo. Un simulador que solo simula el
caso amable no sirve de red.

---

## Tus siete recomendaciones

| # | veredicto |
|---|---|
| **1 · cablear `valor_efectivo()`** | **Hazlo ya**, no lo dejes. Tu prudencia es correcta, pero la red existe: con `desviaciones_activas=[]` el replay tiene que salir **bit-idéntico**. Si sale, el cableado es seguro; si no, el cableado está mal — y eso es exactamente lo que quieres saber. Tu paso 3 es el procedimiento correcto |
| **2 · contador `muertes_eval`** | **Sí**, en la misma pasada |
| **3 · "5 días" vs "~7 días"** | **Te equivocas: no es una discrepancia, son dos relojes distintos.** 5 días = cuándo el bot **escala la alerta**. ~7 días = cuándo **el proveedor mata la cuenta** por inactividad. Son cosas diferentes y las dos son correctas. El dashboard debe mostrar **las dos**: días bloqueada, y días que quedan hasta que el proveedor la mate. Eso es más útil que cualquiera de las dos sola |
| **4 · NT8 sin validar** | **Correcto, no hay nada que hacer.** Bloqueado hasta que haya máquina |
| **5 · `k`/`m` en el bloque 1** | Opción **(a): persistir `k`/`m` del día en `estado.json`**. La (b) está mal: recalcular daría un número que **no es el que se usó**, y un dashboard que enseña un número plausible pero falso es peor que uno que enseña un guion |
| **6 · `09_DESPLIEGUE.md`** | Sí, pero **después** de la pasada de arriba |
| **7 · bucle de comandos** | **Correcto**, es D8 |

---

## Qué hacer ahora, en una sola pasada

1. **Defecto 1** — estados terminales en las dos fases, y actualizar `07_ADAPTADOR_NT8.md` §5.3.
2. **Defecto 2** — `hay_conexion` antes de abrir nada.
3. **Defecto 3** — salir por posición, no por estado de orden; y el falso, menos complaciente.
4. **Recomendaciones 1, 2 y 5** — `valor_efectivo()` cableado, contador `muertes_eval`, y
   `k`/`m` persistidos. Las tres tocan `ciclo_vida.py`, así que van juntas.
5. **Recomendación 3** — dos relojes, no uno.
6. **Re-verifica todo.** El replay con `desviaciones_activas=[]` tiene que seguir dando
   **504 días · 0 fallos y caja final 29.134,87 $**. Cualquier otra cosa es un bug del cableado.
7. **R3 por cada defecto:** rechazo antes del timeout (hedge y prop), cuenta desconectada, y
   aplanar sobre cuenta plana con el falso rechazando. Las tres roturas, con sus salidas.

Cuando esté, **sigue con `09_DESPLIEGUE.md`** y luego para. Nada de esto necesita NT8.

**Luz verde a todo lo demás.** D2–D7 y D-C están bien hechos y lo he comprobado yo.
