# 02 · ARQUITECTURA · cómo se construye el bot
### Módulos, máquina de estados, esquema de `estado.json`, y el día minuto a minuto.
Este documento dice **cómo organizar el código**. Lo que el código debe *hacer* está en
`01_ESPECIFICACION_E2E.md` y los números en `03_CONFIG.yaml`.

---

## 1 · Principio de diseño: el núcleo no sabe que existe el mundo

```
                 ┌──────────────────────────────────────────┐
                 │            NÚCLEO (puro)                 │
                 │  sizing.py   ·   sesion.py               │
                 │  sin red, sin reloj, sin ficheros,       │
                 │  sin aleatoriedad, sin logging           │
                 │  entra un dict → sale un dict            │
                 └──────────────────▲───────────────────────┘
                                    │  (llamadas puras)
    ┌───────────────────────────────┴────────────────────────────────┐
    │                        ORQUESTADOR                             │
    │  ciclo_vida.py · tesoreria.py · calendario.py · estado.py      │
    │  decide qué cuenta opera, compra/cancela subs, retira, para    │
    └───────────────▲────────────────────────────────▲───────────────┘
                    │                                │
        ┌───────────┴──────────┐         ┌───────────┴────────────┐
        │  ADAPTADOR PROP      │         │  ADAPTADOR HEDGE       │
        │  (MFF / plataforma)  │         │  (AMP-CQG / NT)        │
        └──────────────────────┘         └────────────────────────┘
                    │                                │
        ┌───────────┴────────────────────────────────┴───────────┐
        │  SIMULADO  (fase 1)  →  PAPEL (fase 2)  →  REAL (fase 3)│
        └────────────────────────────────────────────────────────┘
```

**La regla que hace que esto funcione:** el núcleo se valida con `tests/goldens_v10.json`
y **no puede tener dependencias**. Si para pasar un golden necesitas importar algo que
lee el reloj o la red, has puesto la lógica en el sitio equivocado.

---

## 2 · Módulos, uno por uno

| módulo | responsabilidad | **prohibido** |
|---|---|---|
| `config.py` | **Solo** cargar y validar `03_CONFIG.yaml`. Comprueba los DERIVADOS con assert. | contener cualquier número |
| `sizing.py` | R-2: `fl`, `Mm`, `G`, `den`, las dos pasadas de `k`, bloqueo, `nu`, `ndn` | tocar estado, loguear, llamar a brokers |
| `sesion.py` | R-3: barrido de barras desde `b0+1`, desempate, muerte EOD, P&L del hedge | conocer cuentas, pool, tesorería |
| `ciclo_vida.py` | R-4 y R-5: pool, empalme, reset, emergencia, recámara, relevo, escalera | aritmética de sizing (la pide a `sizing.py`) |
| `tesoreria.py` | R-7: muro dinámico, degradación, retiro mensual, `qcap`/`qcap_tes` | decidir operaciones |
| `calendario.py` | R-6: dirección (sorteo + CONTRA), ventana RTH/22h, campana T−20 | mirar precios |
| `estado.py` | serializar/deserializar `estado.json`, con versión y checksum | lógica de negocio |
| `adaptadores/` | traducir intención → órdenes; traducir fills → hechos | decidir nada |
| `bot.py` | el bucle: leer estado → calendario → sesión → persistir → dormir | contener reglas |

**Regla de dependencias (se comprueba con un test):**
`sizing` y `sesion` no importan **nada** del proyecto salvo `config`.
`adaptadores` no importan `ciclo_vida` ni `tesoreria`.

---

## 3 · La máquina de estados

### 3.1 · Suscripción (pool)

```
   COMPRADA ──────► FRESCA ──────► OPERANDO ──────► ROTA
                       ▲               │             │
                       │               ▼             │ reset gratis (prob 1/30 diaria)
                       │           APROBADA          │ o EMERGENCIA (cancelar+recomprar $77)
                       │               │             │
                       └───── recompra ┘             └──────────────┘
```
- `OPERANDO → ROTA`: la cuenta murió.
- `OPERANDO → APROBADA`: tocó objetivo con `bal ≥ objetivo_eval_usd` → `sunk` a la recámara,
  se cancela la sub y se **recompra** una nueva.
- `ROTA → FRESCA`: reset gratuito de su día de facturación.

### 3.2 · Cuenta fondeada

```
   RECÁMARA(dormida) ──activación──► ACTIVA[ciclo 1..5] ──cobro──► ACTIVA[ciclo+1]
          ▲                              │      │                        │
          │                              │      │ muerte                 │ ciclo 5 cobrado
          │                              │      ▼                        ▼
          └──── nueva aprobación ────    │   ESPERA_RELEVO ◄──────── CERRADA
                                         │        │
                                         │        └── al día siguiente de negociación → ACTIVA
                                         ▼
                                     BLOQUEADA (k<1) — no opera, no muere, espera
```
**Como mucho UNA fondeada ACTIVA.** `BLOQUEADA` no es un estado terminal ni un error.

### 3.3 · Slot de evaluación

Un único slot (`n_evals_simultaneas = 1`). En un día:
```
  slot vacío ──toma fresca──► sesión 1 ──┬── sobrevive/pausa → sigue mañana
                                         ├── aprueba → slot vacío
                                         └── muere ──┬── barra < NB−4 y hay fresca → EMPALME
                                                     │      └► sesión 2 (media fricción)
                                                     └── si no → slot vacío hasta mañana
```
**Máximo dos sesiones en el día, y solo si son cuentas distintas.**

---

## 4 · `estado.json` · el esquema

Es la memoria del bot entre días. **Se escribe de forma atómica** (fichero temporal +
`rename`) y se versiona. Campos, con su equivalencia exacta en la traza de referencia
(`tests/replay_v10.json` → `fin_de_dia`):

```jsonc
{
  "version_esquema": 1,
  "version_config": "v10",
  "checksum_config": "<sha256 de 03_CONFIG.yaml>",
  "dia_negociacion": 137,             // contador, no fecha
  "fecha_ultimo_cierre": "2026-08-19",

  "caja": 4812.55,                    // USD reales acumulados (incluye cuotas pagadas)
  "retirado": 0.0,                    // acumulado retirado del sistema

  "direccion": -1,                    // +1 largo prop / -1 corto prop
  "contra_pendiente": 0,              // días que queda por mantener la dirección

  "funded": {
    "activa": false,
    "fase": 0,                        // ciclo 1..5 (0 = no activa)
    "bal": 0.0, "pico": 0.0,
    "H": 0.0,                         // P&L acumulado del hedge de ESTE linaje
    "s0": 0.0,                        // coste hundido vivo
    "dias": 0,                        // días de negociación en el ciclo (para dias_min_eval)
    "espera": 0                       // días de relevo pendientes
  },

  "eval": {
    "activa": false,
    "bal": 0.0, "pico": 0.0,
    "H": 0.0, "s0": 0.0,
    "aprobada_provisional": false,     // el fill dice que aprobó...
    "aprobada_confirmada": false       // ...pero hasta que el humano lo confirma, NO cuenta
  },

  "recamara": {                       // ← DESAGREGADA en el bot (el modelo agrega; ver R-7.4)
    "dormidas": [ {"s0": 286.8, "desde_dia": 12} ],
    "n": 1,
    "sunk_total": 286.8               // debe cuadrar con sum(dormidas[].s0)  ← ASSERT
  },

  "pool": {
    "frescas": 2, "rotas": 0,
    "subs": [                          // el humano mantiene esta lista (ver §8)
      {"sub_id": "MFF-...", "estado": "FRESCA", "dia_facturacion": 7},
      {"sub_id": "MFF-...", "estado": "ROTA",   "dia_facturacion": 22}
    ]
  },

  "pendientes_humano": [               // alertas abiertas; el bot NO actúa por su cuenta
    {"que": "recomprar_sub", "desde_dia": 136, "deadline": "apertura siguiente"}
  ],

  "acumulados_mes": { "peak": 0.0, "dias_desde_retiro": 4 },

  "degradado": false,                 // una vez true, NO se revierte solo
  "dia_degradacion": null
}
```

**Invariantes que el bot comprueba al cargar Y al guardar (fatales, no warnings):**
1. `recamara.sunk_total == sum(recamara.dormidas[].s0)` (tol. 1e-6)
2. `recamara.n == len(recamara.dormidas)`
3. `pool.frescas + pool.rotas + (1 si eval.activa) == subs_compradas_vivas`
4. `funded.activa` ⟹ `1 ≤ funded.fase ≤ 5`
5. `funded.espera > 0` ⟹ `funded.activa == false`
6. `checksum_config` coincide con el fichero actual — **si no, el bot NO arranca.**
7. `eval.aprobada_confirmada` ⟹ `eval.aprobada_provisional` (nunca al revés).
8. Ninguna dormida entra en `recamara.dormidas` sin `aprobada_confirmada` (§8).

---

## 5 · El día, barra a barra

**En barras, no en reloj.** El modelo trabaja sobre **86 de las 88 barras de 15 min** que
trae la serie: la sesión es de 22 h y se deja de operar en los **últimos 30 minutos**.
**Ningún artefacto del paquete fija una hora de reloj.** El mapeo barra → hora lo establece
el adaptador contra el horario real del contrato; hasta entonces es una **pregunta**, no un
dato (`03_CONFIG.yaml` → `sesion.barras_por_dia.ojo`).

`b0` es la barra de entrada: **0** en la ventana de 22 h, **62** en día de dato (RTH).

| momento | qué hace el bot |
|---|---|
| **antes de `b0`** | Carga `estado.json`. Valida invariantes. Valida checksum de config. **Si algo falla: no opera y avisa.** |
| | Lee `pendientes_humano`: si hay una alerta sin resolver que bloquea el día, **se anota y el slot queda vacío** (§8). No se improvisa. |
| | Aplica **resets gratuitos** que tocan hoy (R-4.4) y **activación de dormida** si la espera venció (R-5.1/5.2) **y está confirmada**. |
| | Decide **dirección** (sorteo, o mantener si CONTRA está pendiente — R-6.1). |
| | Decide **ventana**: ¿hoy hay dato? → RTH, entrada en `b0_rth`. Si no → 22 h, `b0=0` (R-6.2). |
| | Comprueba `qcap` / `qcap_tes` (R-4.6): ¿se abre intento de eval hoy? |
| **barra `b0` (cierre)** | Para **cada cuenta que opera**: resuelve el sizing (R-2). Si `k < 1` → **bloqueo**, esa cuenta no abre nada. |
| | Abre `k` contratos en la prop y `m` micros **en contra** en el bróker. **Las dos patas o ninguna.** |
| **barras `b0+1` … 85** | Vigila. Suelo → cierra al DLL (pausa o muerte, R-3.4). Objetivo → cierra y evalúa aprobación/cobro. |
| | Si murió la eval y quedan ≥4 barras y hay fresca → **empalme** heredando el hedge (R-4.3). |
| **barra 85 (campana)** | Cierra **todo** lo que siga abierto. Las barras 86 y 87 (los últimos 30 min) **no se operan**: no se lleva posición al cierre oficial. |
| **tras la campana** | Actualiza `caja`, `H`, `s0`, recámara, pool. Aplica **CONTRA** si hubo muerte. |
| | Recalcula el **muro dinámico** y comprueba **degradación** (R-7.2). |
| | Si toca fin de mes (cada `dias_por_mes`): **anota el retiro** (R-7.3) — moverlo lo hace el humano. |
| | Emite las **alertas** del día (recomprar, cancelar, confirmar aprobación, pedir payout). |
| | Escribe `estado.json` **atómicamente**. Escribe la línea del diario. |

---

## 6 · El diario (una línea por día, append-only)

Formato JSONL. **Debe contener lo suficiente para reconstruir el día y para compararlo con
`tests/replay_v10.json`.** Campos mínimos, con los nombres del replay pack para que el
runner los compare directo:

```json
{"dia":137,"direccion":-1,"ventana":"22h",
 "eventos":{"intentos":1,"aprobaciones":0,"muertes_funded":1,"resets":0,
            "emergencias":0,"recompras":0,"cuotas_dia":0.0},
 "invariantes":{"sesiones_de_eval":1,"empalmes":0,
                "peor_dia_una_cuenta_eval":-412.3,"peor_dia_funded":-1000.0,
                "bloqueo_funded":0},
 "fin_de_dia":{ ...el mismo bloque que estado.json... }}
```

**Por qué importa:** con este diario, `tests/runner_replay_v10.py` compara tu bot contra
504 días de referencia sin que tengas que instrumentar nada más.

---

## 7 · Las dos patas, o ninguna

El fallo operativo más caro que puede tener este bot **no** es un error de cálculo: es
quedarse con **una sola pata abierta**. Sin hedge, la cuenta prop es una posición
direccional desnuda; sin cuenta prop, el hedge es una pérdida pura.

**Requisitos, no sugerencias:**
1. **Apertura:** se manda primero la pata **real** (el hedge) y solo cuando está confirmada
   se manda la de la prop. Si la prop no confirma en `N` segundos → **cerrar el hedge y no
   operar hoy**. (El valor de `N` no está en config: **hay que decidirlo — pregunta.**)
2. **Cierre:** el orden inverso.
3. **Reconciliación al arrancar:** antes de nada, el bot compara posiciones reales en ambos
   lados contra `estado.json`. Si no cuadran, **no opera**: avisa y para.
4. **Nunca se reintenta una pata en bucle.** Un fallo de pata es motivo de parada del día.

> Esto **no está en el modelo** (el simulador asume ejecución perfecta salvo el
> deslizamiento). Es riesgo de ingeniería puro y por eso está aquí y no en la norma.

---

## 8 · Lo que el bot NO hace: las acciones manuales

**Esto es la diferencia más importante entre el modelo y el bot, y hay que tenerla clara
desde el primer delta.**

El simulador asume que comprar una suscripción, cancelarla, activar una dormida o cobrar un
payout ocurre **instantáneamente y solo**. En la realidad **ninguna de esas cosas tiene API**:
se hacen en la web del proveedor, a mano.

> **El bot NUNCA compra, NUNCA cancela, NUNCA activa y NUNCA mueve dinero.
> Alerta, y espera a que el humano confirme en `estado.json`.**

| acción | quién | cómo lo ve el bot |
|---|---|---|
| Comprar / recomprar una suscripción | **humano** | el bot emite alerta con deadline la apertura siguiente; el humano anota `sub_id` y día de facturación en el estado; el bot **valida el cambio al cargar** |
| Cancelar una rota (emergencia) | **humano** | igual |
| Confirmar que una eval ha **aprobado** | **humano** | el bot marca `APROBADA_PROVISIONAL` con el fill y **exige un visto bueno explícito** antes de que esa cuenta sea elegible como fondeada. **Nunca se activa una fondeada no confirmada.** |
| Solicitar el payout | **humano** | el `W` entra en caja **cuando llega y está conciliado**, no cuando se devenga |
| Retirar a la cuenta bancaria | **humano** | el bot solo lo contabiliza |
| Abrir y cerrar posiciones | **bot** | lo único que el bot hace solo |

**Consecuencia de ingeniería:** entre "el modelo dice que hoy arranca un intento" y "hay una
cuenta operable" hay un paso humano que puede tardar. El bot tiene que tolerar ese retraso
sin corromper el estado: si la fresca no está, **el slot se queda vacío ese día** y se anota.
Eso es exactamente lo que el modelo llama `idle`, y es una de las razones por las que el bot
real rendirá **por debajo** del modelo, no por encima.

---

## 9 · Modo de operación y banderas

| bandera | qué hace | por defecto |
|---|---|---|
| `--modo simulado` | adaptadores falsos, barras de fichero. Fase 1. | — |
| `--modo papel` | cuentas demo en ambos lados. Fase 2. | — |
| `--modo real` | dinero real. Fase 3. | **nunca por defecto** |
| `--replay <fichero>` | fuerza dirección, ventana, resets y barras desde el pack | — |
| `--dry-run` | calcula todo y **no manda ninguna orden**; escribe el diario | — |
| `--parar` | cierra todo ordenadamente y no vuelve a abrir | — |

**`--modo real` exige confirmación explícita y que las tres puertas de
`05_ORDEN_DE_CONSTRUCCION.md` estén verdes.** No hay atajo.
