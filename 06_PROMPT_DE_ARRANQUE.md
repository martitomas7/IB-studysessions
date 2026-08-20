# 06 · PROMPT DE ARRANQUE
### Qué pegar en la sesión de ingeniería. Literal.

---

## Paso 1 · El mensaje de apertura (pégalo tal cual, con el zip adjunto)

> Vas a construir un bot de trading automatizado. **No vas a diseñarlo: ya está
> especificado.** Te adjunto el paquete de ingeniería completo.
>
> **Antes de escribir una sola línea de código, lee en este orden:**
> 1. `00_LEEME_PRIMERO.md`
> 2. `04_GUARDARRAILES_CONSTRUCCION.md` — las reglas de cómo se trabaja aquí
> 3. `05_ORDEN_DE_CONSTRUCCION.md` — los deltas y sus puertas
> 4. `01_ESPECIFICACION_E2E.md` — la norma
> 5. `02_ARQUITECTURA.md` — los módulos y el `estado.json`
> 6. `03_CONFIG.yaml` — **la única fuente de números**
>
> **Después de leerlos, y antes de implementar nada, respóndeme con:**
> - un resumen en 10 líneas de qué hace el sistema, con tus palabras;
> - la lista de **cosas que la especificación NO decide** y que tú necesitarías decidir;
> - **tres preguntas** sobre lo que te haya quedado ambiguo.
>
> **No implementes nada en este primer mensaje.** Cuando responda a tus preguntas,
> empezamos por el delta **D0**.
>
> **Dos cosas que tienes que saber antes de leer nada:**
> - En `03_CONFIG.yaml` hay entradas marcadas **`SUPUESTO`**: son números **adoptados, no
>   medidos**. Cada una lleva el coste de que esté mal. No los trates como datos.
> - Los dos más importantes (`spr_usd` y `slip_usd_micro`) **nadie los ha medido nunca**, y
>   la cifra objetivo está condicionada a ellos.
>
> Reglas que no son negociables en toda esta sesión:
> - Si un test dorado falla, **se arregla el código**. Jamás el test, jamás la norma.
> - **Ningún número sale de tu cabeza.** Si necesitas uno que no está en `03_CONFIG.yaml`,
>   **pregunta**. No lo estimes ni lo inventes.
> - **Nada se da por bueno sin verlo fallar.** Toda comprobación que escribas la rompes a
>   propósito y me pegas la salida de la rotura.
> - **Un mensaje = un delta.** No implementes dos a la vez ni te adelantes.
> - **No modifiques nada de `tests/` ni de `modelo/`.**

---

## Paso 2 · El mensaje de cada delta (plantilla)

> Implementa el **delta D{n}: {título}**.
>
> **Norma aplicable** (pegada entera, no resumida):
> ```
> [pegar aquí las reglas R-x.y que indica 05_ORDEN_DE_CONSTRUCCION.md para este delta]
> ```
>
> **Números:** los que estén en `03_CONFIG.yaml`. Si falta alguno, para y pregúntame.
>
> **Puerta:** `{el comando exacto que dice 05}`.
> No des el delta por terminado sin ejecutarla y **pegarme su salida**.
>
> **Y por la regla R3:** rompe tu propia implementación a propósito de la forma que
> describe el delta, ejecuta la puerta otra vez, y pégame también esa salida.
>
> Cuando termines, dime en dos líneas qué has dejado sin hacer.

---

## Paso 3 · Qué NO decir nunca en esa sesión

| no digas | por qué |
|---|---|
| «optimiza esto» / «mejora la cifra» | la cifra está cerrada. Mejorarla es re-optimizar, y eso se hace **aquí**, no en ingeniería |
| «haz lo que veas mejor» | invita a inventar. Cada decisión abierta está listada en la norma §8 |
| «implementa todo el bot» | se pierde el control de las puertas. Un delta por vez |
| «los tests son muy estrictos» | son la única red que hay. Los dos bugs caros los encontró un auditor, no los tests |
| «asume un valor razonable para X» | R2. Si falta un número, es una pregunta para el operador |
| «la fricción/el deslizamiento son los que dice la config» | son **SUPUESTOS**, no datos. Si el ingeniero los da por ciertos, corrígelo |

---

## Paso 4 · Cómo saber si la sesión de ingeniería va bien

**Buenas señales:**
- Te hace preguntas concretas sobre números que no encuentra.
- Pega salidas de comandos, no descripciones de salidas.
- Se niega a seguir cuando una puerta no está verde.
- Dice explícitamente qué ha dejado sin hacer.

**Malas señales — para y corrige:**
- Aparece un número en el código que no está en `03_CONFIG.yaml`.
- Aparece cualquier lógica que decide **cuándo** entrar mirando el **precio** (R-1.4).
- "He ajustado el test para que pase."
- Implementa dos deltas en un mensaje.
- Dice "debería funcionar" sin haber ejecutado la puerta.
- Toca `tests/`, `modelo/` o `03_CONFIG.yaml`.

---

## Paso 5 · Lo que el operador (tú) tiene que decidir, tarde o temprano

Esto **no** lo decide la sesión de ingeniería. Está listado también en la norma §8 y en la
sección `pendientes` de `03_CONFIG.yaml`.

1. **Timeout de confirmación de la primera pata** (Arquitectura §7.1). Si la pata de la prop
   no confirma en N segundos, se cierra el hedge y no se opera. `N` no está medido.
2. **Qué hacer si el bróker rechaza la orden del hedge.** Sin especificar.
3. **Qué hacer si la prop y el bróker discrepan en el precio de referencia.** Sin especificar.
4. **Política de orden de activación de dormidas** (R-7.4). Hasta que se mida, FIFO.
5. **Retardo de entrada el día 1 de una fondeada nueva** (`b0_nuevo`). NO MEDIDO — la
   conclusión anterior fue retractada.
6. **Qué hacer con una cuenta bloqueada** (R-2.4). El bloqueo es **absorbente**: si nadie
   hace nada, a los ~7 días el proveedor la mata por inactividad **sin hedge abierto** y se
   pierde el carry entero del linaje. Los tres rescates automáticos están medidos y
   **rechazados**. Falta decidir la disposición deliberada. Ocurre en ~0,5 % de los linajes.

Las seis pueden esperar hasta la Fase 2 — **salvo la 6**, que hay que decidir antes de que
una cuenta llegue a bloquearse en real. Ninguna puede resolverse inventando un número.
