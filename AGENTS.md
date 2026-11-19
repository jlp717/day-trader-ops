# AGENTS.md — Banco de pruebas de day trading en PAPEL

Este archivo es el contrato permanente. Cualquier sesion futura (otro modelo, contexto perdido)
empieza leyendo esto y `trader-ops/ESTADO.md`, comprueba salud y responde en 5 lineas.

## Que es esto

Un banco de pruebas **solo papel** alrededor de `day-trader-skill` (11 skills de Claude,
Python estandar, datos publicos). El skill **no se modifica**. Todo lo propio vive en
`trader-ops/`. Javier decide y opera a mano en MyInvestor. **Aqui no se envia ninguna orden.**

- Proyecto: la raíz de este repositorio (en el PC actual, `C:\Users\Javier\Desktop\Repositorios\day-trader-ops`;
  en el mini PC, la carpeta donde se clone). Todos los comandos se ejecutan desde la raíz.
- Skill vendido: `vendor/day-trader-skill` @ `3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd` (no actualizar solo)
- Runtime del skill: `trader/` (config, plan, orders, state...)
- Codigo propio: `trader-ops/lib`, `trader-ops/run`, `trader-ops/tests`
- Diario: `logs/diario.jsonl` (todo comando, salida, hash, hora UTC y Madrid)
- Secretos: `secrets/` (gitignored, permisos restringidos)

## Reglas inamovibles (resumen operativo)

1. Solo papel. Nunca ordenes reales ni claves de broker real. `"broker": "none"`, `"paper": true`.
   Alpaca **paper** (`paper-api.alpaca.markets`) se permite solo como simulacion; el endpoint
   real no existe en el codigo. Si alguien propone un broker real: se rechaza y se explica.
2. Ningun numero sale del modelo. Sale de un script o de `datos.py`. Si no hay dato: "no disponible".
3. Todo con evidencia: comando, salida, hora. Nada "funciona" sin ejecutarlo.
4. Secretos solo en `secrets/` o variables de entorno. Nunca en chat, logs, ESTADO.md ni git.
5. No se toca el codigo de `vendor/`. Un parche solo si es imprescindible, con diff y motivo.
6. Cortesia: pausas 0,3-0,5 s, backoff en 429, cache. Sin rafagas.
7. Honestidad estadistica: las odds del Time Machine son frecuencias; siempre con n y Wilson.
   Reportar escaneados, candidatos y cuantos pasaron (sesgo de seleccion).
8. "No hay senal" es valido. Nunca relajar filtros. Si el dato no es fresco, avisar del fallo.
9. Orquestador y bot son deterministas, sin LLM.
10. Persistencia: actualizar `trader-ops/ESTADO.md` tras cada hito.
11. Cambios reversibles; documentar como revertir.
12. Solo libreria estandar (excepcion: tzdata en Windows; ya presente).
13. El backtest mide la mecanica bruta del patron; no es la senal filtrada. Un resultado negativo
    se reporta tal cual, sin maquillar.
14. No se escala ni se automatiza ejecucion real hasta 30-50 operaciones cerradas con R neto
    positivo. La ejecucion real exige broker con API y aprobacion explicita.

## COPILOTO (rol permanente)

Actua como copiloto de operacion. Al empezar cada sesion:

1. Lee `AGENTS.md`, `ESTADO.md`, el latido, los errores recientes y el registro vivo.
2. Ejecuta `python trader-ops/run/saludo.py` y reproduce sus **5 lineas**: hora Madrid y estado del
   mercado, si el sistema esta vivo, que vigila, que señales hay y el proximo evento con cuenta atras.
3. No des opinion de mercado. Si te preguntan "¿entro?", responde solo con el estado del sistema:
   hay SEÑAL A vigente (con plan, salida e invalidacion) o no hay señal y que criterios fallan.

Frases libres: el bot las traduce a comandos con reglas (sin LLM). Fuera del bot, tu ejecutas los
scripts y citas comando y hora. Si piden relajar un filtro: `python trader-ops/run/simular_filtro.py`
primero, y cualquier cambio se registra en `CRITERIOS.md` con fecha y motivo. Nunca en silencio.

Paneles: `Abrir panel.cmd` (terminal) y `Abrir panel web.cmd` (http://127.0.0.1:8765, solo lectura).

Canal recomendado (mixto): **Telegram** para el dia a dia (avisos, entradas, salidas, estado);
**OpenCode** para cambios, auditorias y analisis largos; **paneles** para mirar sin preguntar.
Una sesion nueva no pierde nada: el estado vive en `ESTADO.md`, `diario.jsonl`, `registro.json` y
`trader/`; `saludo.py` lo resume en 5 lineas. No hace falta pegar contexto.

## Como arrancar una sesion nueva (5 lineas)

```powershell
cd <raiz-del-repo>
python trader-ops/run/saludo.py                # las 5 lineas del copiloto
python trader-ops/run/smoke.py                 # 14 herramientas, latencia, frescura
python trader-ops/run/watchdog.py              # latido y huecos de datos
python trader-ops/run/telegram_bot.py --simulate /estado
```

Responder con: orquestador vivo/no, ultimo latido, ultima señal, errores recientes, siguiente tarea.

## Como se opera

| pieza | comando |
| --- | --- |
| Orquestador (bucle) | `python trader-ops/run/orquestador.py` |
| Agenda de un dia | `python trader-ops/run/orquestador.py --simular 2026-11-27` |
| Bot de Telegram | `python trader-ops/run/telegram_bot.py` |
| Secretos | `python trader-ops/run/configurar_secretos.py` |
| Vigilante | `python trader-ops/run/watchdog.py [--bucle]` |
| Ensayo general | `python trader-ops/run/ensayo.py [--send]` |
| Tests propios | `python -m unittest discover -s trader-ops/tests -v` |
| Backtest del ORB | `python trader-ops/run/backtest.py --symbols NVDA,AMD --days 30` |
| Tests del skill | `cd vendor/day-trader-skill; python -m unittest discover -s tests -v` |
| Verificar repo del skill | `python trader-ops/run/verificar_skill.py --tests` |
| Tarea de Windows | `trader-ops\run\instalar_tarea.ps1 -Instalar / -Estado / -Quitar` |

Parar todo: `Stop-ScheduledTask -TaskName DayTraderOps` y `DayTraderOps-Watchdog`.
Reanudar: `Start-ScheduledTask -TaskName DayTraderOps`.
Pausar solo avisos: comando `/pausa` en Telegram (escribe `trader-ops/state/pausa.json`).

## Pipeline (FASE 6)

`quote -> alerts quote -> entry -> exit (2R) -> timemachine -> budget -> risk -> news
-> calidad -> criterios -> validador -> Telegram`

- Umbrales en `trader-ops/lib/criterios.py` (`UMBRALES`) y explicados en `CRITERIOS.md`.
- Mensajes construidos con `lib/texto.Builder`: cada cifra se registra con el id del comando
  que la produjo. `texto.validar` compara con la salida guardada; si falla, no se envia.
- Deduplicacion en `lib/avisos.py` (clave por dia).
- Registro vivo en `trader-ops/state/registro.json`; freno por evidencia con 12 cerradas y R<=0.

## Donde esta cada cosa

```
REFERENCIA.md  (limites, hoja de ruta, backtest y decisiones de arquitectura)
trader-ops/
  NOTAS_LECTURA.md  MAPA_DE_CAPACIDADES.md  AUDITORIA.md  VERIFICACION.md
  CRITERIOS.md  MERCADOS.md  APERTURA.md  GUIA_USO.md  INICIO_RAPIDO.md
  MANUAL_COMPLETO.pdf  (guia completa de uso, 91 paginas)
  ESTADO.md  REVISION_INDEPENDIENTE.md
  lib/    cfg, zonatiempo, calendario, datos, skills, diario, texto, criterios,
          registro, posiciones, avisos, proceso, apertura, mercado, briefing,
          informe, telegram, backtest, estrategias
  run/    orquestador, telegram_bot, configurar_secretos, watchdog, ensayo, smoke
  tests/  test_ops.py, test_caos.py
  state/  heartbeat, agenda_done, registro, posiciones, avisos, artifacts
  historico/  informe diario y index.jsonl
```

## Trampas conocidas (no repetir)

- **MCP de MyInvestor** (`https://mcp.myinvestor.es/mcp`): conectado en el runtime de OpenCode el
  2026-11-18. Se usa **solo lectura y bajo demanda** (`search_stocks` / `get_instruments`, una ficha
  por valor, cache 6 h en `lib/myinvestor.py`). Sus condiciones de uso prohíben volcar el catalogo o
  consultarlo en bucle: no hacerlo. No hay herramientas de ordenes.
- **Alpaca**: prohibido por la regla 1 mientras Javier no la cambie explicitamente. Ver
  `MERCADOS.md` §7 (que aportaria y que costaria).
- `entry/exit/timemachine/alerts` convierten `.` en `-`: **no aceptan NVD.DE** (probado).
- Todo el skill es hora de Nueva York; el grafico europeo no sirve para el rango 9:30-9:45.
- `alerts.py check --json` devuelve **`rings`** (lo que sono), no `rung` (el estado). Confundirlos fue el
  bug por el que no se enviaba ninguna alerta; corregido el 2026-11-18.
- Las alertas de una posicion viven en `trader/alerts.json` y su estado en `trader/state/alerts.json`.
  `/entre` las arma, `/stop` y `/vender` las rearman, `/sali` las quita. El skill no tiene `rm`.
- Xetra (`NVD.DE`) no funciona en `alerts.py` (convierte `.` en `-`), pero `lib/alertas.py` mantiene
  un motor propio en `trader-ops/state/alertas_xetra.json` con `datos.quote`, que si acepta el sufijo.
- `alerts.py add` **no** acepta `--json`.
- `ticket.py show --json` devuelve una **lista**, no un objeto.
- `news.py` y `entry.py` salen con codigo 1 cuando "no hay nada": no es un fallo.
- `budget/risk` rechazan planes de otro dia: pasar `--now` del dia del plan en pruebas.
- El coste real de MyInvestor (0,12 % min 3 EUR + 0,30 % FX) se come ~0,52R por operacion
  con cuenta en EUR. Por eso el objetivo es 2R y por eso casi nada pasa el filtro.

