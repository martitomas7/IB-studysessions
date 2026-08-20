# modelo/ · DEFECTOS CONOCIDOS DEL MOTOR CONGELADO
**Ninguno está corregido, y es deliberado.** La regla R6 congela `modelo/`: tocarlo
invalidaría la trazabilidad de la cifra y de los 504 días del replay. Se documentan aquí
para que nadie los descubra creyendo que ha encontrado algo nuevo, y para que nadie los
active por accidente.

Los cinco están **fuera de la ruta de la configuración v10**: ninguno afecta a ninguna cifra
publicada. Verificado el 19-08-2026.

---

## D-1 · `CMS = 1.04` sigue siendo el valor por defecto del módulo
`pipeline3.py:35`. Es la comisión **retirada** (la real del proveedor es 1,90; ver
`03_CONFIG.yaml` §retirados).

**Por qué no muerde:** la config V10 pasa `cms=1.90` explícitamente, y
`tests/comprueba_config.py` lo asevera contra la config congelada.

**Cómo muerde si te descuidas:** cualquier llamada a `corre()` **sin** `cms=` usa 1,04 en
silencio y te da una cifra ~53 $/mes más alta. Si contrastas contra el motor —cosa que
`LEEME_TESTS.md` te invita a hacer— **pasa siempre el dict de config completo**.

---

## D-2 · Otros tres defectos por defecto del mismo tipo
| constante | valor por defecto en el módulo | valor de v10 |
|---|---|---|
| `M_FUN` (`pipeline3.py:43`) | 3.0 | **4** |
| `EXP_FUN` (`pipeline3.py:43`) | 1000.0 | **1480** |
| margen en `holg` (`pipeline3.py:~165`) | 150.0 codificado | **40** (vía `cal_rth`) |

Mismo patrón, misma mitigación: V10 los pasa todos, `comprueba_config.py` los asevera.

---

## D-3 · `sesion()` usa el `DLL` global en la rama `b_cond`
`pipeline3.py:67`:
```python
_imp = Mm > (DLL + _CMS * kcap) * cond      # ← DLL global, no _DLL
```
El resto de la función usa correctamente el `_DLL` parametrizado. Solo esta línea no.

**Por qué no muerde:** `b_cond = 0` en la config V10 y en los 34 ejes de la tabla de estrés,
así que la rama entera está muerta.

**Cómo muerde si alguien la despierta:** el eje `regla_DLL_750` **sí** pasa `dll=750`. Si
algún día se combina `dll=` con `b_cond > 0`, el resultado es **silenciosamente incorrecto**
—no falla, da otro número—. Si vas a tocar `b_cond`, arregla esto primero **y pregunta antes
de hacerlo**, porque cambiar `modelo/` obliga a regenerar el replay y la tabla de estrés.

---

## D-4 · La rama `b_cond` en sí
No es un bug, es un experimento: soltar el buffer los días en que la muerte es imposible.
Está **medido y rechazado** (1.198,5 → 1.069,2 $/mes, P(degradar) 1,10 % → 17,19 %; ver
`cifras_citadas.json`). No se activa.

---

## Cómo se comprueba que siguen sin morder

```bash
python tests/comprueba_config.py     # asevera que la config pasa todos los valores buenos
python modelo/cifras_citadas.py      # regenera las cifras con el dict de config completo
```

Si alguna vez uno de estos defectos entra en la ruta activa, la cifra se moverá y
`comprueba_config.py` o el replay lo cazarán. **Ninguno se arregla sin permiso explícito.**

---

## D-5 (`bot/`, NO `modelo/`) · `qok` causal en vivo

A diferencia de D-1 a D-4, este NO es un defecto de `pipeline3.py` -- `modelo/` sigue
intacto y R6 sigue aplicando igual. Se registra aquí porque el operador pidió una sola
lista de defectos conocidos y asumidos (`RESPUESTA_D8_CONCURRENCIA.md` §5), no porque
`modelo/` haya cambiado.

**El defecto:** el motor congelado (y por tanto el replay de 504 días) evalúa el tope de
recámara (`qcap_abierto_por_tesoreria`, R-4.6) con la caja del día **DESPUÉS** de sumar el
P&L de funded de hoy (`orquestador.procesa_dia()`, camino de replay: funded se procesa
primero, y `qok` de eval se calcula con `st["caja"]` ya actualizada). El bot en vivo
(`bot/bucle_de_tiempo.py`, D8.4 reestructuración, 20-08-2026) resuelve funded y eval A LA
VEZ, por un bucle de tiempo compartido -- así que `qok` solo puede calcularse con la caja
de **INICIO** de día, antes de que corra ninguna sesión de hoy: usar el P&L de funded de
HOY para decidir si eval puede abrir HOY sería mirar al futuro de la propia sesión de hoy,
imposible en un bot real.

**Por qué existe (no es un bug):** con `ResuelveDiaEnVivo` (bloqueante, dueño de su propio
cursor de barras) eval no podía empezar su sesión hasta que funded resolviera la SUYA
entera, si las dos estaban activas el mismo día -- medido contra el pack: 222/504 días
(44 %). La reestructuración a un bucle de tiempo compartido es la corrección de ESE bug
real; el precio es que `qok` deja de poder mirar el resultado de funded de hoy.

**Medido, no estimado:** sobre `tests/replay_v10.json`, el orden `funded→eval` (el del
motor congelado) solo cambia el valor de `qok` en **1 de 504 días** (el día 269 --
`caja − retirado` cruza `qcap_tes_usd` = 10.000 $ durante ESE mismo día, por el P&L de
funded). Corriendo el replay completo con `qok` causal en vez de con el orden actual:

| | caja final |
|---|---|
| orden actual (contrato del motor congelado) | 29.134,87 $ |
| `qok` causal (lo que verá el bot real) | 29.085,13 $ |
| diferencia | −49,74 $ en 504 días (≈ −2,07 $/mes, ≈ −0,17 %) |

**No se corrige:** corregirlo exigiría que el bot conociera el futuro de la sesión de hoy
de funded antes de que termine. LA PUERTA GRANDE (`ORDEN_DE_TRABAJO_D8.md` §4) se corre en
dos pasadas precisamente por esto -- Pasada A (fidelidad, `qok` del contrato inyectado por
el arnés) exige 0 discrepancias contra el replay; Pasada B (causalidad, el `qok` real que
usará el bot) exige que la ÚNICA divergencia sea, exactamente, la de este defecto (día 269,
−49,74 $) -- si diverge en cualquier otro día, es un bug de verdad, no este defecto.
