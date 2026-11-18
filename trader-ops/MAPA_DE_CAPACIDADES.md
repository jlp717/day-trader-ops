# MAPA DE CAPACIDADES — qué puede y qué no puede hacer este skill fuera de Nueva York

Todo lo que sigue está comprobado con el código de
`vendor/day-trader-skill` @ `3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd`
y con ejecuciones reales del 2026-11-18 (Madrid), contra Yahoo en vivo.
Comandos y salidas literales en `VERIFICACION.md`.

## (i) ¿Aceptan las herramientas de un solo valor símbolos de Yahoo no estadounidenses (NVD.DE)?

**No.** El símbolo se transforma antes de pedir el gráfico:

```python
# trader-entry/entry.py:230
def yahoo_symbol(sym):
    return sym.upper().replace(".", "-")
# trader-exit/exit.py:394  y  trader-alerts/alerts.py:201  y  trader-timemachine/timemachine.py:190
```

Ese `replace` existe para `BRK.B -> BRK-B`. Cualquier sufijo de mercado con punto se destroza:
`NVD.DE -> NVD-DE`, que Yahoo no conoce.

Prueba real:

| comando | resultado |
| --- | --- |
| `entry.py check NVD.DE --now "2026-11-17 11:00"` | `Yahoo has no data for NVD.DE: No data found, symbol may be delisted` |
| `entry.py check NVD-DE --now "2026-11-17 11:00"` | idéntico error |
| `alerts.py quote NVD.DE --json` | `{"quotes": {}, "errors": ["Yahoo has no data for NVD.DE: ..."]}` |
| `scan.py daily --symbols NVD.DE,NVDA --no-write --min-volume 0 --json` | `"universe": 2, "scanned": 1, "failed": 1` — solo NVDA |
| `exit.py plan --symbol NVD.DE --entry 139.40 --or-high 140.10 --or-low 138.20` | **sí** devuelve plan (stop 139.15, target 139.65): `exit.py` no valida el símbolo ni pide datos si el stop es `or-mid`/`pct`/`price` |

Matiz importante: `exit.py` **acepta** el símbolo y hace la aritmética, pero es una aritmética sobre
niveles que le hemos dado, no sobre barras del valor. Todo lo que necesita barras
(`entry`, `timemachine`, `alerts quote`, `scan`) falla.

El propio `quote` de Yahoo sí sirve `NVD.DE` (comprobado: 103 barras de 5 min, `GER`, `EUR`, 139,40).
El límite es del skill, no de la fuente.

## (ii) ¿Horario, zona horaria, rango de apertura, calendario y "flat by close" están fijados a Nueva York?

**Sí, todos.** Constantes idénticas repetidas en `scan.py`, `entry.py`, `exit.py`, `timemachine.py`,
`alerts.py`, `check.py`:

```python
OPEN  = datetime.time(9, 30)
CLOSE = datetime.time(16, 0)
EARLY = datetime.time(13, 0)      # cierre anticipado NYSE
NYSE_HOLIDAYS = {...}             # 2026-2027, de nyse.com
NYSE_EARLY_CLOSE = {...}          # 2026-11-27, 2026-12-24, 2027-11-26
```

- `to_eastern()` / `eastern_offset()` calculan el horario de verano **de EE. UU.** (2.º domingo de marzo
  a 1.er domingo de noviembre). No usan `zoneinfo` ni la zona del equipo. Para Madrid eso significa que
  entre el 25-oct y el 1-nov (Europa ya en CET, EE. UU. aún en EDT) la diferencia es de 5 h, no 6.
- `entry.py:451` filtra `if et.date() != day or not (open_dt <= et < close_dt): continue` → **descarta
  toda barra fuera de 9:30–16:00 NY**. Un gráfico europeo se queda sin barras utilizables.
- `scan.py:598` (`session_bars`) hace el mismo filtro para el rango de apertura.
- `timemachine.py:87` `OPEN_MIN=9*60+30`, `CLOSE_MIN=16*60`, `SESSION_BARS=78`.
- `exit.py` `flat_by` por defecto **15:55 NY**; en cierre anticipado NYSE lo mueve a 12:55.
- `--now "YYYY-MM-DD HH:MM"` se interpreta **siempre** como hora de Nueva York (o UTC si acaba en `Z`).
  No hay bandera de zona horaria.
- Calendario: solo festivos NYSE 2026–2027. Fuera de esos años `calendar_known=false` y avisa.
  Los festivos europeos (24-dic XETRA cerrado, 26-dic, etc.) **no existen** para el skill.

Consecuencia práctica: el "rango de apertura" es siempre 9:30–9:45 **de Nueva York**, aunque el valor
cotice en Fráncfort a las 9:00. No es configurable.

## (iii) Setups, qué hace `scan.py daily` y qué ventana usa el Time Machine

**Setups diarios** (solo cierres, sin máximos ni mínimos, del endpoint spark):

| setup | regla exacta (código `find_setups`) |
| --- | --- |
| `breakout_20d` | último cierre > máximo de los 20 cierres anteriores |
| `bull_flag` | `c[-6]/c[-16]-1 > 10 %` y los últimos 5 cierres en un rango < 5 % |
| `reclaim_ma20` | cierre anterior < MA20 anterior y último cierre > MA20 |
| `oversold` | RSI 14 de Wilder < 30 |
| `oversold_bounce` | RSI ayer < 30 y hoy cierra arriba |

**Setup intradía**: `orb`, primer barrido de 5 min **cerrado** por encima del máximo del rango
(`scan.py orb`, `entry.py check --setup orb`), más `level` (cierre por encima de un precio dado).

**`scan.py daily`**: ventana de **3 meses de barras diarias** (`range=3mo&interval=1d`), 20 símbolos por
petición; descarta la barra de hoy hasta el cierre de la sesión NY; exige ≥ 30 cierres;
filtro de liquidez por `regularMarketPrice ≥ 5` y `regularMarketVolume ≥ 1.000.000`;
ordena por precio × volumen. Universo: ~5.900 símbolos (Nasdaq Trader), 298 peticiones, ~145 s con pausa 0,3 s.

**Time Machine**: `range=60d&interval=5m`, una petición. Conserva solo sesiones **completas** de
**78 barras** (9:30–16:00 NY), excluye el día del plan; mínimo **20 sesiones**; 10.000 replays,
`seed 19`. Histórico: la misma regla sobre esas sesiones pasadas.

## (iv) ¿Qué cambia si el mercado no es NYSE?

| pieza | efecto |
| --- | --- |
| `universe` | inútil: solo listas de Nasdaq Trader (EE. UU.) |
| `daily` | funciona con cualquier ticker que Yahoo sirva **sin punto**; con sufijo de mercado falla |
| `orb` / `entry` | **no funciona**: el rango es 9:30–9:45 NY y las barras europeas caen fuera |
| `exit` | funciona si le das entrada y rango a mano (aritmética pura) |
| `timemachine` | **no funciona**: necesita barras en la rejilla 9:30–16:00 NY |
| `alerts` | `quote` falla con sufijo; `clock` responde siempre por NYSE |
| `risk` | ventana horaria y calendario NYSE; un valor europeo se evalúa con reloj americano |
| `flat_by` | 15:55 NY = 21:55 Madrid en invierno, 22:55 en verano: **después del cierre europeo** (17:30) |

Conclusión operativa: **el motor de señales solo es válido para el mercado estadounidense**.
Para el mismo valor en Europa se puede usar el gráfico europeo solo como *ejecución*, nunca para
calcular niveles, salvo que se traduzcan a mano y se marquen (ver `MERCADOS.md`).

## (v) Otras capacidades verificadas

- **Sin broker**: `ticket.py show` renderiza tickets leyendo `trader/orders.json` + `state/risk.json`.
  No hay ninguna llamada de red en `ticket.py` (grep de `urllib` en ese archivo: ninguna).
- **Sin claves**: Yahoo, Nasdaq Trader, SEC y House Clerk son públicos. SEC exige User-Agent con
  nombre y email (`sec_user_agent` o `SEC_USER_AGENT`); sin él, `news.py` omite filings y `facts.py` se niega.
- **Salidas machine-readable**: `--json` en todos los scripts; los archivos de `trader/` son el contrato
  entre pasos. Nuestro orquestador consume **solo** esos JSON, nunca la prosa.
- **Reproducibilidad**: `timemachine --seed 19` da el mismo resultado dos veces (test del repo
  `test_same_seed_same_numbers`, y prueba propia en `VERIFICACION.md`).
- **Cortesía**: pausas de 0,3–0,5 s, un reintento tras 429 con 5 s, `query2 → query1`. Sin ráfagas.
- **Tests**: 315, offline, todos en verde el 2026-11-18.
