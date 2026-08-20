# Recomendaciones — para evaluar, no aplicadas automáticamente

Todo lo de abajo fue una propuesta razonada en la entrega original de D-C (20-08-2026, primera pasada):
ninguna se aplicó sola en ese momento, precisamente porque cada una tocaba código ya verificado (D2-D7,
504/504) o dependía de una máquina que este entorno no tiene (NT8 real). Estaban ordenadas por impacto.

**Actualización 20-08-2026, revisión 4 — el operador dio veredicto sobre las 7 y encontró, además, tres
defectos reales en el protocolo de las dos patas que ninguna recomendación cubría** (`REVISION_ENTREGA_
20260820.md`). Los tres defectos, corregidos en esta misma pasada, están documentados en
`07_ADAPTADOR_NT8.md` §5.3 (revisión 4) y en `08_LABORATORIO.md` §12 (historial, revisión 4) — no se
repiten aquí porque este fichero es sobre recomendaciones, no sobre defectos; el resumen de una línea:
(1) un rechazo/cancelación limpios del bróker se trataban como "el timeout expira" en vez de como
información cierta, desperdiciando `N`/`N_hedge` sin necesidad; (2) `hay_conexion()` nunca se llamaba
antes de abrir una pata, pese a que el contrato del puerto lo exige; (3) el reintento de cierre decidía
si había terminado mirando el estado de la última orden, no la posición real de la cuenta. Los tres,
corregidos, con `verificacion_R3/prueba_protocolo_dos_patas.py` §§8-10 (40/40 verde) como comprobación R3.

Cada recomendación de abajo lleva ahora su estado real, con el veredicto del operador citado donde lo dio.

---

## 1 · Cablear `valor_efectivo()` dentro de `ciclo_vida.py` (prioridad alta) — ✅ HECHO (revisión 4)

**Veredicto del operador:** hacerlo ya, junto con las recomendaciones 2 y 5 (todas tocan el mismo
fichero), con la re-verificación bit-idéntica del replay como única condición de aceptación.

**Qué se hizo.** `bot/comandos.py::valor_efectivo()` ya decide el valor real de las cuatro palancas de
Clase B: `empalme` y `pausa_eval` (intento nuevo de eval) en `bot/ciclo_vida.py::procesa_dia_eval`,
`emergencia` en `toma_sub`, y `contra` en `bot/calendario.py::sortea_direccion` (con
`valor_apagado=0`, no `False`, porque es numérico). `ciclo_vida.py` ya no lee `cfg.orquestacion.*`
directo para estas cuatro.

**Aceptación (la única que pedía el operador):** `desviaciones_activas=[]` (el caso del replay) hace que
`valor_efectivo()` devuelva siempre el valor certificado — por diseño, un no-op garantizado. Re-corrido
`bot/orquestador.py tests/replay_v10.json` + `tests/runner_replay_v10.py`: **504 días · 0 fallos · caja
final 29.134,87 $, sin cambio.**

---

## 2 · `ciclo_vida.py` no distingue "muertes de eval" de "muertes totales" en el diario — ✅ HECHO (revisión 4)

**Veredicto del operador:** en la misma pasada que 1 y 5.

**Qué se hizo.** `eventos["muertes_eval"] += 1` añadido en los dos puntos de muerte de una eval dentro de
`ciclo_vida.py::procesa_dia_eval` (intento 0 y empalme). `bot/orquestador.py` lo acumula en el diario
igual que los demás contadores. `bot/contexto_dashboard.py::_agrega_eventos` ya lo agrega, y el bloque 6
(MODELO vs REALIDAD) del dashboard ya compara la tasa observada contra `modelo/cifras_citadas.json` —
deja de decir "no trackeado todavía".

---

## 3 · Reconciliar la discrepancia "5 días" vs "~7 días" (cuenta bloqueada) — ✅ RESUELTO, no como se pensaba (revisión 4)

**Veredicto del operador, textual en sustancia:** no es una discrepancia que resolver a un solo número —
son **dos relojes distintos**, y el dashboard debe mostrar los dos.

**Qué se hizo.** `03_CONFIG.yaml` §10 reescrita: `alertas.bloqueada_escalada_dias` (5, DADO, reloj del
BOT — cuándo el propio bot escala la alerta a un canal más ruidoso) y `alertas.proveedor_mata_cuenta_dias`
(7, SUPUESTO con virgulilla en su propia fuente, reloj del PROVEEDOR — cuándo MyFundedFutures mata la
cuenta por inactividad) — dos claves separadas, cada una con su fuente propia, ninguna sustituye a la
otra. `bot/contexto_dashboard.py` calcula ambos por pendiente bloqueada (`dias_esperando` contra el
umbral del bot; `dias_hasta_proveedor_mata = max(0, proveedor_dias - dias_esperando)`), y
`bot/dashboard.py` (bloque 3, PENDIENTES) pinta las dos columnas con semáforo propio en cada una —
verificado con render real (Playwright + Chromium) y valores sintéticos (3/6/8 días bloqueada → 4/1/0
días restantes de proveedor, semáforos aviso/grave/crítico respectivamente).

---

## 4 · `da1_diagnostico.ps1` e `IndicadorLaboratorioMercado.cs` siguen sin validar contra NT8 real — sin acción (correcto, según el operador)

**Veredicto del operador:** bloqueado, correctamente, hasta que haya máquina real — ninguna acción posible
desde esta sesión de ingeniería.

Ninguno de los dos se ha podido compilar/ejecutar en este entorno (Linux, sin NT8 ni PowerShell real).
Cuando haya máquina Windows con NT8 disponible, en este orden:
1. Correr `da1_diagnostico.ps1` entero (incluido el bloque D-A1.2b de estado del feed) y pegar la salida
   completa — es la comprobación que decide si el Camino B (§2 de `07_ADAPTADOR_NT8.md`) sigue siendo
   viable tal cual está escrito.
2. Compilar `IndicadorLaboratorioMercado.cs` en el editor de NinjaScript (F5). Los dos puntos marcados
   "SIN VERIFICAR" en el propio fichero (la firma de `OnMarketData`, y el cálculo de "día de negociación"
   para la rotación de fichero) son los primeros candidatos a fallar.
3. Una vez el indicador escriba de verdad `laboratorio/mercado_<dia>.jsonl`, falta un lector pequeño
   (`bot/contexto_dashboard.py` hoy solo acepta una lista de snapshots ya en memoria, vía el parámetro
   `mercado_snapshots=`) que lea esos ficheros JSONL reales — no escrito en este pase porque no hay
   ficheros reales contra los que probarlo todavía.

---

## 5 · Bloque 1 del dashboard no muestra `k`/`m` reales de las patas abiertas — ✅ HECHO (revisión 4)

**Veredicto del operador:** en la misma pasada que 1 y 2.

**Qué se hizo.** `ciclo_vida.py::procesa_dia_eval` persiste `ev["k"]`/`ev["m"]` tras cada sesión resuelta
(intento inicial y empalme); `procesa_dia_funded` persiste `fu["k"]`/`fu["m"]` igual. `bot/estado.py`
gana `k: 0.0, m: 0.0` en el esquema de arranque en frío de ambos dicts. El dashboard ya no recalcula —
solo muestra lo que `ciclo_vida.py` ya usó ese día, tal como pedía la recomendación original.

---

## 6 · `09_DESPLIEGUE.md` sigue sin escribir — confirmado como siguiente paso (revisión 4)

**Veredicto del operador:** "Sí, pero después de la pasada de arriba" — confirmado que no necesita nada
de NT8. Es el siguiente documento a escribir tras cerrar esta revisión.

Sin relación con D-C — ya estaba anotado como pendiente antes de esta sesión
(`05_ORDEN_DE_CONSTRUCCION.md`, "Entregable previo a FASE 2"). El hueco real antes de D8: el watchdog de
proceso, arranque automático, permisos, y el registro de contra qué build de NT8 se validó por última vez
el adaptador.

---

## 7 · El mecanismo de comandos existe, pero nada lo invoca todavía en un bucle real — sin acción (correcto, alcance D8)

**Veredicto del operador:** confirmado como alcance de D8, sin acción en esta revisión.

`bot/comandos.py` (escribir, leer pendientes, procesar con caducidad/idempotencia) está construido y
probado como librería. Falta el bucle que, dentro del bot corriendo de verdad (D8), llame a
`comandos.lee_pendientes(directorio, clase='A')` de forma continua durante la sesión y a
`clase='B'` en el punto de decisión del día siguiente, tal como exige `08_LABORATORIO.md` §7.3 — eso es
integración de D8, no de D-C, y depende de que D8 exista.
