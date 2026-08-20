<#
.SYNOPSIS
    watchdog_bot.ps1 -- 09_DESPLIEGUE.md §1.3

    Comprueba `latido.json` (que el bucle principal del bot, D8, escribe cada
    pocos segundos mientras esta vivo Y avanzando -- ver 09_DESPLIEGUE.md §1.1).
    Si el latido esta ausente o rancio, reinicia el proceso del bot; si los
    reinicios se repiten en poco tiempo, deja de reintentar y solo alerta --
    reiniciar en bucle contra un fallo estructural es peor que pararse.

.AVISO DE HONESTIDAD (mismo que da1_diagnostico.ps1, 07_ADAPTADOR_NT8.md §8)
    Revisado a mano -- llaves/parentesis balanceados, logica trazada linea por
    linea contra la tabla de 09_DESPLIEGUE.md §1.2 -- pero NO se ha podido
    ejecutar contra un Task Scheduler real ni contra un proceso de bot real:
    este entorno de ingenieria es Linux, sin PowerShell ni Windows Task
    Scheduler. La primera vez que corra de verdad es una comprobacion R3 mas
    que hay que ver pasar (o fallar y corregir) con la salida pegada -- forzar
    un latido rancio a mano (parar el bot, o no escribir latido.json) y
    confirmar que esto lo detecta, alerta, y reinicia, antes de confiar en
    ello con dinero real.
#>

param(
    [string]$RutaBot        = "C:\ruta\al\bot",                       # AJUSTAR
    [string]$ComandoArranque = "python bot\main.py",                  # AJUSTAR -- D8 no existe todavia
    [string]$FicheroLatido  = "$RutaBot\latido.json",
    [string]$FicheroReinicios = "$RutaBot\watchdog_reinicios.json",
    # Los dos valores de abajo viven en 03_CONFIG.yaml -> adaptador.latido_intervalo_s /
    # adaptador.latido_rancio_umbral_s (movidos ahi 20-08-2026, 10_SEGURIDAD.md §1: "es un
    # parametro de RIESGO, no de operacion... cumple la misma funcion que N/N_hedge"). PowerShell
    # no tiene un parser de YAML sin una libreria externa, asi que estos DEFAULTS son una copia
    # literal del valor de config -- si 03_CONFIG.yaml cambia, este script se actualiza a mano
    # (mismo aviso que arriesga cualquier valor duplicado fuera de su unica fuente; R2 exige que
    # la fuente sea 03_CONFIG.yaml, no que sea imposible copiarlo a un sitio que no puede leerlo).
    [double]$LatidoIntervaloS = 30.0,                    # = adaptador.latido_intervalo_s
    [double]$LatidoRancioUmbralS = 90.0,                 # = adaptador.latido_rancio_umbral_s
    [int]$VentanaReiniciosMin = 15,                      # 10_SEGURIDAD.md §5: punto de partida del
    [int]$MaxReiniciosEnVentana = 3                      # operador, pendiente de afinar en papel
)

function Escribe-Log($mensaje, $prioridad = "INFO") {
    $ts = (Get-Date).ToString("o")
    $linea = "[$ts] [$prioridad] $mensaje"
    Write-Output $linea
    # 09_DESPLIEGUE.md §1.2: "misma canal que las alertas del propio bot" --
    # AJUSTAR al mecanismo de alerta real cuando exista (correo, Slack, lo que
    # decida el operador). Aqui, de momento, solo el log de la propia tarea.
    Add-Content -Path "$RutaBot\watchdog_log.txt" -Value $linea
}

function Lee-Json-Seguro($ruta) {
    if (-not (Test-Path $ruta)) { return $null }
    try {
        return Get-Content -Raw -Path $ruta | ConvertFrom-Json
    } catch {
        # fichero a medio escribir o corrupto -- tratar como "sin latido",
        # nunca como "todo bien" (mismo principio de R7: ante la duda, no se
        # asume que esta sano)
        Escribe-Log "latido.json no se pudo leer/parsear: $_" "AVISO"
        return $null
    }
}

function Escribe-Json-Atomico($ruta, $objeto) {
    # mismo patron que bot/estado.py::guardar() -- fichero temporal + rename,
    # nunca se deja un fichero de control a medio escribir.
    $tmp = "$ruta.tmp"
    $objeto | ConvertTo-Json -Depth 5 | Set-Content -Path $tmp -Encoding UTF8
    Move-Item -Path $tmp -Destination $ruta -Force
}

function Cuenta-Reinicios-Recientes {
    $reg = Lee-Json-Seguro $FicheroReinicios
    if ($null -eq $reg) { return @() }
    $limite = (Get-Date).AddMinutes(-$VentanaReiniciosMin)
    return @($reg.reinicios | Where-Object { [DateTime]$_.ts -gt $limite })
}

function Registra-Reinicio {
    $recientes = Cuenta-Reinicios-Recientes
    $recientes += [PSCustomObject]@{ ts = (Get-Date).ToString("o") }
    Escribe-Json-Atomico $FicheroReinicios ([PSCustomObject]@{ reinicios = $recientes })
    return $recientes.Count
}

# --- 1. leer latido.json y calcular su edad -----------------------------
$latido = Lee-Json-Seguro $FicheroLatido
$rancio = $true
if ($null -ne $latido -and $latido.ts_iso) {
    $edad = ((Get-Date) - [DateTime]$latido.ts_iso).TotalSeconds
    $rancio = $edad -gt $LatidoRancioUmbralS
    if (-not $rancio) {
        Escribe-Log "latido OK (edad ${edad}s, fase=$($latido.fase))" "INFO"
        exit 0
    }
    Escribe-Log "latido RANCIO (edad ${edad}s > umbral ${LatidoRancioUmbralS}s)" "CRITICO"
} else {
    Escribe-Log "latido.json ausente o sin ts_iso -- tratado como proceso muerto" "CRITICO"
}

# --- 2. decidir: reiniciar, o dejar de intentar y solo alertar -----------
$numReiniciosRecientes = Registra-Reinicio
if ($numReiniciosRecientes -gt $MaxReiniciosEnVentana) {
    Escribe-Log ("$numReiniciosRecientes reinicios en los ultimos $VentanaReiniciosMin min -- " +
                 "ALERTA MAXIMA, NO se reinicia mas: el fallo es estructural, no un cuelgue " +
                 "transitorio (09_DESPLIEGUE.md §1.2). Intervencion humana explicita requerida.") "ALERTA_MAXIMA"
    exit 1
}

# --- 3. reiniciar el proceso ----------------------------------------------
# 09_DESPLIEGUE.md §1.2: reiniciar es seguro PORQUE el propio bot, al
# arrancar, se reconcilia solo contra estado.json (07_ADAPTADOR_NT8.md §6) --
# el watchdog no necesita saber nada de patas ni posiciones.
Escribe-Log "reiniciando el proceso del bot (intento $numReiniciosRecientes de $MaxReiniciosEnVentana en esta ventana)" "ALERTA"
Get-Process | Where-Object { $_.Path -like "*$ComandoArranque*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile -Command `"cd '$RutaBot'; $ComandoArranque`"" `
    -WorkingDirectory $RutaBot
Escribe-Log "proceso relanzado -- sigue la reconciliacion de 07_ADAPTADOR_NT8.md §6 al arrancar" "INFO"
