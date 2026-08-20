<#
    D-A1 -- DIAGNOSTICO COMBINADO (07_ADAPTADOR_NT8.md §8)
    ========================================================
    Fusiona D-A1.0 + D-A1.1 + D-A1.2 en UNA sola ejecucion. Vuelca TODO a un
    fichero de texto con timestamp junto a este script.

    QUE HACE (todo de solo lectura / reflexion -- no manda NINGUNA orden, no
    toca NINGUNA cuenta):
      - D-A1.0: localiza NinjaTrader.Client.dll, su arquitectura (MSIL/x86/
        Amd64), su runtime .NET, y la version de NT8 (del propio fichero y,
        si esta al lado, de NinjaTrader.exe).
      - D-A1.1: vuelca por reflexion TODOS los tipos del ensamblado, localiza
        (por heuristica: la clase con un metodo estatico "SetUp") la clase
        que expone la ATI, lista sus firmas reales, y llama SetUp()/Connected().
      - D-A1.2: si D-A1.1 identifico la clase, suscribe MarketData de MES y
        mide la cadencia real de cambios durante 60 s.
      - D-A1.2b (nuevo, 08_LABORATORIO.md revision 3, DATOS_Y_DASHBOARD.md §1.1):
        intenta determinar si el feed de esta conexion es TIEMPO_REAL o
        RETRASADO -- por heuristica de reflexion, igual que D-A1.1 localiza la
        clase de la ATI, porque no hay confirmado de antemano que metodo
        expone esto (AVISO DE CONFIANZA, ver el bloque). Si no se puede
        determinar por software, la regla de 08_LABORATORIO.md §1.1 es
        DESCONOCIDO = RETRASADO -- nunca asumir tiempo real por defecto.

    QUE NO HACE: D-A1.3 (ciclo de orden en Sim101) y D-A1.4 (minimo contra
    MFF) NO estan aqui a proposito -- son pasos que mandan/cancelan ordenes
    reales y necesitan que los mires en el momento, no un script desatendido.
    Siguen siendo manuales, uno a uno, con la tecnica de precio-lejos-del-
    mercado descrita en 07_ADAPTADOR_NT8.md §8.

    CADA BLOQUE ESTA AISLADO CON try/catch: si algo falla, el fallo se anota
    en el fichero de salida y el script SIGUE con el siguiente bloque -- no
    se pierde lo que ya se consiguio por un fallo posterior ("guarda todo lo
    que se pueda", mismo principio que 08_LABORATORIO.md).

    USO:
        powershell -ExecutionPolicy Bypass -File da1_diagnostico.ps1

    Al terminar, pega el CONTENIDO INTEGRO del fichero de salida (la ruta se
    imprime al final, y aparece también dentro del propio fichero) en la
    sesion de ingenieria. No lo resumas: pégalo entero, incluidos los errores.
#>

$ErrorActionPreference = 'Continue'

$horaInicio = Get-Date
$nombreSalida = "da1_diagnostico_{0:yyyyMMdd_HHmmss}.txt" -f $horaInicio
$rutaSalida = Join-Path $PSScriptRoot $nombreSalida

# Escribe la linea en pantalla Y la anade al fichero de salida de inmediato --
# asi, si el script se interrumpe a media ejecucion (Ctrl+C, timeout largo en
# el muestreo de MarketData), lo ya recogido queda guardado igualmente.
function Anota {
    param([string]$Linea)
    Write-Host $Linea
    Add-Content -Path $rutaSalida -Value $Linea -Encoding UTF8
}
function Seccion {
    param([string]$Titulo)
    Anota ""
    Anota ("=" * 78)
    Anota $Titulo
    Anota ("=" * 78)
}

New-Item -Path $rutaSalida -ItemType File -Force | Out-Null

Seccion "D-A1 DIAGNOSTICO COMBINADO -- $($horaInicio.ToString('yyyy-MM-dd HH:mm:ss'))"
Anota "Maquina: $env:COMPUTERNAME  ·  Usuario: $env:USERNAME"
Anota "PowerShell: $($PSVersionTable.PSVersion)"
Anota "Este proceso de PowerShell es de 64 bits: $([Environment]::Is64BitProcess)"
Anota "El sistema operativo es de 64 bits:       $([Environment]::Is64BitOperatingSystem)"

# =============================================================================
Seccion "D-A1.0 · Localizar la DLL, version de NT8, arquitectura y runtime .NET"
# =============================================================================
$rutasCandidatas = @(
    "C:\Program Files\NinjaTrader 8\bin\NinjaTrader.Client.dll",
    "C:\Program Files (x86)\NinjaTrader 8\bin\NinjaTrader.Client.dll"
)
$rutaDll = $null
foreach ($r in $rutasCandidatas) {
    if (Test-Path $r) {
        Anota "ENCONTRADA: $r"
        try {
            $an = [System.Reflection.AssemblyName]::GetAssemblyName($r)
            Anota "  ProcessorArchitecture: $($an.ProcessorArchitecture)"
        } catch {
            Anota "  ERROR leyendo AssemblyName: $($_.Exception.Message)"
        }
        try {
            $asmRO = [System.Reflection.Assembly]::ReflectionOnlyLoadFrom($r)
            Anota "  ImageRuntimeVersion:   $($asmRO.ImageRuntimeVersion)"
        } catch {
            Anota "  ERROR en ReflectionOnlyLoadFrom: $($_.Exception.Message)"
            Anota "  (si es BadImageFormatException: la bitness de ESTA PowerShell no coincide"
            Anota "   con la DLL -- repite todo el script con la PowerShell de la otra arquitectura:"
            Anota "   32 bits -> %windir%\SysWOW64\WindowsPowerShell\v1.0\powershell.exe)"
        }
        try {
            $vi = (Get-Item $r).VersionInfo
            Anota "  FileVersion:    $($vi.FileVersion)"
            Anota "  ProductVersion: $($vi.ProductVersion)"
            Anota "  ProductName:    $($vi.ProductName)"
        } catch {
            Anota "  ERROR leyendo VersionInfo: $($_.Exception.Message)"
        }
        if (-not $rutaDll) { $rutaDll = $r }
    } else {
        Anota "NO existe: $r"
    }
}

# version de NT8 desde el propio ejecutable, si esta al lado de la DLL que encontramos
foreach ($base in @("C:\Program Files\NinjaTrader 8\bin", "C:\Program Files (x86)\NinjaTrader 8\bin")) {
    $exe = Join-Path $base "NinjaTrader.exe"
    if (Test-Path $exe) {
        try {
            $vi = (Get-Item $exe).VersionInfo
            Anota "NinjaTrader.exe en $exe -> FileVersion $($vi.FileVersion) / ProductVersion $($vi.ProductVersion)"
        } catch {
            Anota "ERROR leyendo version de NinjaTrader.exe en ${exe}: $($_.Exception.Message)"
        }
    }
}

if (-not $rutaDll) {
    Anota ""
    Anota "FALLO: no se encontro NinjaTrader.Client.dll en ninguna ruta candidata."
    Anota "Buscando exhaustivamente en C:\ (puede tardar varios minutos)..."
    try {
        $encontrado = Get-ChildItem C:\ -Recurse -Filter NinjaTrader.Client.dll -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($encontrado) {
            $rutaDll = $encontrado.FullName
            Anota "Encontrada por busqueda exhaustiva: $rutaDll"
        } else {
            Anota "No se encontro NinjaTrader.Client.dll en ningun sitio de C:\."
        }
    } catch {
        Anota "ERROR en la busqueda exhaustiva: $($_.Exception.Message)"
    }
}

# =============================================================================
Seccion "D-A1.1 · Volcado por reflexion + hola-mundo (SetUp / Connected)"
# =============================================================================
$tipoATI = $null
if ($rutaDll) {
    try {
        Add-Type -Path $rutaDll
        Anota "Add-Type -Path '$rutaDll' -> OK"
    } catch {
        Anota "ERROR en Add-Type: $($_.Exception.Message)"
    }
    try {
        $tipos = [System.Reflection.Assembly]::LoadFrom($rutaDll).GetTypes()
        Anota "Tipos del ensamblado ($($tipos.Count) en total):"
        foreach ($t in $tipos) { Anota "  $($t.FullName)" }

        # Heuristica para localizar la clase de la ATI, SIN asumir su nombre:
        # se busca la que expone un metodo estatico publico llamado "SetUp".
        $candidatos = $tipos | Where-Object {
            $_.GetMethods([System.Reflection.BindingFlags]'Public,Static') |
                Where-Object { $_.Name -eq 'SetUp' }
        }
        if ($candidatos.Count -eq 1) {
            $tipoATI = $candidatos[0]
        } elseif ($candidatos.Count -gt 1) {
            Anota ""
            Anota "AVISO: mas de una clase expone un metodo estatico 'SetUp' -- se usa la primera,"
            Anota "revisa a mano cual es la correcta:"
            foreach ($c in $candidatos) { Anota "  candidata: $($c.FullName)" }
            $tipoATI = $candidatos[0]
        }

        if ($tipoATI) {
            Anota ""
            Anota "CLASE DE LA ATI IDENTIFICADA: $($tipoATI.FullName)"
            Anota "Metodos estaticos publicos de esa clase (esta es la firma REAL, no la hipotesis"
            Anota "de 07_ADAPTADOR_NT8.md §3 -- actualiza esa tabla con lo que sale aqui):"
            foreach ($m in $tipoATI.GetMethods([System.Reflection.BindingFlags]'Public,Static')) {
                Anota "  $($m.ToString())"
            }
        } else {
            Anota ""
            Anota "AVISO: ninguna clase del ensamblado expone un metodo estatico llamado 'SetUp'."
            Anota "Revisa a mano la lista de tipos de arriba y busca la que expone Command/MarketData."
        }
    } catch {
        Anota "ERROR listando tipos del ensamblado: $($_.Exception.Message)"
    }
} else {
    Anota "SALTADO: no hay una ruta de DLL valida (ver D-A1.0 arriba)."
}

if ($tipoATI) {
    try {
        $r = $tipoATI::SetUp()
        Anota ""
        Anota "SetUp() -> $r"
    } catch {
        Anota "ERROR llamando SetUp(): $($_.Exception.Message)"
    }
    try {
        $c = $tipoATI::Connected(1)
        Anota "Connected(1) -> $c"
    } catch {
        Anota "ERROR llamando Connected(1) (si la firma real no es Connected(int), ajusta a mano"
        Anota "segun la lista de metodos de arriba y repite esta llamada sola): $($_.Exception.Message)"
    }
} else {
    Anota "SALTADO: SetUp()/Connected() -- no se identifico la clase de la ATI."
}

# =============================================================================
Seccion "D-A1.2 · Frecuencia real de muestreo de MarketData de MES (60 s)"
# =============================================================================
if ($tipoATI) {
    Anota "AVISO: este bloque asume los nombres SubscribeMarketData/MarketData con la firma"
    Anota "hipotetica de 07_ADAPTADOR_NT8.md §3. Si la firma real (ver el volcado de D-A1.1 de"
    Anota "arriba) es distinta, este bloque va a fallar -- pega el error igualmente, es"
    Anota "informacion util, y ajusta el bloque a mano con la firma real."
    Anota ""
    $contrato = "MES 12-26"   # <-- AJUSTAR al codigo de contrato con vencimiento vigente en NT8
    Anota "Contrato usado: $contrato   (AJUSTA esta linea del script si no es el vigente y reejecuta)"
    try {
        $subOk = $tipoATI::SubscribeMarketData($contrato)
        Anota "SubscribeMarketData('$contrato') -> $subOk"

        $muestras = New-Object System.Collections.Generic.List[string]
        $ultimoBid = $null; $ultimoAsk = $null; $ultimoLast = $null
        $fin = (Get-Date).AddSeconds(60)
        while ((Get-Date) -lt $fin) {
            try {
                $bid = $tipoATI::MarketData($contrato, "BID")
                $ask = $tipoATI::MarketData($contrato, "ASK")
                $last = $tipoATI::MarketData($contrato, "LAST")
            } catch {
                Anota "ERROR leyendo MarketData: $($_.Exception.Message)"
                break
            }
            if ($bid -ne $ultimoBid -or $ask -ne $ultimoAsk -or $last -ne $ultimoLast) {
                $ts = Get-Date -Format "HH:mm:ss.fff"
                $muestras.Add("$ts  bid=$bid ask=$ask last=$last")
                $ultimoBid = $bid; $ultimoAsk = $ask; $ultimoLast = $last
            }
            Start-Sleep -Milliseconds 50
        }
        Anota ""
        Anota "Cambios de valor detectados en 60 s: $($muestras.Count)"
        foreach ($m in $muestras) { Anota "  $m" }
        if ($muestras.Count -eq 0) {
            Anota "AVISO: cero cambios en 60 s -- revisa que el codigo de contrato este bien"
            Anota "formado (con el vencimiento correcto) y que el mercado este abierto ahora mismo."
        }
    } catch {
        Anota "ERROR suscribiendo o leyendo MarketData: $($_.Exception.Message)"
    }
} else {
    Anota "SALTADO: no se identifico la clase de la ATI (ver D-A1.1 arriba)."
}

# =============================================================================
Seccion "D-A1.2b · Estado del feed (TIEMPO_REAL / RETRASADO / DESCONOCIDO) -- 08_LABORATORIO.md §1.1"
# =============================================================================
# AVISO DE CONFIANZA (igual que D-A1.1): no hay confirmado por adelantado que
# NinjaTrader.Client.dll exponga un metodo o propiedad que diga directamente
# "esta conexion es tiempo real o retrasada". Este bloque es HEURISTICO: busca,
# entre los miembros de la clase de la ATI ya identificada, cualquiera cuyo
# nombre sugiera esto, e intenta invocar los que no piden argumentos. Si no
# aparece nada convincente, el resultado es DESCONOCIDO -- y 08_LABORATORIO.md
# §1.1 dice que DESCONOCIDO se trata como RETRASADO, nunca como tiempo real.
$estadoFeedDetectado = "DESCONOCIDO"
if ($tipoATI) {
    try {
        $patron = 'Realtime|RealTime|Delayed|MarketDataType|DataType|Connection'
        $miembrosCandidatos = @()
        $miembrosCandidatos += $tipoATI.GetMethods([System.Reflection.BindingFlags]'Public,Static') |
            Where-Object { $_.Name -match $patron }
        $miembrosCandidatos += $tipoATI.GetProperties([System.Reflection.BindingFlags]'Public,Static') |
            Where-Object { $_.Name -match $patron }
        if ($miembrosCandidatos.Count -eq 0) {
            Anota "Ningun miembro estatico de $($tipoATI.FullName) tiene un nombre que sugiera"
            Anota "estado de feed (patron buscado: '$patron')."
            Anota "-> No hay forma automatica de determinarlo con esta DLL. RESULTADO: DESCONOCIDO"
            Anota "   (08_LABORATORIO.md §1.1: DESCONOCIDO se trata como RETRASADO)."
        } else {
            Anota "Miembros candidatos encontrados (nombre sugiere estado de feed):"
            foreach ($m in $miembrosCandidatos) { Anota "  $($m.ToString())" }
            Anota ""
            Anota "Intentando invocar los metodos sin argumentos y leer las propiedades:"
            foreach ($m in $miembrosCandidatos) {
                try {
                    if ($m -is [System.Reflection.MethodInfo] -and $m.GetParameters().Count -eq 0) {
                        $v = $tipoATI::$($m.Name)()
                        Anota "  $($m.Name)() -> $v"
                    } elseif ($m -is [System.Reflection.MethodInfo] -and $m.GetParameters().Count -eq 1) {
                        # hipotesis: recibe el contrato, igual que MarketData($contrato, campo)
                        $v = $tipoATI::$($m.Name)($contrato)
                        Anota "  $($m.Name)('$contrato') -> $v"
                    } elseif ($m -is [System.Reflection.PropertyInfo]) {
                        $v = $tipoATI::$($m.Name)
                        Anota "  $($m.Name) (propiedad) -> $v"
                    } else {
                        Anota "  $($m.Name): firma con mas de 1 argumento, no se adivina -- ajusta a mano."
                    }
                } catch {
                    Anota "  ERROR invocando $($m.Name): $($_.Exception.Message)"
                }
            }
            Anota ""
            Anota "NINGUN valor de arriba se interpreta todavia de forma automatica -- el operador"
            Anota "lee la salida y decide TIEMPO_REAL/RETRASADO/DESCONOCIDO a mano la primera vez;"
            Anota "una vez se sepa cual de estos miembros (si alguno) es fiable, este bloque se"
            Anota "actualiza para decidirlo solo."
        }
    } catch {
        Anota "ERROR buscando miembros de estado de feed: $($_.Exception.Message)"
    }
} else {
    Anota "SALTADO: no se identifico la clase de la ATI (ver D-A1.1 arriba)."
}
Anota ""
Anota "COMPROBACION MANUAL DE RESPALDO (no depende de la ATI ni de este script):"
Anota "en NT8, Control Center -> Connections -> [la conexion] -> Data Series / Instrument,"
Anota "o el dialogo de la cuenta, suele mostrar 'Real-time' vs 'Delayed' por instrumento."
Anota "Si este bloque no dio un resultado convincente arriba, confirma ahi a mano y anota"
Anota "el resultado en 08_LABORATORIO.md §1.1 -- mientras no se confirme, RESULTADO: DESCONOCIDO"
Anota "= tratado como RETRASADO (nunca se asume tiempo real por defecto)."

# =============================================================================
Seccion "FIN"
# =============================================================================
$horaFin = Get-Date
Anota "Duracion total: $([math]::Round(($horaFin - $horaInicio).TotalSeconds, 1)) s"
Anota "Fichero de salida: $rutaSalida"
Anota ""
Anota "Pega el CONTENIDO INTEGRO de este fichero (incluidos los errores, si los hay) en la"
Anota "sesion de ingenieria. No lo resumas: cada linea de error es una comprobacion que D-A1"
Anota "necesita ver fallar o pasar para poder darse por buena (regla R3)."

Write-Host ""
Write-Host "================================================================"
Write-Host "Todo volcado a: $rutaSalida"
Write-Host "================================================================"
