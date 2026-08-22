# GUARDARRAÍLES DE CONSTRUCCIÓN
### Las reglas de cómo se escribe este bot. Léelas antes que la especificación.

---

## 1 · Por qué existe este documento

Este proyecto tuvo dos bugs que **inflaron la cifra publicada un 48 %** durante semanas
(1.910 $/mes anunciados frente a 959 reales), y ninguno era un error de matemática:

- **Un bucle que operaba dos veces.** El slot de evaluación corría una segunda sesión el
  mismo día, sobre el mismo camino de precios y desde la misma barra.
- **Una barra mirada antes de tiempo.** Se entraba al cierre de la barra `b0` y luego se
  comprobaba si el máximo y el mínimo *de esa misma barra* habían tocado los niveles.

**El reparto histórico entre los dos (−32,5 % y −13,6 %) se midió sobre la configuración de
v8 y NO es reproducible con este paquete.** Re-medido sobre la config v10
(`modelo/cifras_citadas.py`, 8 semillas, crono, R=3000):

| motor | EV $/mes | Δ vs correcto | P(degradar) |
|---|---|---|---|
| correcto | 1.198,5 | — | 1,10 % |
| con doble sesión | 1.403,0 | **+17,0 %** | 0,65 % |
| con look-ahead | 1.191,3 | −0,6 % | 0,90 % |
| con los dos | 1.358,1 | +13,3 % | 0,52 % |

Dos lecturas, y la segunda es la importante:
1. **La doble sesión sigue inflando**, ahora un 17 %. Es el bug caro.
2. **El look-ahead ya casi no mueve el titular bajo v10** (−0,6 %, del orden del ruido).
   **Eso no lo convierte en aceptable**: sigue siendo una implementación que mira una barra
   que aún no ha ocurrido, los goldens lo cazan en 3 casos, y su impacto depende de la
   configuración — mañana vuelve a costar el 13 %. *Un bug que hoy no se nota es un bug.*

Los dos pasaron doce tests dorados, un pack de repetición, un Excel con once cuadres y tres
revisiones. **Los cazó un auditor externo.** La razón es una sola y hay que interiorizarla:

> **Todo el aparato de validación estaba aguas abajo del fallo.** Los tests, la traza y las
> cifras salían del mismo bucle defectuoso, así que ninguno podía verlo.

Las reglas de abajo existen para que eso no vuelva a pasar. No son estilo: son la diferencia
entre un número que vale y uno que no.

---

## 2 · Las siete reglas

### R1 · La especificación manda. El código se somete.
Si un test dorado falla, **se arregla el código**. Jamás el test, jamás la especificación.
Si crees que la especificación está mal, **para y pregunta**. No la "interpretes".

### R2 · Ningún número sale de tu cabeza
Todos están en `03_CONFIG.yaml`, cada uno con su fuente y su fecha. **Un número que no esté
ahí no existe.** Prohibido:
- literales numéricos de negocio en el código (hay un test estático que lo comprueba),
- "estimar" una constante que falte,
- reutilizar un número de otra versión del proyecto.

Si necesitas un valor que no está: **pregunta**. Es la regla que más veces se ha roto en la
historia de este proyecto y la que más caro ha salido (una comisión de 1,04 $ cuando el
proveedor cobra 1,90 $ estuvo dentro del modelo cinco versiones).

### R3 · Nada se da por bueno sin verlo fallar
**Toda comprobación que escribas debe demostrarse rompiéndola a propósito antes de darla por
buena.** Una aserción que nunca ha disparado no es una aserción: es un comentario.

Esto no es teoría. En este proyecto:
- los goldens de la versión anterior **detectaban cero** de los tres bugs conocidos;
- una fila de estrés se publicó durante dos versiones siendo **un no-op** (el parámetro no
  existía y la fila era bit-idéntica a la base);
- una comprobación del margen del bróker se escribió con una fórmula que **se cancelaba sola**.

Las tres se descubrieron construyendo el fallo a propósito. Procedimiento obligatorio:
escribes la comprobación → **escribes una implementación rota que debería violarla** →
compruebas que salta → solo entonces la das por buena.

### R4 · Una sesión = un delta
Nunca "implementa el bot". Se pide **un delta concreto** de la lista de
`05_ORDEN_DE_CONSTRUCCION.md`, con su sección de la especificación pegada como contexto.
Cada delta termina con su puerta verde o no termina.

### R5 · Las puertas no se saltan
No se pasa de fase sin que la anterior esté al **100 %**. Ningún criterio a medias, ningún
"casi", ningún "lo arreglo después". Si una puerta no pasa, el trabajo de esa fase no ha
terminado.

### R6 · El núcleo de sesión es intocable
La aritmética de una sesión (**R-2 y R-3** de la norma) se implementa **una vez**, pasa los
14 goldens, y **ningún delta posterior la toca**. Si un delta necesita cambiarla, es que el
delta está mal planteado: para y pregunta.

### R7 · Las aserciones fatales son fatales
Cuando una aserción de runtime falla: **aplanar todo, parar, alertar**. Nunca "seguir con la
mejor estimación", nunca "reintentar y ver". Un sistema parado no pierde dinero; un sistema
que sigue con el estado corrupto, sí.

---

## 3 · Prohibiciones explícitas (errores ya cometidos en este proyecto)

| prohibido | qué pasó | barrera |
|---|---|---|
| Literales numéricos de negocio en el código | comisión 1,04 $ cuando el proveedor cobra 1,90 $, durante 5 versiones | todo en `03_CONFIG.yaml`; test estático de literales |
| Mezclar divisas sin tipo | euros y dólares sumados | toda cantidad lleva divisa explícita; el FX es una función única y viva |
| Clavar el tipo de cambio | `FX = 1,08` hardcodeado | grep pre-commit contra literales de FX |
| Usar API de NinjaTrader 7 dentro de NT8 | secciones enteras que no compilaban | toda llamada se valida contra la doc de NT8; **el juez final es el compilador** |
| Código de opciones | un "put fantasma" en el denominador de un sizing | no existe ninguna opción en este sistema |
| `kcap` equivocado por producto | tope de contratos de otra cuenta | config por cuenta + aserción pre-orden |
| Operar sin cobertura | — | R-1.1 de la norma: la cobertura es la condición de existencia. Arquitectura §7: **las dos patas o ninguna** |
| Suponer que un test pasa | doce goldens que detectaban cero bugs | R3 |
| Una comprobación que no discrimina | fila de estrés no-op durante dos versiones | R3 + aserción anti-no-op |

---

## 4 · Cómo se demuestra que una comprobación vale

Plantilla obligatoria para cualquier test, aserción o invariante nuevo:

```
1. Qué comprueba, en una frase.
2. Qué implementación ROTA debería hacerlo saltar.
3. La ejecución de esa implementación rota, con el fallo saliendo por pantalla.
4. La ejecución del código correcto, pasando.
```

Sin el punto 3 la comprobación **no está terminada**. Ejemplos ya hechos en este proyecto,
que puedes usar de modelo:

- `tests/prueba_goldens_v10.py`: tres núcleos rotos a propósito. Salida real, ejecutada:

  | rotura | goldens que caen |
  |---|---|
  | look-ahead en la barra de entrada | **3** — los tres `LOOKAHEAD_*` |
  | sin la cuña de comisión (una sola pasada de `k`) | **6** |
  | operar con `k < 1` (viola R-2.4) | **1** — `bloqueo_k_menor_1` |

  Y el núcleo intacto pasa los 14. Si alguna rotura dejara de romper, los goldens se habrían
  degradado y no se sigue adelante.
- `tests/prueba_replay_v10.py`: ocho orquestadores. El que hace operar dos veces a la eval
  superviviente rompe el invariante **275 veces, la primera el día 2**; el que opera la
  cuenta bloqueada lo rompe el día 210.

---

## 5 · Qué hacer cuando algo no cuadra

**Para. No improvises.** El orden es siempre:

1. ¿El número que uso está en `03_CONFIG.yaml`? Si no → **pregunta**.
2. ¿La especificación dice algo distinto de lo que hace mi código? → **el código está mal**.
3. ¿La especificación no dice nada de este caso? → **pregunta**. No hay casos "obvios": los
   dos bugs de v8 vivían justo en casos que parecían obvios.
4. ¿Un test falla y creo que el test está mal? → **casi nunca lo está**. Demuestra que lo
   está construyendo el contraejemplo antes de tocarlo.
5. **¿Una cifra citada por el operador y una cifra instrumentada por la sesión de
   ingeniería discrepan?** → **gana la instrumentada**, y la discrepancia se anota, nunca se
   silencia. **Esto aplica también contra el operador** -- no es cortesía, es la misma R2 y
   R3 ya escritas arriba: un número que no se ha visto salir de una medición real no vale
   más por venir de quien manda (`ORDEN_DE_TRABAJO_D9.md` §1.3, sobre el censo de
   micro-sesiones de la Pasada 2: 2.742 instrumentado directamente del pack contra 2.746
   citado de memoria -- la diferencia se anotó, y se usó la cifra medida).

---

## 6 · Lo que NO es tu trabajo

- **No optimices.** La configuración está congelada tras 152 configuraciones evaluadas con
  un protocolo pre-registrado, validación cruzada por mitades del histórico y corrección por
  comparaciones múltiples. Si ves algo que "se podría mejorar", anótalo y **no lo cambies**.
- **No mejores la cifra.** Tu trabajo es **reproducir** 1.198 $/mes, no superarla. Una
  desviación al alza es tan sospechosa como una a la baja: los dos bugs de v8 inflaban.
- **No decidas reglas de negocio.** Compras de suscripciones, activaciones de cuentas
  dormidas y retiros son **manuales**. El bot alerta y espera. Nunca compra, nunca activa,
  nunca mueve dinero.
