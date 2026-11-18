# GUIA DE USO

**Manual completo en PDF**: `C:\Users\Javier\Desktop\Repositorios\day-trader-ops\trader-ops\MANUAL_COMPLETO.pdf`
(91 páginas: ruta de aprendizaje, comandos, rutina, datos gratis, ejecución, nueve días de ejemplo, salidas exactas, Telegram, Xetra, BOATS y solución de problemas).

## 1. Qué ocurre cada día sin que hagas nada

El orquestador arranca solo al iniciar sesión (tarea `DayTraderOps`) y decide cada día si hay mercado
con el calendario NYSE. En un día normal (hora de Madrid):

| Hora | Qué pasa |
| --- | --- |
| 13:00 | Premarket: scanner, noticias, resultados, ganadores y Pelosi. |
| 15:00 | Briefing: candidatos, coste de esperar y plan condicional. |
| 15:30 | Abre NYSE; se forma el rango 9:30–9:45 ET. |
| 15:50–21:30 | Escaneo ORB cada 5 min; solo si pasa todo llega una SEÑAL A. |
| 21:30 | Última entrada (15:30 ET). |
| 21:55 | Flat by close: se cierra todo. |
| 22:00 | Informe del día y silencio hasta mañana. |

En cierre anticipado (27-nov, 24-dic) todo se adelanta 3 horas: flat 18:55, cierre 19:00.
En festivo no hay nada.

**Si no hay señal, no se inventa nada.** El informe dice cuántos valores se analizaron, cuántos
fueron candidatos y por qué se descartaron.

## 2. Comandos de Telegram

| Comando | Qué devuelve |
| --- | --- |
| `/ahora` | Fase del día, qué hace el sistema, qué haces tú, próximo evento y cuenta atrás. |
| `/estado` | Orquestador vivo, latido, pausa, registro, posiciones, freno y hora Madrid/NY. |
| `/reloj` | Hora Madrid/NY, desfase real, sesión de hoy y siguiente. |
| `/hoy` | Tabla del día: candidatos antes de abrir; rupturas del rango después. |
| `/briefing` | Briefing previo completo. |
| `/resumen` | Qué hay que hacer hoy en lenguaje llano. |
| `/explica [T]` | Traduce la última evaluación a lenguaje llano. |
| `/porque [T]` | Por qué no hay señales (o por qué se descartó un valor). |
| `/descartadas` | Evaluaciones de hoy que no fueron SEÑAL A. |
| `/registro` | Registro vivo de señales con R. |
| `/ticker T` | Resumen de la cadena: setup, plan, TM, tamaño, risk, noticias. |
| `/elegir T` o `/elegir N` | Análisis completo con criterios, SEC y veredicto. |
| `/evaluar [N]` | Cadena completa de los N ganadores (máx. 5) y ranking. |
| `/ganadores [N]` | Los que más suben, con filtro de liquidez. |
| `/seguir [N]` | Añade los N primeros de `/ganadores` a la lista ORB de hoy. |
| `/incluir T` | Añade un ticker concreto (p. ej. MNSO) a la lista ORB de hoy. No es una compra. |
| `/plan T` | Plan de salida si hay disparo. |
| `/tm T` | Time Machine: odds, media R e histórico. |
| `/tamano T` | Acciones y pérdida máxima al stop. |
| `/risk` | PASS/BLOCK de las órdenes propuestas. |
| `/ticket` | Ticket en papel (nunca se envía). |
| `/noticias T` | Titulares de 24 h con etiquetas. |
| `/resultados T` | Último trimestre SEC (XBRL). |
| `/pelosi` | PTR de Pelosi (contexto, nunca señal). |
| `/apertura T` | Bloque "coste de esperar". |
| `/mercados T` | Comparativa EE. UU. vs Europa. |
| `/vigila T` / `/dejar T` | Añade o quita de la watchlist fija. |
| `/vigilar` | Watchlist con precio y edad del dato. |
| `/alertas` | Reglas de alerta vigentes hoy. |
| `/alerta T precio` | Aviso puntual por encima de un precio. |
| `/precios T` | Yahoo + referencias manuales + plan vigente, con diferencia %. |
| `/ref T precio fuente` | Guarda el precio que ves en Börse Frankfurt/TradingView/Investing/MyInvestor. |
| `/entre T precio qty [stop] [obj]` | Registra tu entrada y arma avisos. |
| `/sali T precio [acciones]` | Registra salida total o parcial. |
| `/vender T precio` | Mueve el objetivo o deja un aviso de venta. |
| `/stop T precio` | Mueve el stop o deja un stop vigilado. |
| `/posiciones` | Posiciones abiertas registradas a mano. |
| `/pnl` | P&L manual bruto y registro de señales. |
| `/diario` | Últimos eventos del día. |
| `/pausa` / `/reanudar` | Silencia o reactiva solo las SEÑAL A nuevas. |
| `/ensenar concepto` | Explica ORB, R, stop, objetivo, Time Machine, Wilson, EV, spread, flat. |
| `/ayuda` | Menú actualizado. |

## 3. Frases que entiende el bot

El intérprete es determinista: normaliza tildes y abreviaturas (`xq`, `k`, `q`) y traduce un conjunto
cerrado de frases. No hay LLM y no se pasa texto libre a un shell.

| Frase | Comando |
| --- | --- |
| "qué está pasando" / "estado" | `/estado` |
| "qué hago ahora" | `/ahora` |
| "qué compro" / "¿entro?" | `/resumen` |
| "entro en NVDA" / "compro NVDA" | `/elegir NVDA` |
| "analiza NVDA" | `/ticker NVDA` |
| "evalúa NVDA" / "análisis completo de TSLA" | `/elegir NVDA` / `/elegir TSLA` |
| "explícame esta señal" | `/explica` |
| "por qué no hay señales" | `/porque` |
| "por qué descartaste NVDA" | `/porque NVDA` |
| "prepárame la apertura" | `/briefing` |
| "ya entré en NVDA a 142,5 con 8" | `/entre NVDA 142.5 8` |
| "he salido de NVDA a 156,4" | `/sali NVDA 156.4` |
| "vende NVDA a 160" | `/vender NVDA 160` |
| "stop de NVDA en 154" | `/stop NVDA 154` |
| "avísame si NVDA toca 155" | `/alerta NVDA 155` |
| "vigila NVDA" / "deja de vigilar NVDA" | `/vigila NVDA` / `/dejar NVDA` |
| "cómo voy" | `/pnl` |
| "qué ganadores hay" | `/ganadores` |
| "vigila los ganadores" / "sigue a los 5 ganadores" | `/seguir` / `/seguir 5` |
| "incluye MNSO en el escaneo" / "mete MNSO en la lista" | `/incluir MNSO` |
| "evalúa los ganadores" | `/evaluar` |
| "enséñame el ORB" | `/ensenar orb` |

## 4. Cómo leer un aviso

Un aviso solo llega si es **SEÑAL A**. Trae:

- **Entrada**, **stop**, **objetivo 2R** y **flat by close**.
- **Tamaño** y **pérdida máxima** al stop.
- **Coste** de ida y vuelta (EUR/USD).
- **Time Machine**, histórico, Wilson, break-even y **EV**.
- **SEC** (último trimestre) y registro vivo.
- **Cierre de vela y latencia**: cuánto tardó el aviso desde el cierre de la vela y cuánto fue el pipeline.

Antes de operar: dato ≤300 s, riesgo real ≤50 USD, EV positivo, sin noticias adversas, dentro de la
ventana y con tiempo para cerrar a las 21:55. Si el precio ya se movió más de 0,5R, la señal caduca.

## 5. Parámetros que puedes tocar

Están en `trader/config.json`:

- `budget`: 5.000 USD.
- `max_loss_per_trade_usd`: 50.
- `max_daily_loss_usd`: 150.
- `max_trades_per_day`: 3.
- `flat_by`: 15:55 ET.
- `no_entries_after`: 15:30 ET.
- `watch`: NVDA.
- `cuenta_eur`: true (si tu cuenta es USD, se pone false).
- `broker`: "none" y `paper`: true. No cambiar a un broker real sin decisión explícita.

Los umbrales de criterios están en `trader-ops/lib/criterios.py` y explicados en `CRITERIOS.md`.
No se cambian en silencio: se miden con `python trader-ops/run/simular_filtro.py` y se registran.

## 6. Si algo falla

| Síntoma | Arreglo |
| --- | --- |
| El bot no responde | Comprobar `DayTraderOps-Bot`, PC encendido y red; reiniciar la tarea. |
| No llegan avisos | Comprobar `DayTraderOps`, latido, pausa, mercado/festivo. |
| Datos obsoletos | `python trader-ops/run/smoke.py`; no operar con dato >300 s. |
| 429 de Yahoo | El sistema tiene backoff; no lanzar `/scan` en bucle. |
| Señal caducada | No perseguir; esperar otra ruptura u otro día. |
| Xetra no analiza | El motor es NY; analizar NVDA (USD); para posición usar `/entre NVD.DE`. |
| P&L no cuadra | `/pnl` es bruto; restar comisiones/FX del aviso. |

Parar todo: `Stop-ScheduledTask DayTraderOps` y `DayTraderOps-Bot`.
Reanudar: `Start-ScheduledTask DayTraderOps` y `DayTraderOps-Bot`.

## 7. De un ticket a una orden en MyInvestor (a mano, nunca automático)

1. La SEÑAL A trae entrada, stop, objetivo y tamaño.
2. Comprueba el precio actual en una fuente en tiempo real (MyInvestor muestra 15 min de retraso).
3. Lanza una orden **limitada** en MyInvestor; no persigas si el precio ya se fue.
4. Registra el fill con `/entre T precio qty stop objetivo`.
5. El sistema arma los avisos de stop y objetivo y vigila la posición.
6. Al cerrar, `/sali T precio` (total o parcial).

MyInvestor opera acciones de EE. UU. de 15:30 a 22:00 Madrid; fuera de ese horario, la orden se
lanza en la apertura. No consta premarket, after-hours ni overnight para acciones.

## 8. Dónde hablar conmigo

| Canal | Para qué |
| --- | --- |
| **Telegram** | El día a día: avisos, "qué hago ahora", entradas, salidas, estado. |
| **OpenCode** | Cambios, auditorías, análisis largos, "por qué", añadir funciones. |
| **Paneles** | Mirar sin preguntar: terminal y web. |

El contexto del chat no es la memoria del sistema. La memoria son los archivos: `ESTADO.md`,
`diario.jsonl`, `registro.json` y `trader/`. Una sesión nueva se reconstruye con `saludo.py`.

## 9. Ritmo diario: no tienes que preguntar cada día

1. **13:00** premarket: scanner + noticias + resultados + ganadores + Pelosi.
2. **15:00** briefing: candidatos y coste de esperar.
3. **15:50–21:30** escaneo ORB cada 5 min; solo si pasa todo llega una SEÑAL A.
4. **21:55** flat by close. **22:00** informe.

Si no llega nada, no hay nada que hacer. Preguntar "¿compro algo?" a las 10:00 no tiene respuesta útil:
todavía no existe el rango de apertura.

### Re-entradas el mismo día

- `entry.py` da un solo disparo por setup y día.
- Límite: 2 SEÑAL A por valor/día, 3/día, 30 min de enfriamiento.
- Tras un stop, no se reentra por el mismo setup. Nada de revenge trading.
- Salidas parciales: `/sali NVDA 156.4 3` cierra 3 acciones y deja el resto con su stop y objetivo.

### Ganadores

- `/ganadores` antes de abrir = ayer; en sesión = hoy.
- `/seguir N` añade los N primeros de esa lista a la lista ORB de hoy.
- `/evaluar N` ejecuta la cadena completa y los ordena por veredicto y EV.
- La única "recomendación" es la SEÑAL A; el resto son candidatos.

## 10. Qué hace el sistema con cada valor (todo lo disponible)

`scanner` (universo y setups) → `news` (titulares + 8-K) → `entry` (disparo) → `exit` (stop/objetivo)
→ `timemachine` (10.000 replays + histórico) → `budget` (tamaño) → `risk` (límites) →
`analyst` (XBRL: último trimestre) → `criterios` (Wilson + EV + liquidez) → `MCP MyInvestor`
(contratable) → validador → Telegram. `pelosi` entra como contexto diario, nunca como señal.

## 11. Qué hacer en cada momento del día

Leyenda: **sistema** = lo que hace solo; **tú** = lo único que se espera de ti; **ignora** = lo que
puedes descartar sin culpa.

### Antes del premarket (hasta 13:00)
- Sistema: duerme; el orquestador solo late.
- Tú: nada. Si quieres, `/ahora` o abrir el panel.
- Ignora: todo.

### Premarket (13:00–15:00)
- Sistema: scanner completo, noticias, resultados y Pelosi. Prepara candidatos.
- Tú: nada obligatorio. Mira `/hoy` si tienes curiosidad.
- Ignora: candidatos que no te interesen; no son compras.

### Antes de abrir (15:00–15:30)
- Sistema: briefing con candidatos, coste de esperar y plan condicional.
- Tú: lee el briefing y decide si hoy operas o no.
- Ignora: el detalle del scanner, ya viene resumido.

### Apertura (15:30–15:50)
- Sistema: espera a que se cierre el rango 9:30–9:45 ET.
- Tú: nada. **No se entra antes** de que exista el rango.
- Ignora: cualquier movimiento de los primeros 15 minutos; para el sistema es ruido.

### Ventana de entrada (15:50–21:30)
- Sistema: escaneo ORB cada 5 min; por cada ruptura, cadena completa y aviso solo si es SEÑAL A.
- Tú: si llega una SEÑAL A, decide y opera a mano. Si no llega, no hay nada que hacer.
- Ignora: rupturas que no pasan los filtros y avisos de "sin señal".

### Últimos 30 minutos (21:30–21:55)
- Sistema: ya no abre entradas nuevas; vigila stops y objetivos.
- Tú: gestiona lo que tengas abierto.
- Ignora: rupturas nuevas, llegan tarde.

### Cierre / flat by close (21:55–22:00)
- Sistema: aviso de flat y, al cierre, informe del día.
- Tú: cierra a mano lo que siga abierto. **No se mantiene nada**.
- Ignora: todo lo demás.

### Post-cierre (después de 22:00)
- Sistema: informe y silencio; vigilante activo.
- Tú: nada. `/resumen` o `/registro` si quieres.
- Ignora: todo. No se opera fuera de horario.

### Día sin señales
- Es un resultado válido. `/porque` dice qué criterios fallaron y cuántas veces.
- No se relajan filtros. Si quieres medir el efecto: `python trader-ops/run/simular_filtro.py --relajar historial`.

### Sistema caído
- `/estado` dirá "PARADO" y el watchdog habrá avisado.
- Arreglo: `Stop-ScheduledTask DayTraderOps; Start-ScheduledTask DayTraderOps`, o `python trader-ops/run/orquestador.py` en una terminal para ver el error.
- El panel muestra latido, errores de la última hora y 429.

### Datos obsoletos
- El sistema **no avisa señales** si el dato tiene más de 300 s: avisa del fallo.
- Comprueba `/estado` (edad de datos) y `python trader-ops/run/smoke.py`.

### Señal caducada
- Si el precio se alejó más de 0,5R antes de enviar, el aviso se marca **SEÑAL CADUCADA**.
- No se persigue: la entrada ya no es la del plan.

### Freno por evidencia activado
- Con 12 señales cerradas y R medio ≤ 0, el sistema deja de enviar SEÑAL A y lo avisa.
- Solo se reactiva si tú lo decides, después de revisar `/registro`.

### Si quieres relajar un filtro o un límite
1. `python trader-ops/run/simular_filtro.py --relajar <check>` mide cuántas señales más saldrían y con qué EV.
2. Si el EV medio de las nuevas es ≤ 0, no se relaja.
3. Si aun así decides cambiar algo, se anota en `CRITERIOS.md` con fecha, motivo y efecto medido. Nunca en silencio.

## 12. Paneles

| Panel | Cómo abrirlo | Qué es |
| --- | --- | --- |
| Terminal | doble clic en `Abrir panel.cmd` o `python trader-ops/run/panel.py` | Pantalla que se refresca cada 5 s: hora, mercado, fase, salud, vigilados, señales, posiciones, alertas, P&L y "qué hacer ahora". |
| Web | doble clic en `Abrir panel web.cmd` | `http://127.0.0.1:8765`, solo lectura, refresco 5 s, sin secretos ni botones. |

Ambos leen archivos de estado: no llaman a Yahoo, no cuestan cuota y no pueden ejecutar nada.
Si quieres una captura puntual: `python trader-ops/run/panel.py --once`.

## 13. Extras evaluados

| Extra | Estado | Nota |
| --- | --- | --- |
| Exportación CSV | **HECHO** | `python trader-ops/run/exportar.py` → `historico/*.csv` |
| Panel de terminal | **HECHO** | `Abrir panel.cmd` · refresco 5 s · solo lectura |
| Panel web local | **HECHO** | `Abrir panel web.cmd` · 127.0.0.1:8765 · sin secretos |
| Simulador de relajación de filtros | **HECHO** | `simular_filtro.py`: cuántas más y con qué EV |
| `/analiza X` con LLM | **DESCARTADO** | el modelo podría introducir cifras no verificadas; el validador no cubre prosa libre y el objetivo es cero tokens. Queda documentado como opción futura con etiqueta "no verificada" |
