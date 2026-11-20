# Instalar el banco de pruebas en el mini PC

Runbook para dejar el mini PC igual que el PC actual, encendido y funcionando solo.
Tiempo realista: **45–60 minutos**, casi todo instalación de Windows.

Al final hay una lista de comprobación; si algo falla, ve a *Problemas frecuentes* antes de seguir.

---

## 0. Qué se copia y qué no

El repositorio de GitHub lleva **todo el código, la configuración de papel, el manual y los tests**.
No lleva, a propósito:

| No viaja por GitHub | Por qué | Cómo llega al mini PC |
| --- | --- | --- |
| `secrets/` | token del bot y email de la SEC | USB o gestor de contraseñas |
| `logs/` | diario de ejecución, datos personales de uso | no hace falta |
| `trader-ops/state/` | latido, señales y avisos del día | se reconstruye solo |
| `trader-ops/cache/` | respuestas de Yahoo/Telegram | se reconstruye solo |
| `trader/universe.txt`, `watchlist.json` | listas generadas | se regeneran en el premarket |
| `trader-ops/manual/page_*.png` | capturas de revisión del PDF | no hacen falta |

`trader/config.json` **sí** viaja: es la configuración de papel (presupuesto 5.000 USD, riesgo 50 USD
por operación, 150 USD/día, `"paper": true`, `"broker": "none"`).

Comprobación rápida de que no se ha colado nada sensible (se puede repetir cuando quieras):

```powershell
cd C:\day-trader-ops
git ls-files secrets                      # debe salir vacío
git check-ignore -v secrets/telegram.json # debe mostrar la regla del .gitignore
```

No debe aparecer ningún archivo de `secrets/` versionado.

---

## 1. Preparar Windows

### 1.1 Hora y zona horaria

El sistema calcula Madrid ↔ Nueva York con `zoneinfo`; si el reloj está mal, todo cuadra mal.

```powershell
Set-TimeZone -Id "Romance Standard Time"
w32tm /resync
Get-Date
```

Debe salir la hora de Madrid correcta. Si el mini PC tiene la pila agotada, la hora se va al
apagarlo: cámbiala o sincronízala al arrancar.

### 1.2 Energía: que no se duerma nunca

Con el portátil/mini PC **enchufado**:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /change monitor-timeout-ac 10
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
```

- `standby-timeout-ac 0` = nunca suspender enchufado.
- `monitor-timeout-ac 10` = la pantalla se apaga a los 10 min; el PC sigue trabajando.
- `LIDACTION 0` = cerrar la tapa no hace nada (solo si es un portátil).

Comprobar:

```powershell
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
```

Debe mostrar `0x00000000` en *Current AC Power Setting Index*.

### 1.3 BIOS/UEFI: volver a encenderse tras un corte de luz

Entra en la BIOS del mini PC y busca **Restore on AC Power Loss** / **AC Back** / **Power On after
Power Failure** y ponlo en **Power On**. Sin eso, un corte de luz deja el sistema apagado hasta que
alguien pulsa el botón.

### 1.4 Windows Update: que no reinicie en horario de mercado

Configuración → Windows Update → *Horas de actividad*: **12:00–23:00**. Y en *Opciones avanzadas*,
desactiva "Reiniciar lo antes posible cuando sea necesario reiniciar para completar una actualización".

Un reinicio a las 16:00 te deja sin ORB el resto del día.

---

## 2. Instalar Git

Descarga: <https://git-scm.com/download/win> (instalador de 64 bits, opciones por defecto).

Comprobar en una PowerShell **nueva**:

```powershell
git --version
```

### Autenticación con GitHub (el repo es privado)

Opción recomendada, con GitHub CLI:

```powershell
winget install --id GitHub.cli
gh auth login          # GitHub.com → HTTPS → login con navegador
```

Si prefieres no instalar `gh`: crea un **token fine-grained** en GitHub con permiso de lectura sobre
`jlp717/day-trader-ops` y úsalo como contraseña cuando `git clone` la pida.

---

## 3. Instalar Python 3.11

Descarga: <https://www.python.org/downloads/windows/> → *Python 3.11.x* → **Windows installer (64-bit)**.

En la primera pantalla del instalador:

- Marca **Add python.exe to PATH** ← imprescindible.
- Marca **py launcher** (viene marcado).
- Instalación normal, no hace falta "Install for all users".

Comprobar en una PowerShell nueva:

```powershell
python --version        # Python 3.11.x
py -3.11 --version
```

> El script de tareas usa `python` del PATH, no `py`. Si `python --version` no funciona, el paso 6
> fallará con "no se encuentra python".

Instala la única dependencia (zonas horarias; Windows no las trae):

```powershell
py -3.11 -m pip install --user -r C:\day-trader-ops\requirements.txt
```

Comprobación:

```powershell
py -3.11 -c "from zoneinfo import ZoneInfo; import datetime; print(datetime.datetime.now(ZoneInfo('Europe/Madrid')))"
```

Debe imprimir la hora de Madrid con `+01:00` o `+02:00`.

---

## 4. Clonar el proyecto

```powershell
git clone https://github.com/jlp717/day-trader-ops.git C:\day-trader-ops
cd C:\day-trader-ops
git log --oneline -3
```

El repo incluye el skill ya congelado en `vendor/day-trader-skill`; **no hay submódulos** que
inicializar.

Si quieres que la ruta sea idéntica a la del PC actual, usa
`C:\Users\Javier\Desktop\Repositorios\day-trader-ops` en vez de `C:\day-trader-ops`. El código no
depende de la ruta, así que `C:\day-trader-ops` es más corto y más limpio.

---

## 5. Copiar los secretos

En el **PC viejo**, copia a un USB (o al gestor de contraseñas) **solo estos dos archivos**:

```
secrets\telegram.json
secrets\sec.json
```

En el **mini PC**:

```powershell
cd C:\day-trader-ops
New-Item -ItemType Directory -Force secrets | Out-Null
# pega aquí los dos archivos
```

Restringe permisos (solo tu usuario):

```powershell
icacls secrets /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F"
```

Comprobar sin revelar nada:

```powershell
python trader-ops\run\configurar_secretos.py --estado
```

Debe decir que el token es válido, el `@usuario` del bot y el `chat_id` detectado. **Nunca** pegues el
token en un chat, en un issue ni en un commit.

> Si no tienes los archivos a mano, se pueden recrear desde cero con
> `python trader-ops\run\configurar_secretos.py` (pide el token con `getpass`, comprueba contra
> Telegram y espera tu `/start` para detectar el `chat_id`).

---

## 6. Verificar antes de arrancar

En orden. Si un paso falla, para y resuélvelo.

```powershell
cd C:\day-trader-ops

# 1) El skill está completo y sus 315 tests pasan
python trader-ops\run\verificar_skill.py --tests

# 2) Los 92 tests propios
python -m unittest discover -s trader-ops\tests
```

Esperado: `Archivos requeridos: 31 · faltan: 0`, `Ran 315 tests ... OK`,
`Ran 92 tests ... OK (skipped=1)`.

```powershell
# 3) Salud de las 11 herramientas (puede tardar 1-2 min y usa red)
python trader-ops\run\smoke.py
```

Esperado: `14/14` sin fallo inesperado. Con el mercado cerrado, `scanner.orb` puede marcar
"requiere sesión": eso es información, no un error. Si aún no hay email de SEC, `analyst` también
puede salir marcado.

```powershell
# 4) Estado en 5 líneas
python trader-ops\run\saludo.py
```

```powershell
# 5) El bot responde, sin enviar nada a Telegram
python trader-ops\run\telegram_bot.py --simulate /estado
```

Si el paso 5 dice "token inválido" o el 4 se queja de la zona horaria, no sigas al paso 7.

---

## 7. Registrar el arranque automático

Crea **tres** tareas del Programador: orquestador, watchdog y bot. Se lanzan **al iniciar sesión**.

```powershell
powershell -ExecutionPolicy Bypass -File trader-ops\run\instalar_tarea.ps1 -Instalar
powershell -ExecutionPolicy Bypass -File trader-ops\run\instalar_tarea.ps1 -Estado
```

Esperado: `OK DayTraderOps`, `OK DayTraderOps-Watchdog`, `OK DayTraderOps-Bot`, `OK DayTraderOps-PreRadar`, `OK DayTraderOps-PostRadar` y `OK DayTraderOps-Vigia`. Las tres primeras en `Running`; los radares y el vigilante en `Ready` hasta su hora.

Arrancarlas ahora sin reiniciar:

```powershell
Start-ScheduledTask -TaskName DayTraderOps
Start-ScheduledTask -TaskName DayTraderOps-Watchdog
Start-ScheduledTask -TaskName DayTraderOps-Bot
```

Comprobar que hay tres procesos `pythonw`:

```powershell
Get-Process pythonw -ErrorAction SilentlyContinue | Select-Object Id, StartTime, Path
```

### 7.1 Que arranque solo después de un reinicio

Las tareas son **AtLogOn**: si el PC se reinicia y nadie inicia sesión, no arranca nada. Tienes dos
opciones:

1. **Dejar la sesión iniciada** (recomendado si el equipo está en casa): no cierres sesión, solo
   bloquea la pantalla con `Win+L`. Las tareas siguen.
2. **Inicio de sesión automático**: `netplwiz` → desmarca "Los usuarios deben escribir su nombre y
   contraseña" → guarda la contraseña. Cómodo, pero la contraseña queda almacenada en el equipo
   (cualquiera con acceso de administrador puede recuperarla). Es una decisión tuya, no del sistema.

Si eliges la opción 2, comprueba tras un reinicio de prueba que las cinco tareas están en `Running`.

---

## 8. Primer día: lista de comprobación

Antes de las 13:00 (Madrid), con el mercado abierto:

- [ ] `python trader-ops\run\saludo.py` da hora correcta y estado vivo.
- [ ] En Telegram, `/estado` responde en segundos.
- [ ] `/reloj` muestra Madrid y Nueva York con la diferencia correcta (5 o 6 h).
- [ ] A las 13:00 llega el premarket/briefing (scanner + lista ORB).
- [ ] `/hoy` devuelve valores; si no, `/ganadores 5` y `/seguir 5`.
- [ ] `/precios NVDA` devuelve precio con edad del dato (puede avisar de retraso: es normal en Yahoo).
- [ ] A las 15:30 llega el aviso de apertura.
- [ ] A las 21:55 llega el aviso de *flat by close* y a las 22:00 el informe.

Si algo de esto no llega, mira *Problemas frecuentes*.

---

## 9. Un solo bot: parar el PC viejo

Telegram entrega cada mensaje a **una** instancia. Dos PCs con el mismo token = respuestas
intermitentes y confusión.

En el **PC viejo**, antes de dar el mini PC por bueno:

```powershell
Stop-ScheduledTask -TaskName DayTraderOps
Stop-ScheduledTask -TaskName DayTraderOps-Watchdog
Stop-ScheduledTask -TaskName DayTraderOps-Bot
```

Y desactiva el arranque automático para que no vuelvan al reiniciar:

```powershell
powershell -ExecutionPolicy Bypass -File trader-ops\run\instalar_tarea.ps1 -Quitar
```

Eso **no borra nada** del proyecto; solo quita las tareas. El PC viejo queda como copia de consulta.

---

## 10. Actualizar el mini PC cuando cambie el código

En el PC donde edites:

```powershell
git add -A
git commit -m "tipo(scope): cambio"
git push
```

En el mini PC:

```powershell
cd C:\day-trader-ops
git pull
python -m unittest discover -s trader-ops\tests
Stop-ScheduledTask -TaskName DayTraderOps; Start-ScheduledTask -TaskName DayTraderOps
Stop-ScheduledTask -TaskName DayTraderOps-Watchdog; Start-ScheduledTask -TaskName DayTraderOps-Watchdog
Stop-ScheduledTask -TaskName DayTraderOps-Bot; Start-ScheduledTask -TaskName DayTraderOps-Bot
```

No copies carpetas a mano: `secrets/` es lo único que vive fuera de git, y no cambia.

---

## 11. Problemas frecuentes

| Síntoma | Causa habitual | Solución |
| --- | --- | --- |
| `python` no se reconoce | instalado sin "Add to PATH" | reinstalar marcando la casilla, o `py -3.11` y arreglar el PATH |
| `ModuleNotFoundError: tzdata` | falta el paquete | `py -3.11 -m pip install --user tzdata` |
| El bot no responde en Telegram | dos instancias con el mismo token | para las tareas del otro PC; mira `Get-Process pythonw` |
| El bot responde a ratos | PC suspendido o tapa cerrada | revisa el paso 1.2 |
| Las tareas están en `Ready`, no `Running` | nadie ha iniciado sesión | inicia sesión o configura auto-login (7.1) |
| `409 Conflict` en el log del bot | long polling duplicado | igual que "dos instancias" |
| Llega el briefing pero no el ORB | PC dormido entre 13:00 y 15:30 | energía + BIOS |
| Hora desplazada 1 h | zona horaria o `tzdata` viejo | `Set-TimeZone`, `pip install -U tzdata` |
| `smoke.py` con fallos de red | sin internet o Yahoo limitando | repetir en 5 min; no es el sistema |
| Tras actualizar, algo raro | código nuevo sin tests | `git log -1`, `git revert`, reiniciar tareas |

Logs útiles:

```powershell
Get-Content logs\diario.jsonl -Tail 20
Get-ScheduledTaskInfo -TaskName DayTraderOps
python trader-ops\run\watchdog.py
```

---

## 12. Desinstalar y volver atrás

```powershell
# quitar el arranque automático
powershell -ExecutionPolicy Bypass -File trader-ops\run\instalar_tarea.ps1 -Quitar

# volver a una versión anterior del código
cd C:\day-trader-ops
git log --oneline -10
git checkout <commit>
```

Nada de esto toca `secrets/` ni los datos históricos. Para borrar el proyecto entero, elimina
`C:\day-trader-ops` y las cinco tareas; no queda nada en el sistema.
