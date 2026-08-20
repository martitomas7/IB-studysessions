# PAQUETE DE INGENIERÍA · circuito cubierto v10
### Todo lo que necesitas para construir el bot. Y las reglas de cómo hacerlo.

---

## LO PRIMERO: cómo se trabaja aquí

Este proyecto ha pasado **seis auditorías adversariales**. Los dos fallos más caros de su
historia costaron el **48 % del titular** y ninguno fue un error de matemática: fueron un
bucle que operaba dos veces y una barra que se miraba antes de tiempo. Los cazó un auditor
externo, no los tests. Por eso este paquete no te da solo una especificación: te da **la
forma de trabajar que impide que vuelva a pasar**.

**Las cinco reglas, y no son negociables:**

1. **La especificación manda sobre el código.** Si un test dorado falla, se arregla el
   código. Jamás el test, jamás la especificación.
2. **Ningún número sale de tu cabeza.** Todos están en `03_CONFIG.yaml` con su fuente y su
   fecha. Un número que no esté ahí **no existe**. Si necesitas uno que no está, **pregunta**;
   no lo inventes ni lo estimes.
3. **Nada se da por hecho sin verlo fallar.** Toda comprobación que escribas debe demostrarse
   rompiéndola a propósito antes de darla por buena. Una aserción que nunca ha disparado no
   es una aserción: es un comentario.
4. **Una sesión de trabajo = un delta.** Nunca "implementa todo". Se pide un delta concreto
   con su sección pegada como contexto (ver `05_ORDEN_DE_CONSTRUCCION.md`).
5. **Las puertas no se saltan.** No se pasa de fase sin que la anterior esté verde al 100 %.
   Ningún criterio a medias.

---

## Qué hay aquí y en qué orden leerlo

| # | fichero | qué es |
|---|---|---|
| **01** | `01_ESPECIFICACION_E2E.md` | **LA NORMA.** Qué hace el sistema, con toda la matemática. Manda sobre todo lo demás |
| **02** | `02_ARQUITECTURA.md` | Cómo se construye: módulos, máquina de estados, `estado.json`, día minuto a minuto |
| **03** | `03_CONFIG.yaml` | **La única fuente de números.** Cada constante con su valor, su fuente y su fecha |
| **04** | `04_GUARDARRAILES_CONSTRUCCION.md` | Las reglas de ingeniería: qué está prohibido, qué hay que demostrar, errores ya cometidos |
| **05** | `05_ORDEN_DE_CONSTRUCCION.md` | Los deltas, en orden, con la puerta de cada uno |
| **06** | `06_PROMPT_DE_ARRANQUE.md` | Qué pegar en la sesión de ingeniería para empezar |
| — | `tests/` | Los artefactos de validación. **Empieza por `tests/LEEME_TESTS.md`** |
| — | `modelo/` | El simulador congelado, sus datos y sus cifras. Para contrastar, **no para tocar** |
| — | `core/` | Un shim de 6 líneas para que `modelo/` funcione fuera del laboratorio original |
| — | `MANIFIESTO.txt` | sha256 de cada fichero. Si uno no cuadra, el paquete llegó alterado |

**Dos avisos que conviene leer antes que nada:**

- **Hay dos números en este proyecto que NADIE ha medido nunca**: la fricción real del hedge
  (`spr_usd`) y el deslizamiento real por muerte (`slip_usd_micro`). La cifra objetivo está
  **condicionada a ellos** y el eje de fricción es el que más riesgo mueve por unidad de
  error: si en vez de 3,00 sale 4,10 —el valor que sugiere la física del mercado— la cifra
  cae un 8,7 % y P(degradar) se triplica. La **Fase 3.1** de `05` existe exactamente para
  medirlos. Ver norma R-9.3 y R-9.4.
- En `03_CONFIG.yaml` los números llevan **cuatro etiquetas**, no tres: `DADO` (impuesto,
  no se discute), **`SUPUESTO`** (adoptado, **no medido**, y con el coste de equivocarse
  citado), `OPTIMIZADO` y `DERIVADO`. La diferencia entre DADO y SUPUESTO es la que te dice
  qué puedes cuestionar.

**Empieza por 04 y 05.** La especificación se lee cuando ya sabes cómo vas a trabajar.

**Comprueba que el paquete llega entero** antes de nada:

```bash
python tests/comprueba_config.py        # -> 03_CONFIG.yaml: OK  + 6 auto-verificaciones
python tests/runner_goldens_v10.py      # -> 14/14 goldens OK
python tests/prueba_goldens_v10.py      # -> PRUEBA DE DISCRIMINACION: OK
python tests/prueba_nucleo_vs_motor.py  # -> EQUIVALENCIA: OK (0 de 60.000 estados)
python tests/runner_replay_v10.py       # -> replay v10: 504 dias · 0 fallos
python tests/prueba_replay_v10.py       # -> tabla de 8 orquestadores rotos (tarda ~10 min)
```

Los seis tienen que salir verdes **antes** de escribir código. Si alguno no, el paquete
llegó roto y no se empieza.

---

## El sistema en cinco líneas

Se compran cuentas de evaluación de una prop firm (capital ficticio) y se opera cada una
con `k` contratos, cubierta por `m` micros MES reales en dirección contraria en otro bróker.
La dirección diaria **se sortea**: no hay predicción. El `sizing` está calculado para que
cuando una cuenta muere, el hedge recupere el coste hundido del linaje más un buffer. El
beneficio sale de dos sitios: ese buffer en cada muerte, y los pagos de la prop firm cuando
una cuenta sobrevive y cobra.

**Cifra objetivo del modelo:** **1.198 $/mes** (sd 3,7 · p5 797 $) con **P(degradar) 1,10 %**
(sd 0,32), escenario cronológico, 8 semillas × 3.000 réplicas. **Tu trabajo NO es mejorarla: es
reproducirla.** Cualquier desviación es un bug hasta que se demuestre lo contrario — y una
desviación **al alza** es igual de sospechosa: los dos bugs históricos inflaban la cifra.

Y una advertencia que conviene tener presente todo el tiempo: el bot real rendirá **por
debajo** del modelo, porque hay pasos manuales que el modelo supone instantáneos (R-4.7) y
una ejecución real que el modelo supone perfecta salvo el deslizamiento.
