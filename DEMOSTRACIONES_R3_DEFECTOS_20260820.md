# Demostraciones R3 · los tres defectos de `REVISION_ENTREGA_20260820.md`

**R3 (04_GUARDARRAILES_CONSTRUCCION.md): "nada se acepta como correcto sin haberse visto fallar
primero".** `verificacion_R3/prueba_protocolo_dos_patas.py` §§8-10 (40/40 verde) ya demuestra que el
código ACTUAL (corregido) se comporta bien. Este documento es la otra mitad: reconstruye literalmente el
comportamiento de **antes** de la revisión 4, lo corre de verdad contra el mismo escenario que el
operador describió, pega la salida real de que sí falla — y solo entonces corre el código real para
confirmar que la revisión 4 lo corrige. Script fuente:
`verificacion_R3/demuestra_defectos_operador_20260820.py` (ejecutable tal cual, no forma parte de la
puerta D-C — es la demostración en sí, no un runner de CI).

Mismo método que `verificacion_R3/romper_mi_orquestador.py` (D2-D7): para el Defecto 2, el guardián de
conexión se quita del código fuente real vía string-replace + `exec` — no se toca ningún fichero en
disco, solo una copia en memoria de esa corrida.

---

## Defecto 1 · rechazo/cancelación limpios tratados como "sigue viva"

Un `RECHAZADA` instantáneo del bróker (antes de que expire `N`/`N_hedge`) es información **cierta**, no
ambigua — pero el código de antes de la revisión 4 solo sondeaba hasta `LLENA`, así que lo trataba igual
que "el timeout expira", consumiendo `N_hedge` = 30 s enteros sin necesidad.

```
==============================================================================
DEFECTO 1 · rechazo limpio del hedge ANTES de N_hedge (30 s)
==============================================================================

-- ANTES (reconstrucción literal de la revisión 3) --
  resultado: {'abierto': False, 'motivo': 'N_hedge_expirado_rechazada'}
  tiempo lógico consumido: 30.0 s  (N_hedge = 30.0 s)
  FALLA COMO SE ESPERABA (consume N_hedge entero pese al rechazo instantáneo): SI

-- DESPUÉS (bot/protocolo_dos_patas.py real, revisión 4) --
  resultado: {'abierto': False, 'order_id_hedge': 'FAKE-1', 'order_id_prop': None, 'motivo': 'hedge_rechazado_no_se_opera_hoy'}
  tiempo lógico consumido: 0.0 s
  eventos: [{'tipo': 'hedge_rechazado_limpio', 'order_id': 'FAKE-1', 'estado': 'RECHAZADA'}]
  CORREGIDO (cero tiempo, sin alerta máxima -- información limpia): SI
```

**Lectura:** antes, un rechazo instantáneo costaba los 30 s completos de `N_hedge` (y en el caso de la
prop, ese tiempo lo pasaría el hedge desnudo). Después, cero tiempo consumido y sin alerta máxima —
porque un rechazo limpio no es una situación ambigua que necesite que un humano mire.

---

## Defecto 2 · `hay_conexion()` ausente del guardián de apertura

El contrato del puerto (`07_ADAPTADOR_NT8.md` §1) exige comprobar la conexión "antes de cada operación" —
pero el código de antes de la revisión 4 nunca la llamaba en la práctica: una cuenta desconectada podía
terminar con ambas patas abiertas igual.

```
==============================================================================
DEFECTO 2 · hay_conexion() ausente del guardián de apertura
==============================================================================

-- ANTES (mismo módulo, guardián de conexión quitado por string-replace) --
  resultado: {'abierto': True, 'order_id_hedge': 'FAKE-1', 'order_id_prop': 'FAKE-2'}
  posiciones tras la corrida: {('CUENTA_HEDGE', 'MES (Micro E-mini S&P 500)'): -4, ('CUENTA_PROP', 'instrumento prop de ejemplo'): 10}
  FALLA COMO SE ESPERABA (abre las dos patas con la prop desconectada): SI

-- DESPUÉS (bot/protocolo_dos_patas.py real, revisión 4) --
  resultado: {'abierto': False, 'order_id_hedge': None, 'order_id_prop': None, 'motivo': 'conexion_caida_no_se_abre_nada'}
  posiciones tras la corrida: {}
  eventos: [{'tipo': 'conexion_caida', 'hedge_conectado': True, 'prop_conectado': False, 'alerta': 'MAXIMA'}]
  CORREGIDO (no abre nada, alerta máxima registrada): SI
```

**Lectura:** antes, con la cuenta prop desconectada, el módulo abría igualmente las dos patas (posiciones
reales de −4 y +10 en las dos cuentas). Después, con el mismo escenario, no se manda ninguna orden y se
registra una alerta de máxima prioridad — exactamente lo que exige el contrato del puerto.

---

## Defecto 3 · `aplanar()` salía por estado de la última orden, no por posición real

Si el bróker rechaza una orden de cantidad cero (posición ya plana) en vez de aceptarla como
no-operación, el reintento de cierre de antes de la revisión 4 podía no converger nunca — porque miraba
si la ÚLTIMA orden decía `LLENA`, y una orden rechazada nunca lo dice, aunque la cuenta ya esté
exactamente donde debía estar.

```
==============================================================================
DEFECTO 3 · aplanar() sale por estado de orden, no por posición
==============================================================================

-- ANTES (reconstrucción literal de la revisión 3, tope bajo de reintentos=5 solo para que la demostración no tarde) --
  posición de partida: (0, None)  (ya plana)
  confirmado=False, intentos=5
  eventos generados: 5 alerta(s) máxima(s)
  FALLA COMO SE ESPERABA (nunca converge, 5 alertas máximas sobre una cuenta YA plana): SI

-- DESPUÉS (bot/protocolo_dos_patas.py real, revisión 4) --
  posición de partida: (0, None)  (ya plana)
  confirmado=True, intentos=0
  eventos generados: 0 alerta(s) máxima(s)
  CORREGIDO (confirmado sin mandar NINGUNA orden, cero alertas): SI
```

**Lectura:** antes, con una cuenta ya exactamente plana y el adaptador simulando un bróker que rechaza
cantidad cero, el reintento no convergía nunca — 5 alertas de máxima prioridad sobre una cuenta que ya
estaba correcta (con `max_reintentos` real de producción, 10 000, habría sido una alerta cada 10 ms
durante 100 s antes de rendirse, sobre nada que arreglar). Después, la comprobación de posición al
principio de `_aplana_hasta_confirmar()` detecta que ya está en cero y no manda ninguna orden — cero
intentos, cero alertas.

---

## Cierre

Los tres defectos: reproducidos con el código de antes (reconstruido literal contra la propia
descripción del operador y las docstrings de `07_ADAPTADOR_NT8.md`), y confirmados corregidos con el
código real de `bot/protocolo_dos_patas.py` en su estado actual (revisión 4). Junto con
`verificacion_R3/prueba_protocolo_dos_patas.py` §§8-10 (40/40 verde), esto cierra el punto 7 del plan de
acción del operador: demostraciones R3 con salida real pegada para los tres defectos, no solo el código
corregido y una afirmación de que funciona.
