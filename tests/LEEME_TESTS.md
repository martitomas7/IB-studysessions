# tests/ · qué hay aquí y cómo se usa

Todo esto **ya está verde** sobre el motor congelado. Su función no es "pasar": es
**romperse cuando construyas mal**. Cada suite viene con su prueba de que sabe romperse.

---

## Los seis comandos

```bash
python tests/comprueba_config.py            # D0 · el YAML cuadra y coincide con lo medido
python tests/runner_goldens_v10.py          # D1 · 14/14 sobre el núcleo de referencia
python tests/prueba_goldens_v10.py          # D1 · demuestra que los goldens discriminan
python tests/prueba_nucleo_vs_motor.py      # D1 · núcleo == motor en 60.000 estados
python tests/runner_replay_v10.py           # Fase 1 · 504 días · 0 fallos
python tests/prueba_replay_v10.py           # Fase 1 · demuestra que el replay discrimina
```

---

## Precedencia: quién manda si dos cosas discrepan

`01_ESPECIFICACION_E2E.md` dice «la norma manda sobre el código y sobre los tests». Eso vale
para **tu** código. Entre los tres artefactos del paquete —la norma en prosa, el núcleo de
referencia y el motor congelado— la regla es distinta y es ésta:

> **Hoy no discrepan.** `prueba_nucleo_vs_motor.py` los compara en 60.000 estados y da **0
> discrepancias**, con 2.830 muertes, 20.597 bloqueos y 11.219 objetivos ejercitados. Si
> algún día divergen, **no gana ninguno por defecto: paras y preguntas.** Una divergencia
> entre la norma y su propia implementación ejecutable no es algo que se resuelva eligiendo;
> es la señal de que alguien entendió algo mal, y hay que averiguar quién.

Para validar **tu** código, pásale el módulo:
```bash
python tests/runner_goldens_v10.py mi_nucleo      # debe exponer resolver_sesion(entradas)->salidas
python tests/runner_replay_v10.py  mi_orquestador
```

---

## Ficheros

| fichero | qué es |
|---|---|
| `nucleo_referencia_v10.py` | **La especificación EJECUTABLE del núcleo.** Python puro, sin numpy, 70 líneas |
| `prueba_nucleo_vs_motor.py` | compara el núcleo contra el motor congelado en 60.000 estados |
| `goldens_v10.json` | 14 casos de sesión con entradas y salidas exactas |
| `runner_goldens_v10.py` | valida cualquier adaptador contra los goldens |
| `prueba_goldens_v10.py` | rompe el núcleo de 3 maneras y exige que los goldens caigan |
| `replay_v10.json` | **504 días** de traza día a día (semilla 14): barras, dirección, ventana, eventos, invariantes y `fin_de_dia` |
| `replay_v10.py` | el generador de la traza (por si hay que regenerarla) |
| `runner_replay_v10.py` | compara estado + invariantes de tu orquestador contra la traza |
| `prueba_replay_v10.py` | 8 orquestadores rotos a propósito; demuestra qué caza el replay |
| `comprueba_config.py` | valida `03_CONFIG.yaml` y que sigue siendo la config medida |

---

## Qué caza el replay pack (medido, no prometido)

| orquestador roto | divergencias de estado | invariantes rotos | 1er día |
|---|---|---|---|
| **CORRECTO** | **0** | **0** | — |
| relevo D+2 (un día tarde) | 2.296 | 0 | 4 |
| `qcap` ignorado (recámara sin tope) | 2.405 | 0 | 25 |
| la eval **superviviente** opera dos veces | 2.499 | **275** | 2 |
| look-ahead en la barra de entrada | 2.359 | 0 | 9 |
| opera la cuenta bloqueada (viola R-2.4) | 296 | **1** | 210 |
| bug de v8 «doble sesión de la eval» | 0 | 0 | — |
| empalme sin tope de 1/día | 0 | 0 | — |

**Las dos últimas filas dan 0 y está bien.** A `R=1` (un solo circuito, que es lo que es el
bot) esas dos perturbaciones son **no-ops estrictos**: el bug de v8 era un artefacto de
vectorización (`mu.any()` es una reducción global sobre réplicas). Se publican precisamente
para que nadie las cuente como cobertura que no existe.

---

## Cobertura de rama de la traza (medida sobre los 504 días)

| rama | veces |
|---|---|
| fase 1 / 2 / 3 / 4 / **5** | 366 / 94 / 31 / 8 / **4** |
| empalme | 150 |
| **bloqueo (R-2.4)** | **1** |
| aprobación | 98 |
| muerte de fondeada | 94 |
| emergencia | 138 |
| reset gratis | 11 |
| ventana RTH | 94 |
| dirección corta | 225 |

La semilla 14 se eligió **deliberadamente**: el bloqueo de R-2.4 ocurre en 5 de 80 semillas,
y sin él esa rama queda sin cubrir. La traza se extendió a 504 días para que además llegara
a la **fase 5**.

---

## Lo que estas suites NO cubren, dicho claro

- **Ejecución.** El modelo asume fills perfectos salvo el deslizamiento. Nada de aquí prueba
  el manejo de rechazos, patas colgadas, desconexiones o latencia.
- **Los adaptadores de bróker.** Ni una línea.
- **La política de orden de activación de dormidas** (R-7.4): el modelo agrega la recámara.
- **Cambios de reglas del proveedor.** Eso está en `modelo/estres_v10.json`, no aquí.

---

## `modelo/` · el simulador congelado

Se incluye para que puedas **contrastar**, no para que lo modifiques.
```bash
python -c "import sys; sys.path.insert(0,'modelo'); import pipeline3"
```
Trae `motor_exp.py` y `modelo/datos/{HG22,LG22,CG22}.npy` para que funcione sin el
laboratorio original. `pipeline2_congelado_REFERENCIA.py` es el motor **con** los dos bugs
históricos: existe solo como referencia de regresión.

| fichero | qué es |
|---|---|
| `estres_v10.py` → `estres_v10.json` | la tabla de estrés: 34 ejes × 8 semillas, con sd en las dos columnas |
| `cifras_citadas.py` → `cifras_citadas.json` | **regenera todas las cifras que la norma cita**: identidad de cobertura, holgura y déficit por deslizamiento, libro del hedge, experimento `b_cond`, coste de los dos bugs, campana, y el **barrido fino de la puerta F3.1**. ~10 min |
| `DEFECTOS_CONOCIDOS.md` | los cinco defectos del motor congelado que **no** se corrigen, y por qué ninguno muerde |

> **Regla R6:** no se toca. Si crees que el modelo está mal, **para y pregunta**.
>
> **Y si lo usas para contrastar: pásale SIEMPRE el dict de config completo.** Los valores
> por defecto del módulo son los viejos (`CMS=1.04`, `M_FUN=3.0`, `EXP_FUN=1000.0`) y una
> llamada incompleta te da otra cifra sin avisar. Ver `modelo/DEFECTOS_CONOCIDOS.md`.
