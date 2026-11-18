# NOTAS DE LECTURA — day-trader-skill v2

Lectura completa hecha el **2026-11-18** (Madrid 05:1x–06:3x, Nueva York 23:1x del 17-nov).

- Repo: `https://github.com/Jakeschincariol/day-trader-skill`
- Commit fijado: **`3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd`** (2026-10-20 09:17:50 -0500, "The Trader skill v2: 11 day-trading skills")
- Copia vendida sin modificar en `vendor/day-trader-skill/` (solo lectura).
- Licencia MIT.

## 1. Qué es

11 "skills" de Claude (carpeta + `SKILL.md` + un script Python de librería estándar).
El `SKILL.md` es el prompt/método; el `.py` es la herramienta determinista. En OpenCode
usamos **solo los .py** (ver `MAPA_DE_CAPACIDADES.md` §7 y `AGENTS.md`).

Flujo del README: `scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> broker`,
con `alerts` durante la posición y `news/analyst/pelosi` en paralelo.

## 2. Script por script

### trader-scanner/scan.py (1083 líneas)
Subcomandos: `universe`, `daily`, `orb`.

| arg | efecto |
| --- | --- |
| `universe [--out trader/universe.txt] [--offline DIR] [--no-write] [--pause 0.3] [--json]` | descarga `nasdaqlisted.txt` y `otherlisted.txt` de nasdaqtrader.com y filtra acciones comunes/ordinarias/ADR |
| `daily [--symbols A,B] [--watchlist F] [--universe F] [--limit N] [--min-price 5] [--min-volume 1000000] [--offline P] [--now "YYYY-MM-DD HH:MM"] [--out trader/watchlist.json] [--no-write] [--pause] [--show 50] [--quiet] [--json]` | setups desde cierres diarios (spark, 20 símbolos por petición, 3 meses) |
| `orb [--or-minutes 15] [--max-confirm 200] [--at HH:MM] [--until HH:MM] [--config trader/config.json]` + los comunes | rupturas del rango de apertura en barras de 5 min |

- Lee: `trader/universe.txt`, `trader/config.json` (`no_entries_after`).
- Escribe: `trader/universe.txt`, `trader/watchlist.json`
  (`{created_by, created_at, mode, as_of, universe, scanned, failed, unconfirmed, source, filters, note, hits[]}`).
- `hits[]` daily: `{symbol, setups[], price, close_date, rsi, volume}`.
- `hits[]` orb: `{symbol, setups:["orb"], price, at, bar_start, bar_index, or_high, or_low, pct_over}`.
- Setups: `breakout_20d`, `bull_flag`, `reclaim_ma20`, `oversold`, `oversold_bounce` (solo cierres).
- Límites: `SPARK_MAX=20`, `PAUSE=0.3 s`, `BACKOFF=5 s` (un reintento en 429), `MAX_CONFIRM=200`
  gráficos v8 en la etapa 2, `MIN_DAILY_BARS=30`.
- Ventanas: `OPEN=09:30`, `CLOSE=16:00`, `EARLY=13:00` **hora de Nueva York**, tabla NYSE 2026–2027.
- Salida: texto legible o `--json`. Código 0 si encontró algo, 1 si no o error.

### trader-news/news.py (546)
`--tickers ... [--portfolio] [--watchlist] [--plan] [--state trader/state/news.json] [--hours 48]
[--all] [--forms 8-K] [--no-sec] [--no-moves] [--move-pct 3] [--user-agent] [--config] [--offline DIR]
[--now] [--dry-run] [--json]`
- Fuentes: RSS de titulares Yahoo por ticker, chart Yahoo (precio vs cierre previo), Atom de SEC EDGAR (8-K).
- Escribe `trader/state/news.json` (vistos 30 días + CIK por ticker). Sin UA de SEC omite los filings.
- Marca `MOVING` a partir de `--move-pct` (3 %). Etiquetas: earnings, analyst, legal, deal, capital, people, risk, halt, regulatory, macro.

### trader-entry/entry.py (960)
`check SYMBOL | watch SYMBOL | watchlist`, comunes: `--setup orb|level --or-minutes 15 --interval 5m|1m
--level P --min-volume-x X --side buy --now --offline PATH --config`.
`check` añade `--write [trader/entry.json] --json`; `watch` añade `--every 30 --until HH:MM --out`.
- Regla: primer barrido **cerrado** que cierra por encima del máximo del rango (o del nivel).
- `trader/entry.json`: `{created_by, symbol, setup, side, date, status, time, bar_start, bar_index, price,
  level, interval, opening_range{high,low,minutes}, source, checked_at, reason}`.
- Estados: `triggered`, `waiting`, `expired`, `no-data`. Solo largos.
- Config: `no_entries_before 09:45`, `no_entries_after 15:30` (NY); en cierre anticipado se mueven 3 h.

### trader-exit/exit.py (735)
`plan [--from F] [--symbol S --entry P --or-high P --or-low P] [--or-minutes] [--setup] [--date] [--time]
[--entry-bar] [--interval] [--stop or-mid|or-low|price:X|pct:X|atr:K] [--target 2R|1R|price:X]
[--flat-by HH:MM] [--config] [--offline] [--now] [--write] [--json]` y `show`.
- Escribe `trader/plan.json`: `{symbol, side, date, setup, entry, entry_time, entry_bar, interval,
  opening_range, stop, stop_rule, stop_label, target, target_r, target_label, risk_per_share,
  reward_risk, flat_by, stop_detail, created_at, note}`.
- Aritmética en `Decimal`: stop redondeado **hacia abajo** al centavo, target half-up.
- Rechaza stop ≥ entrada, target ≤ entrada, riesgo < 0,05 % del precio, entrada ≥ flat_by.
- `flat_by` 15:55 NY; en cierre anticipado 12:55.

### trader-timemachine/timemachine.py (956)
`run [--plan F] [--symbol --date --entry --stop --target --entry-time] [--until 15:55] [--replays 10000]
[--seed 19] [--window 2] [--offline] [--now] [--write [trader/timemachine.json]] [--json]` y `chart`.
- Piscina: sesiones **completas** de 78 barras de 5 min (9:30–16:00 NY) de los últimos 60 días.
- 10.000 replay Monte Carlo con `random.Random(seed)`; stop se comprueba antes que target.
- `trader/timemachine.json`: `{plan, mc{...}, history{...}, verdict...}`.
- Mínimo 20 sesiones completas; rechaza entrada fuera de rejilla o no presente.
- Histórico: re-ejecuta la misma regla (rango, stop, R) en cada sesión pasada.

### trader-budget/size.py (881)
`[--budget N] [--limit [PRICE]] [--prices F] [--portfolio F] [--now] [--config] [--plan] [--write [trader/orders.json]] [--json]`
más modo pesos `--weights/--targets/--top/--whole-shares/--cents`.
- Tamaño = mínimo de 4 límites: pérdida máx/riesgo por acción, 75 % del budget/entrada,
  `max_order_usd`/entrada, (budget − colchón)/entrada.
- Escribe UNA orden bracket con forma Alpaca: `{symbol, side, qty, type, time_in_force, order_class,
  take_profit_limit_price, stop_loss_stop_price, why, plan{...}}`.
- Rechaza plan de otro día, blocked, short, riesgo cero, R:R < mínimo.

### trader-risk/check.py (819)
`[--orders F] [--config] [--portfolio] [--prices] [--state trader/state/broker.json] [--now] [--today]
[--out trader/state/risk.json] [--no-write] [--json]`.
- Comprueba formato, activo, cortos, blocked, tamaño, posición, caja, stop obligatorio, pérdida,
  R:R, pérdida diaria, nº de trades, ventana horaria, PDT opcional, duplicados, límite diario.
- Escribe veredictos con huella (fingerprint) de cada orden exacta. Una salida solo se avisa, nunca se bloquea.
- `prices.json` con precio < 15 min puede **elevar** la entrada y reducir el tamaño.

### trader-broker/ticket.py (720)
`show | approve --index N --reply "..." | decline | result --index N --status placed|denied|failed
[--broker-id] [--filled-qty] [--filled-price] [--note] | fill --symbol --side --qty --price | flatten
--symbol [--qty] | log`. **Nunca habla con un broker**: solo renderiza tickets y mantiene
`trader/state/broker.json`. Se puede usar en papel sin credenciales (`show`).

### trader-alerts/alerts.py (787)
`clock | quote [SYMBOLS] [--holdings] [--write] | check | add (--from-plan | --symbol + --stop/--target/
--above/--below/--pct/--at/--opening-bell) | list | reset ID`.
- Fuentes: Yahoo chart v8 y Stooq CSV (`stooq.com`, hoy 404 según el propio SKILL.md).
- Escribe `trader/alerts.json`, `trader/state/alerts.json`, `trader/prices.json`
  (`{as_of, prices{SYM: px}}`).
- Cada regla suena una vez; reglas con `date` solo ese día NY.

### trader-analyst/facts.py (548)
`TICKERS... [--quarters 6] [--no-filings] [--metrics F] [--user-agent] [--config] [--offline DIR] [--json]`.
- SEC XBRL `companyfacts`, `submissions`, índice del 8-K 2.02 y su EX-99.1.
- Exige User-Agent con nombre y email. Escribe `trader/metrics.json` con `--metrics`.
- No trae fechas de resultados: hay que sacarlas de news o de la web de la empresa.

### trader-pelosi/ptr.py (566)
`index [--member X] [--year] [--type P] [--since] [--limit] [--json]`, `new [--state] [--today]
[--dry-run] [--read] [--pdf-dir] [--tickers]`, `fetch DOC_ID`, `parse TEXT --filed`.
- Índice `disclosures-clerk.house.gov/.../<YEAR>FD.zip`, PTRs en PDF.
- `pdftotext` (poppler) opcional vía `subprocess.run([exe,"-layout",pdf,"-"])` — argumentos fijos, sin shell.
- Escribe `trader/state/pelosi.json` y PDFs en `trader/state/ptr-pdfs/`.

## 3. Archivos compartidos en `trader/`

| archivo | lo escribe | lo lee |
| --- | --- | --- |
| `universe.txt` | scan universe | scan daily/orb |
| `watchlist.json` | scan daily/orb | news, entry watchlist |
| `entry.json` | entry --write/watch | exit plan |
| `plan.json` | exit plan --write | timemachine, budget, alerts, risk, ticket |
| `timemachine.json` | timemachine --write | (informativo) |
| `orders.json` | budget --write, ticket flatten | risk, ticket |
| `state/risk.json` | risk check | ticket |
| `state/broker.json` | ticket approve/result/fill | risk (duplicados, trades/día, pérdida diaria) |
| `prices.json` | alerts quote/check | budget, risk |
| `portfolio.json` | ticket fill/result | risk, budget, alerts, news |
| `alerts.json`, `state/alerts.json` | alerts | alerts |
| `state/news.json`, `state/pelosi.json` | news, ptr | news, ptr |
| `config.json` | **nosotros** | scan, entry, exit, risk, budget, ticket, alerts, news, facts |

## 4. Límites por defecto (config.example.json)

`budget 5000`, `cash_buffer_pct 10`, `max_position_pct 75`, `max_order_usd 4000`, `min_order_usd 5`,
`max_loss_per_trade_usd 50`, `max_daily_loss_usd 150`, `max_trades_per_day 3`, `max_orders_per_day 10`,
`min_reward_risk 1.0`, `require_stop true`, `no_entries_before 09:45`, `no_entries_after 15:30`,
`flat_by 15:55`, `fractional false`, `broker alpaca`, `paper true`, `allow_options/margin/short false`,
`pdt_guard false`.

**Nuestro config** (`trader/config.json`): igual pero `max_daily_loss_usd 100`, `broker "none"`,
`sec_user_agent` pendiente de tu nombre/email, `watch ["NVDA"]`, `execution_market "US"`.

## 5. Lo que depende de Claude y cómo se sustituye en OpenCode

| pieza Claude | dependencia | sustituto determinista |
| --- | --- | --- |
| Ejecutar el script correcto con los flags | el modelo lee `${CLAUDE_SKILL_DIR}` y decide | `trader-ops/lib/skills.py` llama a `python <ruta fija> <argv>` con lista de argumentos, timeout y registro |
| Redactar el brief (news, analyst) | el modelo interpreta titulares | `trader-ops/lib/briefing.py` formatea **solo** campos de las salidas JSON; sin prosa generada |
| Decidir "este gráfico me gusta" | el modelo elige | `criterios.py` aplica umbrales numéricos fijos (CRITERIOS.md) |
| `/loop 15m` | bucle del agente | `orquestador.py` con reloj y calendario propios |
| Tarjeta "Allow once" del broker | permiso de Claude | no aplica: **no hay broker**, solo ticket impreso |
| `${CLAUDE_SKILL_DIR}` | variable de Claude | ruta absoluta a `vendor/day-trader-skill/<skill>/` |
| Plugin/marketplace de Claude | `/plugin` | copia de las carpetas a `~/.config/opencode/skills/` (OpenCode) |

Ninguna de estas sustituciones toca el código del skill: se invoca por CLI y se leen sus JSON.

## 6. Observaciones de lectura (no son fallos, son límites)

1. Todo el reloj interno es **Nueva York**: `OPEN/CLOSE/EARLY`, calendario NYSE 2026–2027 y filtros
   `9:30 <= hora ET < 16:00`. Un valor europeo queda fuera por diseño.
2. `to_yahoo()/yahoo_symbol()` convierten `.` en `-` (para `BRK.B`). Eso rompe cualquier sufijo de
   mercado con punto (`NVD.DE` -> `NVD-DE`, que Yahoo no conoce). Probado, ver MAPA §1.
3. Los símbolos con guion (`BRK-B`) se normalizan a punto (`BRK.B`), así que el ida y vuelta funciona
   solo para clases de acción estadounidenses.
4. `daily` usa solo cierres (spark): no hay máximos/mínimos, los setups son "primos" de los del vídeo.
5. `orb` etapa 1 es condición necesaria (cierre ≥ mayor cierre del rango), etapa 2 confirma con
   máximos reales; con más de `--max-confirm` candidatos avisa `PARTIAL`.
6. `timemachine` necesita ≥ 20 sesiones completas y **la barra de entrada dentro de los datos**;
   con la sesión de hoy en curso sirve, con fechas viejas solo vía `--offline`.
7. `risk` cuenta la pérdida **completa** al stop de cada entrada del día, no la pérdida realizada.
8. `ticket.py` no contacta con ningún broker: `show` funciona sin credenciales (requisito del usuario).
9. Los tests (315) son offline con fixtures reales recortadas; `python -m unittest discover -s tests -v`
   pasó entero el 2026-11-18.
