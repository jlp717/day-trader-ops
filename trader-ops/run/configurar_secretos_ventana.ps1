# Ventana guiada para configurar los secretos sin pasar nada por el chat.
# La lanza OpenCode; Javier escribe el token y su email aqui, no en el chat.
chcp 65001 > $null
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Day Trader PAPEL - configurar secretos"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  CONFIGURACION - banco de pruebas en papel" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "PASO 1. Token del bot de Telegram." -ForegroundColor Yellow
Write-Host "  - Si no tienes bot: Telegram -> @BotFather -> /newbot."
Write-Host "  - Copia el token (123456789:AAH...)."
Write-Host "  - Para pegarlo aqui: CLIC DERECHO del raton en esta ventana."
Write-Host "  - No se vera al pegar. Pulsa Enter."
Write-Host ""
Write-Host "PASO 2. Tu nombre y email para la SEC (la SEC lo exige)." -ForegroundColor Yellow
Write-Host ""
Write-Host "PASO 3. Cuando el script lo pida, abre tu bot en Telegram y enviale /start." -ForegroundColor Yellow
Write-Host ""
Write-Host "Nada de esto se guarda en el chat ni en el repositorio: va a secrets\." -ForegroundColor Green
Write-Host ""

python trader-ops\run\configurar_secretos.py

Write-Host ""
Write-Host "Si algo ha fallado, puedes repetir solo la deteccion del chat con:" -ForegroundColor Green
Write-Host "  python trader-ops\run\configurar_secretos.py --detectar"
Write-Host ""
Read-Host "Pulsa Enter para cerrar"
