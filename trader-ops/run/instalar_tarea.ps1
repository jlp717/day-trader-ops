# Registra el banco de pruebas en el Programador de tareas de Windows.
#   .\instalar_tarea.ps1 -Instalar     crea las tareas (orquestador + vigilante)
#   .\instalar_tarea.ps1 -Estado       muestra si existen
#   .\instalar_tarea.ps1 -Quitar       las borra (reversible)
#
# No toca ajustes globales del sistema: solo crea dos tareas del usuario.
param(
    [switch]$Instalar,
    [switch]$Quitar,
    [switch]$Estado
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$py = (Get-Command python).Source
$pyw = Join-Path (Split-Path -Parent $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }
$orch = Join-Path $root "trader-ops\run\orquestador.py"
$dog = Join-Path $root "trader-ops\run\watchdog.py"

function Get-Task($name) { Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue }

if ($Estado) {
    foreach ($n in @("DayTraderOps", "DayTraderOps-Watchdog", "DayTraderOps-Bot", "DayTraderOps-PreRadar", "DayTraderOps-PostRadar", "DayTraderOps-Vigia")) {
        $t = Get-Task $n
        if ($t) {
            $i = Get-ScheduledTaskInfo -TaskName $n
            "OK   $n  estado=$($t.State)  ultimo=$($i.LastRunTime)  resultado=$($i.LastTaskResult)"
        } else { "NO   $n" }
    }
    exit 0
}

if ($Quitar) {
    foreach ($n in @("DayTraderOps", "DayTraderOps-Watchdog", "DayTraderOps-Bot", "DayTraderOps-PreRadar", "DayTraderOps-PostRadar", "DayTraderOps-Vigia")) {
        if (Get-Task $n) { Unregister-ScheduledTask -TaskName $n -Confirm:$false; "Borrada $n" }
    }
    exit 0
}

if (-not $Instalar) {
    "Uso: .\instalar_tarea.ps1 -Instalar | -Estado | -Quitar"
    exit 1
}

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

$action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$orch`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName "DayTraderOps" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Banco de pruebas day trading en papel (orquestador)" -Force | Out-Null
"Registrada DayTraderOps (al iniciar sesion, reinicio 3 veces)"

$action2 = New-ScheduledTaskAction -Execute $pyw -Argument "`"$dog`" --bucle --cada 300" -WorkingDirectory $root
$trigger2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName "DayTraderOps-Watchdog" -Action $action2 -Trigger $trigger2 `
    -Settings $settings -Description "Vigilante del banco de pruebas" -Force | Out-Null
"Registrado DayTraderOps-Watchdog (cada 5 minutos)"

$botpy = Join-Path $root "trader-ops\run\telegram_bot.py"
$action3 = New-ScheduledTaskAction -Execute $pyw -Argument "`"$botpy`"" -WorkingDirectory $root
$trigger3 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName "DayTraderOps-Bot" -Action $action3 -Trigger $trigger3 `
    -Settings $settings -Description "Bot de Telegram del banco de pruebas" -Force | Out-Null
"Registrado DayTraderOps-Bot (long polling)"

$radar = Join-Path $root "trader-ops\run\prepost.py"
$action4 = New-ScheduledTaskAction -Execute $pyw -Argument "`"$radar`" --radar --top 30 --modo pre --send" -WorkingDirectory $root
$trigger4 = New-ScheduledTaskTrigger -Daily -At "13:10"
Register-ScheduledTask -TaskName "DayTraderOps-PreRadar" -Action $action4 -Trigger $trigger4 `
    -Settings $settings -Description "Radar premarket (solo analisis)" -Force | Out-Null
"Registrado DayTraderOps-PreRadar (13:10 diario)"

$action5 = New-ScheduledTaskAction -Execute $pyw -Argument "`"$radar`" --radar --top 30 --modo post --send" -WorkingDirectory $root
$trigger5 = New-ScheduledTaskTrigger -Daily -At "22:05"
Register-ScheduledTask -TaskName "DayTraderOps-PostRadar" -Action $action5 -Trigger $trigger5 `
    -Settings $settings -Description "Radar postmarket (solo analisis)" -Force | Out-Null
"Registrado DayTraderOps-PostRadar (22:05 diario)"

$vigia = Join-Path $root "trader-ops\run\vigia.py"
$action6 = New-ScheduledTaskAction -Execute $pyw -Argument "`"$vigia`" --cada 30 --send" -WorkingDirectory $root
$trigger6 = New-ScheduledTaskTrigger -Daily -At "15:25"
Register-ScheduledTask -TaskName "DayTraderOps-Vigia" -Action $action6 -Trigger $trigger6 `
    -Settings $settings -Description "Vigilante rapido de niveles (30 s, hasta el cierre)" -Force | Out-Null
"Registrado DayTraderOps-Vigia (15:25 diario, se cierra solo al cierre)"

"Para arrancarlo ahora sin reiniciar:"
"  Start-ScheduledTask -TaskName DayTraderOps"
"Para pararlo:"
"  Stop-ScheduledTask -TaskName DayTraderOps"
