# day-trader-ops

Banco de pruebas de **day trading en papel** (simulado) sobre acciones de EE. UU., con datos
públicos, bot de Telegram, paneles locales y un manual de uso. **No hay broker conectado y no se
envía ninguna orden real.** Javier decide y ejecuta a mano en MyInvestor; este sistema solo
confirma o descarta rupturas y deja registro.

> Regla de oro: **sin SEÑAL A no se compra.** La lista de candidatos no es una compra.

## Qué hace

| Hora (Madrid) | Qué ocurre |
| --- | --- |
| 13:00 | scanner diario del universo, noticias, resultados y briefing |
| 15:30 | apertura NYSE: aviso de inicio y alertas de precio |
| 15:50–21:30 | escaneo ORB cada 5 min; si hay ruptura, cadena completa (entrada, salida, Time Machine, tamaño, risk, criterios) |
| 21:55 | aviso de *flat by close* |
| 22:00 | informe del día y silencio hasta mañana |

El sistema **no predice**: espera a que una vela de 5 minutos cierre por encima del máximo del rango
9:30–9:45 ET y entonces filtra. Si nada pasa los filtros, el informe dice cuántos valores se
miraron y por qué se descartaron. No se escanea postmercado, overnight ni BOATS.

## Requisitos

- Windows 10/11 encendido de **13:00 a 22:00** (Madrid) para el ciclo completo.
- **Python 3.11** (probado con 3.11.7) con el lanzador `py`.
- **Git** para clonar y actualizar.
- `tzdata` (paquete de Python; Windows no trae la base de zonas horarias).
- Un bot de Telegram propio y, opcional, un email para la SEC (User-Agent que exige la SEC).

No hace falta nada más: el proyecto usa **solo la biblioteca estándar** de Python. Ni pandas, ni
navegador automatizado, ni base de datos.

## Instalación rápida (mini PC)

Guía detallada, con comprobaciones y problemas frecuentes: **[INSTALACION_MINI_PC.md](INSTALACION_MINI_PC.md)**.

```powershell
# 1. Clonar (repo privado: pide login de GitHub la primera vez)
git clone https://github.com/jlp717/day-trader-ops.git C:\day-trader-ops
cd C:\day-trader-ops

# 2. Dependencia única
py -3.11 -m pip install --user -r requirements.txt

# 3. Secretos: copiar la carpeta secrets\ del PC viejo (USB o gestor de contraseñas)
#    secrets\telegram.json y secrets\sec.json NO están en GitHub, a propósito.

# 4. Verificar antes de arrancar
py -3.11 trader-ops\run\verificar_skill.py --tests
py -3.11 -m unittest discover -s trader-ops\tests
py -3.11 trader-ops\run\smoke.py
py -3.11 trader-ops\run\saludo.py

# 5. Registrar el arranque automático (3 tareas del Programador)
powershell -ExecutionPolicy Bypass -File trader-ops\run\instalar_tarea.ps1 -Instalar
powershell -ExecutionPolicy Bypass -File trader-ops\run\instalar_tarea.ps1 -Estado
```

Si el paso 4 falla, **no sigas**: el sistema no está listo.

## Secretos

| Archivo | Contenido | Dónde vive |
| --- | --- | --- |
| `secrets/telegram.json` | token del bot y `chat_id` | solo en el PC, nunca en git |
| `secrets/sec.json` | nombre y email para el User-Agent de la SEC | solo en el PC, nunca en git |

`secrets/` está en `.gitignore`. Para crearlos desde cero: `py -3.11 trader-ops\run\configurar_secretos.py`
(no muestra el token en pantalla ni lo guarda en el historial). Para comprobar que existen sin
revelarlos: `py -3.11 trader-ops\run\configurar_secretos.py --estado`.

**Un solo bot por token.** Si el PC viejo y el mini PC corren a la vez, Telegram entrega los mensajes
a uno de los dos y parece que el bot "no responde". Para las tareas del PC viejo antes de arrancar
el nuevo:

```powershell
Stop-ScheduledTask -TaskName DayTraderOps
Stop-ScheduledTask -TaskName DayTraderOps-Watchdog
Stop-ScheduledTask -TaskName DayTraderOps-Bot
```

## Uso diario

Por Telegram, con el bot propio: `/estado`, `/hoy`, `/briefing`, `/elegir TICKER`, `/precios TICKER`,
`/posiciones`, `/guia`, `/chuleta`, `/ayuda`. Lista completa en [`trader-ops/GUIA_USO.md`](trader-ops/GUIA_USO.md) y en el
manual.

En el PC:

```powershell
python trader-ops\run\saludo.py      # 5 líneas: hora, mercado, estado, señales, próximo evento
python trader-ops\run\smoke.py       # salud de las 11 herramientas
python trader-ops\run\watchdog.py    # latido y huecos de datos
python trader-ops\run\backtest.py --symbols NVDA,AMD --days 30   # mide el ORB bruto
python trader-ops\run\ml.py --features features.csv --split 0.7   # baseline ML
python trader-ops\run\prepost.py --symbols NVDA,AMD --modo pre    # análisis pre/post
python trader-ops\run\libro.py --symbol NVDA --proveedor alpaca_iex  # top-of-book IEX
python trader-ops\run\orden.py --broker paper --side buy --symbol NVDA --qty 1  # simulacro
```

Paneles locales: `Abrir panel.cmd` (terminal) y `Abrir panel web.cmd` (<http://127.0.0.1:8765>,
solo lectura).

## Estructura

```
AGENTS.md                 contrato permanente del proyecto (leer antes de tocar nada)
REFERENCIA.md             referencia, límites y hoja de ruta (pre/post, Europa, ejecución)
ROADMAP.md                fases: qué está hecho, qué se está haciendo y qué queda
INSTALACION_MINI_PC.md    runbook de instalación en un PC nuevo
trader-ops/
  lib/                    lógica: datos, criterios, plan, riesgo, briefing, Telegram, backtest,
                          brokers, proveedores, ml, prepost
  run/                    ejecutables: orquestador, bot, watchdog, smoke, paneles, backtest,
                          ml, prepost, orden, libro
  tests/                  141 tests propios (+ caos)
  manual/                 fuentes HTML del manual y script que genera el PDF
  MANUAL_COMPLETO.pdf     manual de 91 páginas, para estudiar
  ESTADO.md               estado real, decisiones y pendientes
  GUIA_USO.md             guía rápida de comandos y rutina
trader/config.json        configuración de papel (presupuesto, límites, watchlist)
vendor/day-trader-skill/  skill original congelado en un commit (ver vendor/README.md)
secrets/                  NO versionado
logs/                     NO versionado
```

## Actualizar

```powershell
cd C:\day-trader-ops
git pull
py -3.11 -m unittest discover -s trader-ops\tests
```

Las tareas de Windows leen el código en cada arranque, así que basta con reiniciarlas:

```powershell
Stop-ScheduledTask -TaskName DayTraderOps; Start-ScheduledTask -TaskName DayTraderOps
Stop-ScheduledTask -TaskName DayTraderOps-Watchdog; Start-ScheduledTask -TaskName DayTraderOps-Watchdog
Stop-ScheduledTask -TaskName DayTraderOps-Bot; Start-ScheduledTask -TaskName DayTraderOps-Bot
```

## Parar todo

```powershell
Stop-ScheduledTask -TaskName DayTraderOps
Stop-ScheduledTask -TaskName DayTraderOps-Watchdog
Stop-ScheduledTask -TaskName DayTraderOps-Bot
```

Silenciar solo los avisos sin parar el sistema: `/pausa` y `/reanudar` en Telegram.
Desinstalar el arranque automático (no borra datos): `instalar_tarea.ps1 -Quitar`.

## Aviso

Esto es un **banco de pruebas educativo**. No es asesoramiento financiero, no garantiza resultados
y no ejecuta órdenes. Cualquier operación real es responsabilidad de quien la hace, en su broker y
con su dinero.
