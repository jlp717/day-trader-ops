# Ventana grafica para configurar el bot de Telegram sin teclear en la consola.
# Boton "Pegar del portapapeles" -> "Guardar" -> "Esperar /start".
# El token no se imprime, no se pasa por argumentos y no queda en el repositorio.
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
$script = Join-Path $root "trader-ops\run\configurar_secretos.py"
$py = (Get-Command python).Source

$form = New-Object System.Windows.Forms.Form
$form.Text = "Day Trader PAPEL - bot de Telegram"
$form.Size = New-Object System.Drawing.Size(560, 330)
$form.StartPosition = "CenterScreen"
$form.TopMost = $true

$titulo = New-Object System.Windows.Forms.Label
$titulo.Text = "Pega el token de @BotFather"
$titulo.Font = New-Object System.Drawing.Font("Segoe UI", 12, [System.Drawing.FontStyle]::Bold)
$titulo.SetBounds(20, 15, 500, 25)
$form.Controls.Add($titulo)

$ayuda = New-Object System.Windows.Forms.Label
$ayuda.Text = "Telegram -> @BotFather -> /newbot -> copia el token (123456789:AAH...).`nCopia el token y pulsa 'Pegar del portapapeles'. No se vera en pantalla."
$ayuda.SetBounds(20, 45, 510, 45)
$form.Controls.Add($ayuda)

$txt = New-Object System.Windows.Forms.TextBox
$txt.SetBounds(20, 95, 500, 25)
$txt.UseSystemPasswordChar = $true
$form.Controls.Add($txt)

$btnPegar = New-Object System.Windows.Forms.Button
$btnPegar.Text = "Pegar del portapapeles"
$btnPegar.SetBounds(20, 130, 180, 30)
$btnPegar.Add_Click({
    try { $txt.Text = (Get-Clipboard -Raw).Trim() } catch { }
})
$form.Controls.Add($btnPegar)

$btnGuardar = New-Object System.Windows.Forms.Button
$btnGuardar.Text = "Guardar y validar"
$btnGuardar.SetBounds(210, 130, 150, 30)
$btnGuardar.Add_Click({
    $t = $txt.Text.Trim()
    if (-not $t) { $lbl.Text = "Pega el token primero."; $lbl.ForeColor = "DarkRed"; return }
    $env:TG_TOKEN = $t
    $out = & $py $script --solo-guardar 2>&1 | Out-String
    Remove-Item Env:TG_TOKEN -ErrorAction SilentlyContinue
    if ($out -match "TOKEN_OK (@\S+)") {
        $lbl.Text = "Token valido para $($Matches[1]). Ahora pulsa 'Esperar /start'."
        $lbl.ForeColor = "DarkGreen"
        $btnEsperar.Enabled = $true
    } elseif ($out -match "TOKEN_RECHAZADO (.*)") {
        $lbl.Text = "Telegram rechaza el token: $($Matches[1])"
        $lbl.ForeColor = "DarkRed"
    } else {
        $lbl.Text = "Token con formato invalido. Copia el de @BotFather entero."
        $lbl.ForeColor = "DarkRed"
    }
})
$form.Controls.Add($btnGuardar)

$btnEsperar = New-Object System.Windows.Forms.Button
$btnEsperar.Text = "Esperar /start"
$btnEsperar.SetBounds(370, 130, 150, 30)
$btnEsperar.Enabled = $false
$btnEsperar.Add_Click({
    Start-Process powershell -ArgumentList '-NoExit','-ExecutionPolicy','Bypass','-Command',
        "Set-Location '$root'; python '$script' --detectar --minutos 10"
    $lbl.Text = "Se ha abierto otra ventana esperando tu /start. Enviame /start en Telegram."
    $lbl.ForeColor = "DarkBlue"
})
$form.Controls.Add($btnEsperar)

$btnFather = New-Object System.Windows.Forms.Button
$btnFather.Text = "Abrir @BotFather"
$btnFather.SetBounds(20, 175, 150, 28)
$btnFather.Add_Click({ Start-Process "https://t.me/BotFather" })
$form.Controls.Add($btnFather)

$lbl = New-Object System.Windows.Forms.Label
$lbl.SetBounds(20, 215, 500, 60)
$lbl.Text = "1) Copia el token  2) Pegar  3) Guardar  4) Esperar /start y enviarlo en Telegram"
$form.Controls.Add($lbl)

[void]$form.ShowDialog()
