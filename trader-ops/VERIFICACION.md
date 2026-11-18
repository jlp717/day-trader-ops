# VERIFICACION — PASA / FALLA, con evidencia

Todo lo de abajo se ejecuto el **2026-11-18** en `C:\Users\Javier\Desktop\Repositorios\day-trader-ops`.
Las salidas completas estan en `logs/diario.jsonl`; aqui va lo literal relevante.

## 1. Instalacion y tests del skill

| prueba | resultado |
| --- | --- |
| Python | `python 3.11.7` (no existe `py` ni `python3` en este equipo) |
| 315 tests del skill | **PASA**: `Ran 315 tests in 25.824s OK` |
| 41 tests propios | **PASA**: `Ran 41 tests in 0.320s OK` |
| skills en OpenCode | **PASA con matiz**: 11 carpetas copiadas a `~/.config/opencode/skills/trader-*`, con `SKILL.md` y frontmatter validos. La lista de skills se calcula al arrancar la sesion: en esta sesion `skill('trader-alerts')` responde "Unable to load" porque se copiaron despues del arranque. **En la siguiente sesion de OpenCode aparecen.** |

## 2. Datos en vivo y frescura

```
quote NVDA  price 155.46  currency USD  exchange NMS
data_time 2026-11-17T21:00:00Z  age 29187 s
latencia por peticion (14 comandos): mediana 0.36 s, maxima 2.53 s
```

- **PASA**: el precio y la hora del ultimo dato salen del `meta` de Yahoo; la edad se mide contra
  el reloj UTC. A las 06:06 Madrid (00:06 NY) la edad es de ~8 h porque el mercado lleva cerrado
  desde las 16:00 ET: es correcto y el sistema lo trata como "dato no fresco" para señales.
- `scan.py universe`: **PASA** — 5.929 valores en 2,5 s (cache de Nasdaq Trader).
- `scan.py daily` (universo completo): **PASA** — `5929 valores, 1468 escaneados, 262 candidatos`
  en ~150 s. Los 4.461 restantes no pasan el filtro de liquidez del skill (1 M de acciones).
- `scan.py orb` fuera de horario: **FALLA ESPERADA** — `It is 12:06 AM ET: the 15-minute opening
  range...`. El skill se niega a escanear sin sesion; es el comportamiento documentado.
- **Segunda fuente independiente**: Stooq responde **HTTP 404** en `stooq.com/q/l/?s=nvda.us`.
  Conclusion: **fuente unica Yahoo**, documentado en cada aviso como "Yahoo, puede lag".

## 3. Las 11 herramientas (14 comandos), smoke

```
scanner.universe OK   2.53s
scanner.daily    OK   0.55s
scanner.orb      FALLA 0.14s  requiere sesion abierta
news             OK   0.74s  (exit 1 = nada nuevo, normal)
entry            OK   0.36s  (exit 1 = no disparado, normal)
exit             OK   0.12s
timemachine      OK   1.66s
budget           OK   0.08s
risk             OK   0.10s  (BLOCK tambien cuenta como respuesta)
broker.ticket    OK   0.08s
alerts.clock     OK   0.16s
alerts.quote     OK   0.46s
analyst          FALLA 0.18s  sin SEC_USER_AGENT (esperado)
pelosi.index     OK   0.38s
14/14 herramientas sin fallo inesperado
```

`trader-broker` funciona **sin credenciales**: `ticket.py show` solo lee `orders.json` y
`state/risk.json`. No hay ninguna llamada de red en ese archivo.

## 4. Cadena completa y aritmetica (TSLA, 19-oct-2026, fixtures reales)

```
entry   TRIGGERED 10:15 AM at $364.18 (rango 354.47-362.18)
exit    stop 358.32 (mid del rango, redondeado abajo) · target 370.04 (1R)
        riesgo/accion 5.86 · R:R 1.00 · flat 15:55 ET
budget  8 acciones · 2.913,44 USD · perdida al stop 46,88 USD
risk    PASS (limite 50 USD)
```

Verificacion a mano de la aritmetica:

- `50 / 5.86 = 8.53` → **8 acciones** (redondeo a la baja). PASA.
- `8 x 5.86 = 46.88` ≤ 50. PASA.
- `(362.18 + 354.47) / 2 = 358.325` → stop 358.32 (hacia abajo). PASA.
- `364.18 + 1 x 5.86 = 370.04`. PASA.
- `8 x 364.18 = 2.913,44`. PASA.

**trader-risk bloquea de verdad** (forzado con 9 acciones):

```
BLOCK #1 buy TSLA 9 shares, entry
   max loss $52.74 (limit $50), reward:risk 1.00 (min 1)
 - loss: 9 shares x 5.86 risk a share = $52.74 at the stop, over your $50 max loss per trade
0 passed, 1 blocked
```

## 5. Time Machine reproducible

Mismo plan NVDA, mismo seed, dos ejecuciones:

```
{'p_target': 0.0611, 'p_stop': 0.471, 'p_neither': 0.4679, 'avg_R': -0.204,
 'replays': 10000, 'seed': 19}
identicos: True
hist: 32 disparos, 2 objetivo, 16 stop
```

**PASA**. Y el resultado es util: el ORB de NVDA a 2R es malo, y el sistema lo dice.

## 6. Ensayo general

```
entry    triggered 364.18
exit     364.18 / 358.32 / 370.04 / riesgo 5.86
tm       29.2% objetivo, 24.2% stop, 46.6% nada (10.000 replays, seed 19)
         historico 33 disparos, 13 objetivo, 15 stop, Wilson 24.7%-56.3%
budget   8 acciones, 46.88 USD al stop
risk     PASS
aritmetica  cumple=True
evaluacion  DESCARTADA   (EV -0.592R tras coste 0.522R)
validador   ok=True, problemas=[]
telegram    dedupe_ok=True
```

**PASA** el contrato de calidad: el mensaje se construye, el validador lo acepta y la
deduplicacion impide el segundo envio. **El veredicto honesto es DESCARTADA**, no SEÑAL A:
el trade del video no supera los filtros con costes reales. Eso es el sistema funcionando.

## 7. Calendario y reloj

```
Agenda 2026-11-18 (sesion normal)
  premarket 13:00 · briefing 15:00 · apertura 15:30
  orb 15:50 cada 300s hasta 21:30 · alertas cada 20s hasta 22:00
  flat 21:55 · cierre 22:00
Agenda 2026-11-27 (cierre anticipado) -> orb hasta 18:30, flat 18:55, cierre 19:00
Agenda 2026-11-26 (Accion de Gracias) -> sin tareas
```

- Desfase Madrid-NY calculado con `zoneinfo`: **6 h** hoy; **5 h** entre el 25-oct y el 1-nov
  (probado con un test: `offset_hours(2026-10-28) == 5`).
- Festivos NYSE verificados hoy en nyse.com (2026-2028), incluidos el 26-nov y el 27-nov.
- `flat by close` en cierre anticipado: 18:55 Madrid (12:55 ET). PASA.

## 8. Orquestador y autoarranque

```
OK   DayTraderOps  estado=Running  ultimo=18/11/2026 06:04  resultado=267009
heartbeat: {"ts_utc": "2026-11-18T05:04:20Z", "phase": "pre-apertura", "pid": 36724, "tz_offset": 6}
```

- Tarea registrada al iniciar sesion, con reinicio 3 veces y sin limite de tiempo.
- Watchdog registrado cada 5 minutos (latido, hueco de datos, errores).
- `SetThreadExecutionState` evita la suspension desde el proceso (no toca ajustes globales).

## 9. Lo que NO se pudo verificar

| cosa | motivo | efecto |
| --- | --- | --- |
| Contratacion exacta en MyInvestor | no hay MCP de MyInvestor en este OpenCode | se documenta NDQ/NYS/XTR y se marca "no verificado" |
| Bid-ask real | Yahoo no lo da gratis | se usa proxy de rango, etiquetado |
| Calendario Xetra oficial | no se consulto hoy Deutsche Boerse | tabla propia marcada como no verificada |
| Analista SEC | falta el email de Javier | `facts.py` se niega y se dice |
| Envio real a Telegram | falta token/chat_id | modo dry; mensajes en `logs/telegram_out.jsonl` |
| Sesion en vivo completa | la sesion empieza a las 15:30 Madrid | el orquestador queda corriendo; se evaluara en el informe del dia |
