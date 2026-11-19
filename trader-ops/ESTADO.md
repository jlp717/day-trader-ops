# ESTADO — 2026-11-18

## 1. Hecho

| fase | estado | evidencia |
| --- | --- | --- |
| 0 Lectura y mapa | HECHO | `NOTAS_LECTURA.md`, `MAPA_DE_CAPACIDADES.md` (hash `3d0f4ef6...`) |
| 1 Auditoria | PASA | `AUDITORIA.md`: solo Yahoo/Nasdaq/SEC/House Clerk (+stooq sin usar), sin eval/exec/telemetria |
| 2 Instalacion | HECHO | 11 skills en `~/.config/opencode/skills/trader-*`; 315 tests del skill OK; `trader/config.json` |
| 3 Verificacion | HECHO | `VERIFICACION.md`; 14/14 herramientas sin fallo inesperado; ensayo OK |
| 4 Mercados | HECHO | `MERCADOS.md`: NVDA 584x mas liquido que NVD.DE; recomendar EE. UU. |
| 5 Apertura | HECHO | `APERTURA.md`: hueco mediana 0,27 %, 52 % del movimiento en 15 min, ORB paga 1 % mas |
| 6 Motor y criterios | HECHO | `CRITERIOS.md` + `lib/criterios.py`; validador y freno por evidencia |
| 7 Orquestador | HECHO | tarea `DayTraderOps` en ejecucion, latido cada 10 s, agenda calculada |
| 8 Telegram | HECHO | bot con comandos y frases; token/chat_id configurados; mensajes reales enviados |
| 9 Posiciones | HECHO | `/entre`, `/sali`, `/pnl`, deslizamiento, stop peor |
| 10 Resiliencia | HECHO | 92 tests propios + caos; `REVISION_INDEPENDIENTE.md` |
| 11 Evaluacion | HECHO | `lib/informe.py`, `historico/`, resumen diario y semanal |
| 12 Extras | HECHO | CSV, semanal, por setup/hora, Pelosi contexto, datos obsoletos, panel terminal, panel web, simulador de filtros, ganadores y evaluacion bajo demanda |
| 13 Guias | HECHO | `GUIA_USO.md`, `INICIO_RAPIDO.md`, `MANUAL_COMPLETO.pdf` (91 páginas) |
| 14 Vendor repo | HECHO | 31/31 archivos, commit `3d0f4ef6...`, 315 tests del skill OK |
| 15 GitHub + mini PC | HECHO | repo privado `jlp717/day-trader-ops`, 167 archivos, clon limpio verificado (92 + 315 tests); runbook `INSTALACION_MINI_PC.md` |

## 2. Decisiones

- **Objetivo 2R por politica** (no 1R): el coste de ida y vuelta es fijo en dolares y con 1R se
  come la mitad del riesgo. Ver `CRITERIOS.md` §2.
- **Limite diario 150 USD** (elegido por Javier), perdida por operacion 50 USD, cuenta 5.000 USD.
- **Cuenta en EUR** asumida: 0,30 % de cambio por lado. Si hay cuenta en USD, poner
  `"cuenta_eur": false` en `trader/config.json`.
- **Vigilado fijo: NVDA**; el resto sale del scanner.
- **Ejecucion en EE. UU.** (`execution_market: "US"`), Europa solo referencia.
- **Sin broker**: `"broker": "none"`. Se rechazo conectar Alpaca (regla 1).
- **MCP de MyInvestor**: conectado el 18-nov (`https://mcp.myinvestor.es/mcp`, 12 herramientas).
  Verificado en vivo: `NVDA` en XNAS/USD y también NVD.DE/EUR. Uso solo lectura y bajo demanda.
- **SEC**: nombre y email de Javier guardados y probados (`analyst NVDA` devuelve XBRL).
- **GitHub privado** (`jlp717/day-trader-ops`) en vez de público: contiene estrategia y hábitos
  personales. Los secretos no viajan aunque el repo fuera público, pero no hay razón para publicarlo.
- **Vendor como snapshot**, no submódulo: el mini PC se clona en un comando y el skill no cambia
  sin una decisión explícita.

## Pendiente de Javier (10 minutos)

1. **Email para la SEC** — HECHO el 18-nov (nombre + email guardados y probados).
2. **Telegram** — HECHO el 18-nov: token validado, `chat_id` 8886875707, mensajes reales enviados.
3. **Confirmar cuenta EUR/USD** (ahora asumido EUR).
4. **Decidir sobre Alpaca** (ver §7): hoy prohibido por la regla 1.

## 4. Comandos de salud

```powershell
python trader-ops/run/smoke.py
python trader-ops/run/verificar_skill.py --tests
python trader-ops/run/watchdog.py
python trader-ops/run/orquestador.py --simular 2026-11-18
python trader-ops/run/telegram_bot.py --simulate /estado
powershell -File trader-ops/run/instalar_tarea.ps1 -Estado
```

## 5. Registro de esta sesion (2026-11-18, 04:18–07:20 UTC)

- Repo clonado y fijado. 315 tests del skill OK. 52 tests propios OK.
- Probado con datos reales: NVD.DE falla en todas las herramientas de barras (`.` → `-`).
- Ensayo TSLA 19-oct: entrada 364,18 / stop 358,32 / objetivo 370,04 / 8 acciones / 46,88 USD.
  Time Machine 29,2 % objetivo / 24,2 % stop. **Veredicto del motor: DESCARTADA** (EV −0,59R tras
  costes y Wilson por debajo del break-even). Es el resultado correcto: el trade del video no es una ventaja.
- NVDA 2R hoy: objetivo primero 6,1 %, stop 47,1 %, historico 32 disparos / 2 objetivos / 16 stops.
  El ORB de NVDA no pasa el filtro. Se reporta como "sin señal", no se relaja nada.
- Orquestador registrado en el Programador de tareas y arrancado (modo dry hasta que haya token).
- Revision adversarial: los subagentes `security-reviewer` y `verifier` **fallaron por limite de uso**
  de la cuenta. Se sustituyo por 11 pruebas de red team y auto-revision documentada en
  `REVISION_INDEPENDIENTE.md`. Se corrigieron 6 fallos reales (pausa no respetada, mensajes
  programados sin dedupe, argumentos extra ignorados, precios enteros colandose, comision mal
  convertida, corte ORB en cierre anticipado).
- Pendiente de repetir la revision con un subagente cuando haya cupo.

## 5b. Cierre de huecos (2026-11-18, 07:20-07:40 UTC)

Bugs reales encontrados al revisar el uso de extremo a extremo, ya corregidos y con test:

1. `/elegir TICKER` llamaba a `_analisis_natural`, que **no existia**: NameError. Ahora corre la
   cadena completa en sandbox y aplica criterios, sin enviar ni tocar el plan vivo.
2. `orquestador.t_alertas` leia `rung` de la salida de `alerts check`, pero la salida trae `rings`:
   **ninguna alerta se habia enviado nunca**. Corregido.
3. El panel leia el estado de alertas en `trader-ops/state/alerts.json`; el skill escribe en
   `trader/state/alerts.json`. Corregido.
4. `/entre` decia "avisos activados" y **no armaba ninguno**. Ahora arma stop y objetivo con fecha
   de Nueva York, los rearma al mover el nivel y los desarma al cerrar.
5. Cierres **parciales**: `/sali T precio acciones` reduce la posicion, suma el P&L parcial y
   mantiene las alertas del resto.
6. Las alertas se comprobaban cada 20 min; ahora cada 60 s, con aviso de proximidad al 0,5 %.
7. `orb_candidates.json` podia no existir y `t_orb` fallaba cada 5 min; ahora cae a
   `trader/watchlist.json`.
8. `estado_vivo` contaba las operaciones de todo el historico en `trades_today` y no sumaba el
   riesgo de las posiciones manuales. Corregido.
9. `/ganadores`, `/seguir` y `/evaluar` cierran el flujo de ganadores: listar, meter en el escaneo
   ORB del dia y evaluar bajo demanda.
10. Alertas de Xetra (`NVD.DE`): el skill no las admite, asi que `lib/alertas.py` mantiene un motor
    propio en `state/alertas_xetra.json` con `datos.quote`. El panel y `/alertas` muestran las dos.

Evidencia: **92 tests propios OK** (1 skipped); `/elegir NVDA` y `/evaluar 1` ejecutados con datos de
hoy; panel y web renderizados con el desglose de riesgo. **Vendor repo**: 31/31 archivos, commit
`3d0f4ef6...`, **315 tests del skill OK**. **Manual**: 91 páginas con árbol de decisión, guion del día y
día 7 de dos señales.

## 5c. GitHub y mini PC (2026-11-18, 11:30-11:40 UTC)

- Repo **privado** `https://github.com/jlp717/day-trader-ops` (167 archivos, 13 MB con historial).
  Privado porque contiene estrategia, configuración y diario personales; los secretos ni siquiera
  están dentro.
- `secrets/`, `logs/`, `trader-ops/state/`, `trader-ops/cache/` y los PNG de revisión quedan fuera.
  `trader/config.json` sí viaja: es la configuración de papel.
- **Vendor como snapshot plano**: se retiró el `.git` anidado (copia en
  `%TEMP%\opencode\day-trader-skill-git-20261118`) y el hash vive en `vendor/VENDOR_COMMIT`, que lee
  `verificar_skill.py`. Motivo: un solo `git clone`, sin submódulos, y el skill no se mueve solo.
- `verificar_skill.py` ya no confunde el commit del repo padre con el del skill (bug detectado al
  probar el clon limpio).
- `estado_vivo.resumen_5_lineas` mostraba "latido Nones" en una instalación sin latido; ahora dice
  "nunca" y hay test (`test_saludo_sin_latido_no_muestra_none`). Total: **92 tests propios**.
- El aviso de premarket nombraba **toda la watchlist** aunque el titular fuera de un solo valor
  ("Resultados cerca NVDA, MNSO" con una noticia solo de NVDA). Ahora `proceso.simbolos_afectados`
  devuelve los tickers reales del titular.
- **Bug real**: `t_premarket` llamaba a `ganadores.premarket()` sin importar el módulo → `NameError`,
  capturado en silencio. La lista ORB se quedaba **sin los 20 ganadores de ayer** y el mensaje sin
  esa línea. Corregido el import y extraída `_simbolos_orb()` (ganadores primero, sin duplicados,
  techo 150). Lista de hoy regenerada: 20 ganadores + 130 hits. **99 tests propios OK**.
- Runbook de instalación: `INSTALACION_MINI_PC.md`. Verificado sobre un clon real de GitHub:
  99 tests propios OK, 315 del skill OK, `saludo.py` y `telegram_bot.py --simulate /estado` OK.
- **Latencia medida (18/11 15:31 Madrid)**: `/precios NVDA` → 158,75 USD, `data_time`
  14:31:29Z, **edad 2 s**, exchange NMS. Yahoo va en tiempo real para US; la hipótesis de
  15 minutos queda descartada para el feed del sistema.
- **MyInvestor (18/11 15:34)**: ficha de NVDA a **158,59** con Yahoo en **158,75** (0,1 % de
  diferencia). Parecía ir en vivo, pero era **coincidencia**: el precio de premarket estaba cerca
  del vivo. La medición de las 15:50 lo desmiente (siguiente punto).
- **Segundo testigo público verificado (18/11 16:09)**: CNBC
  (`quote.cnbc.com/quote-html-webservice/restQuote/...`) devolvió **154,96** a las 10:09:24 ET
  mientras Yahoo daba **154,95** con edad 1 s. Dos fuentes independientes coinciden al céntimo.
  Sin clave ni login. Candidata a segundo testigo automático; el endpoint es público pero no tiene
  contrato de estabilidad, así que la integración irá con fallback y aviso si falla.
- **MyInvestor ficha vs Yahoo (18/11 15:46)**: ficha a **158,19** mientras Yahoo marcaba **154,44**.
  La vela de 5 min de las 15:35 abrió en 158,15 y cerró en 156,56: 158,19 es el precio de ~15:35.
  **La ficha va ~11 min retrasada**; Yahoo iba en vivo (probado con 6 muestras y precios cambiantes).
  El ticket de ejecución es otro reloj y el **fill** sigue siendo la única verdad para `/entre`.
- **Prueba controlada (18/11 16:20–16:22, misma pantalla, recarga + 1–2 s)**: ficha **155,00** /
  **155,055** / **154,93**; Yahoo en esos minutos **154,91 / 154,75 / 153,87**; CNBC a las 16:22:49
  **153,88**. Las dos fuentes públicas coinciden al céntimo; la ficha va **0–2 min por detrás**.
  El 153,77 de las 16:12:35 (precio de 15:57) era una página que **no se había refrescado de verdad**
  (caché de la SPA), no un retraso fijo de 15 min. La ficha no sirve como reloj: su cadencia de
  actualización no es fiable.
  No se integra la app de MyInvestor: el MCP no expone precio y automatizar la sesión del bróker
  sería frágil, opaco y contrario a la regla 1.
- **Segundo testigo público integrado (18/11 21:20)**: CNBC (`quote_cnbc`) en `lib/datos.py`,
  sin clave. `/precios` muestra Yahoo + CNBC y avisa si difieren >0,5 %. En la señal, el cross-check
  bloquea el envío si la diferencia supera 0,5 %; si CNBC cae, no bloquea. Probado en vivo:
  Yahoo 53,80 / CNBC 53,80 (0,00 %).
- **Comando `/guia`** (también "qué hago ahora"): lee posición, precio, coste, break-even, neto en
  stop/objetivo y fase del día, y devuelve la orden exacta en cada escenario. Los avisos de
  stop/objetivo y el flat añaden la acción concreta y remiten a `/guia`.
- **Mensaje de SEÑAL A operativo (19/11)**: incluye veredicto "COMPRAR" con rango válido
  (stop–stop+0,5R), orden exacta en MyInvestor (limitada, cantidad ajustada al límite para no
  pasar del riesgo máximo), `/entre` con `[fill]`, stop-loss y venta limitada opcionales, salidas
  por stop/objetivo/21:55 y lista de lo que no hacer. Longitud ~2.000 caracteres; test que valida
  HTML y trazabilidad. 113 tests propios OK.
- **Tercer testigo opcional Finnhub** (18/11 21:53): `quote_finnhub` lee `secrets/finnhub.json`
  (`{"api_key": "..."}`) o `FINNHUB_KEY`; plan free con cotización US en tiempo real (feed IEX,
  60/min). `/precios` lo muestra si hay clave; `cross_check` compara Yahoo, CNBC y Finnhub y
  bloquea si el rango supera 0,5 %. Sin clave no se usa y no bloquea. 113 tests propios OK.
- **Manual 91 páginas**: nueva §0.6 "Los comandos, explicados como a un niño" con el desglose de
  `/entre`, `/sali`, `/stop`, `/vender`, `/guia` y el ejemplo CRCL con costes; aviso al inicio de
  los días simulados.
- **Bot caído ~21:19–21:41**: la tarea `DayTraderOps-Bot` quedó en `Ready` con resultado 1 tras el
  reinicio (carrera con la instancia anterior). Reiniciada a las 21:41 (PID 38844). Si `/guia` no
  responde, comprobar `Get-ScheduledTask -TaskName DayTraderOps-Bot`.
- **Causa real del silencio de `/guia` (21:42)**: el comando se ejecutó, pero Telegram rechazó el
  mensaje con **HTTP 400** porque el texto llevaba `<fill>` (etiqueta HTML inválida) y `P&L`
  (ampersand sin escapar). El proceso murió. Corregido a `[fill]` y `PnL` en bot, orquestador e
  informe; test que prohíbe `<fill>` y `&` en `/guia`. Enviado el `/guia` real a las 21:46: OK.
- **Falso positivo del vigilante**: a las 15:34 avisó "sin pasada del scanner desde hace 152 min"
  porque contaba la ventana de sesión completa (15:30-22:00) y el ORB no empieza hasta las 15:50.
  Ahora solo comprueba entre la primera pasada y el corte de entradas. 110 tests propios OK.

## 6. Cambios de ultima hora (reversibles)

- `orquestador.t_orb` escribe los hits ORB en `state/orb.json` y **no** pisa `trader/watchlist.json`
  (asi la lista de candidatos del premarket dura toda la sesion).
- Mensajes programados con `avisos.send_once` (clave por dia): si se corrompe `agenda_done.json`
  no se reenvian.
- `/pausa` ahora si detiene las SEÑAL A (`orquestador.pausado()`).

