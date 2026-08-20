# simulador_nt8 — ESTO NO ES EL ADAPTADOR REAL DE NT8

**Léelo antes de usar cualquier fichero de esta carpeta.**

## Qué es

Un simulador de NT8 **independiente, fuera de proceso** — un proceso de sistema operativo aparte del
proceso Python del bot, que implementa el mismo contrato de puerto que `07_ADAPTADOR_NT8.md` §1 exige de
cualquier adaptador (`abrir`, `aplanar`, `cancelar`, `leer_estado_orden`, `leer_fill`, `leer_posicion`,
`hay_conexion`, `leer_cuenta`, `arrancar`/`parar`). Internamente **envuelve
`bot/adaptador_falso.py::AdaptadorFalso`** — no reimplementa su máquina de estados — y lo expone por un
socket `AF_UNIX` local, para poder probar de verdad lo que `AdaptadorFalso` en proceso estructuralmente
no puede: qué pasa si el proceso "NT8" muere a mitad de una orden, qué pasa si el proceso del BOT muere
con una posición real abierta y hay que reconciliar al reiniciar (`07_ADAPTADOR_NT8.md` §6), y si los
timeouts `N`/`N_hedge` se cumplen de verdad con reloj de pared real, no solo con el reloj lógico
instantáneo de las pruebas unitarias.

## Qué NO es

**No es `adaptadores/`.** El adaptador real de NT8 (D-A) sigue bloqueado por D-A1 hasta que haya una
máquina Windows con NT8 real para verificar firmas exactas, bitness, y el catálogo de errores de la ATI
— ninguno de esos datos existe todavía, y este simulador no los inventa ni los aproxima. Este paquete no
habla con NT8, no habla con la ATI, no habla con `NinjaTrader.Client.dll` — habla con
`simulador_nt8.servidor`, un proceso que **nosotros mismos** escribimos, contra el contrato que
**nosotros mismos** documentamos.

**Pasar la suite de `verificacion_R3/integracion_proceso_real/` no significa que D-A1 esté resuelto.**
Solo demuestra que nuestro propio protocolo de las dos patas, nuestro vigía de conexión, y nuestra
reconciliación de arranque se comportan como se espera bajo una frontera de proceso/red real — con
nuestra propia idea de cómo se comporta un bróker, fabricada por nosotros vía `AdaptadorFalso`. Si NT8
real resulta comportarse de forma distinta al contrato de `07_ADAPTADOR_NT8.md` §1 en algún detalle que
este simulador no anticipó, **solo D-A1 contra la máquina real puede descubrirlo** — este simulador no
tiene ninguna vía para saberlo.

## Salvaguardas contra confundirlo con algo real

1. **Nombre de paquete deliberadamente distinto de `adaptadores/`**, no anidado bajo él.
2. **El servidor se niega a arrancar sin `--entorno=pruebas` explícito** (`ServidorNT8Simulado.__init__`
   lanza `ValueError` sin ese flag exacto) — no hay valor por defecto que permita omitirlo por descuido.
3. **Solo `AF_UNIX`, nunca TCP** — estructuralmente inalcanzable desde fuera de esta máquina, a
   diferencia de un socket de red mal configurado. Los sockets viven en un directorio con permisos
   `0700`, bajo `/dev/shm` o el directorio temporal del sistema.
4. **Este mismo aviso** se repite como docstring de módulo en `servidor.py` y `cliente.py` — no hace
   falta haber leído este fichero para toparse con él.

## Estructura

```
simulador_nt8/
├── protocolo.py         framing JSON Lines compartido (servidor + los dos clientes)
├── errores.py           jerarquía de excepciones de TRANSPORTE (no del puerto -- ver errores.py)
├── motor.py              MotorSimulado: envuelve AdaptadorFalso con reloj REAL + ganchos de prueba
├── servidor.py           ServidorNT8Simulado: proceso independiente, dos sockets AF_UNIX (datos+control)
├── cliente.py            AdaptadorSimuladorNT8: implementa el puerto de 07_ADAPTADOR_NT8.md §1
├── cliente_control.py    ClienteControl: fabrica escenarios desde fuera del proceso bajo prueba
└── __main__.py           `python -m simulador_nt8 --entorno=pruebas ...`
```

## Uso

```bash
# arrancar el servidor (una terminal, o como subprocess.Popen desde una prueba)
python -m simulador_nt8 --entorno=pruebas --dir-sockets /tmp/mi_prueba --fichero-info /tmp/info.json

# en el bot / arnés de pruebas
from simulador_nt8.cliente import AdaptadorSimuladorNT8
adaptador = AdaptadorSimuladorNT8("/tmp/mi_prueba/nt8.sock")
adaptador.arrancar()
# a partir de aqui, es un sustituto inyectable de AdaptadorFalso en
# bot/protocolo_dos_patas.py -- misma firma, mismo comportamiento (ver
# verificacion_R3/integracion_proceso_real/prueba_paridad_adaptador_falso.py)

# para fabricar escenarios desde OTRO proceso (solo arneses de prueba, nunca el bot):
from simulador_nt8.cliente_control import ClienteControl
control = ClienteControl("/tmp/mi_prueba/nt8.control.sock")
control.desconecta("MFF-EVAL-1")
control.congelar()
control.retrasar_respuesta("abrir", 31.0)
```

## Dónde está la suite de pruebas

`verificacion_R3/integracion_proceso_real/` — ocho fases en orden estricto de construcción (R3: cada
pieza se corrió contra una reconstrucción deliberadamente rota antes de aceptar la real), cubriendo los
cuatro escenarios que motivaron este simulador: matar el servidor a mitad de una orden, matar el bot con
una posición real abierta y reconciliar al reiniciar, timeouts `N`/`N_hedge` con reloj de pared real, y
el vigía de `09_DESPLIEGUE.md` detectando un proceso realmente detenido (`SIGSTOP`, no cooperativo).
