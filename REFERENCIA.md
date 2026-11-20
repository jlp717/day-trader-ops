# REFERENCIA — sistema de trading en papel, límites y hoja de ruta

Documento de referencia del proyecto. Recoge lo acordado hasta el 19/11/2026 y separa lo que
**ya existe**, lo que **se puede construir** y lo que **no se debe construir todavía**.

Léelo antes de tocar el motor. El contrato operativo sigue siendo `AGENTS.md`; este documento
explica el porqué y el para qué. El estado por fases está en [`ROADMAP.md`](ROADMAP.md).

---

## 1. Qué es y qué no es

**Es** un banco de pruebas de day trading en papel, solo largo, sobre acciones de EE. UU., con:

- scanner diario del universo;
- lista ORB de 150 valores;
- escaneo cada 5 minutos;
- cadena de filtros (noticias, resultados, plan, risk, Time Machine, histórico, EV, deriva);
- alertas de stop/objetivo;
- registro, informes y panel local;
- ejecución **manual** en MyInvestor.

**No es**:

- un sistema de ejecución real: no hay broker conectado, no hay claves, no hay órdenes;
- un sistema de alta frecuencia;
- un sistema multi-mercado;
- una máquina de predecir dirección.

La ventaja histórica que trae es **pequeña y con muestra corta**. La ingeniería es buena; el alpha
no está demostrado en tu propia operativa (0 operaciones cerradas al escribir esto).

---

## 2. Estado actual (20/11/2026)

| Pieza | Estado |
| --- | --- |
| Motor ORB | funcionando, solo papel |
| Escaneo | 5 min, 150 candidatos |
| Datos | Yahoo (principal), CNBC y Finnhub (contraste) |
| Ejecución | manual en MyInvestor |
| Registro propio | **0 cerradas**; freno por evidencia activo por falta de muestra |
| Tests | **148 propios** + 315 del skill |
| Backtesting | **sí**: `run/backtest.py` (OR minutes, target R, stop mid/low, slippage, split IS/OOS, features) |
| Multi-estrategia | `lib/estrategias.py`: `orb` y `orb_low`; solo ORB en vivo |
| Ejecución de papel | `lib/brokers.py`: `PaperBroker` local y `AlpacaPaperBroker` (bracket); **real no** |
| Piloto de papel | `run/piloto.py`: convierte una SEÑAL A en bracket **paper** (dry-run por defecto) |
| Nivel 2 | **IEX top-of-book** (`lib/proveedores.py`); profundidad completa **no** |
| Machine learning | **baseline logístico** (`lib/ml.py`); sin señal en la muestra |
| Pre/post | **análisis** (`run/prepost.py`, radar automático); ejecución **no** |

---

## 3. Datos y latencia

Medido en vivo el 19/11/2026, mercado abierto:

| Fuente | Retraso observado | Nota |
| --- | --- | --- |
| Yahoo | 3–17 s | feed principal |
| CNBC | 3–10 s | segundo testigo |
| Finnhub | 9–23 s | tercer testigo; feed IEX, puede diferir unos céntimos |
| Ficha MyInvestor | variable, a veces >10 min | no usar para decidir |
| Ticket MyInvestor | el precio executable | la verdad para el fill |
| Vigilante rapido (`run/vigia.py`) | 15-30 s | solo niveles armados, no el universo |

Regla: si las fuentes difieren más de **0,5 %**, no se envía señal y se avisa con los valores.
Si el dato tiene más de **300 s**, no hay señal (`frescura`).

---

## 4. Límites y reglas de seguridad

1. **Solo papel.** `broker: none`, `paper: true`.
2. **Nunca claves de bróker** en el repo, en el chat ni en logs.
3. **No se automatiza la sesión de MyInvestor.** Ni con saldo 0. El bot avisa; el humano ejecuta.
4. **No se entra en el navegador del bróker** con credenciales.
5. **No se mueve un stop hacia abajo.**
6. **No se promedia una posición perdedora.**
7. **No se mantiene de noche** dentro del sistema; si se mantiene, es una decisión manual.
8. **No se escala** hasta tener 30–50 operaciones cerradas y un R neto positivo.

---

## 4b. Claves y planes gratis

| Servicio | Archivo | Plan | Límite | Uso |
| --- | --- | --- | --- | --- |
| Alpaca | `secrets/alpaca.json` | paper gratis | cuenta paper | órdenes simuladas + IEX top-of-book |
| Finnhub | `secrets/finnhub.json` | free | ~60/min | cotización US en tiempo real (IEX) |
| Polygon | `secrets/polygon.json` | de pago | según plan | nivel 2 completo (no gratis) |
| Yahoo | sin clave | free | sin SLA | velas 5m/1d y pre/post |
| CNBC | sin clave | free | sin SLA | segundo testigo de precio |

`secrets/` está en `.gitignore`. Ninguna clave se sube a GitHub, se pega en el chat ni se
escribe en logs.

**Lo que no existe gratis**: libro de órdenes completo (nivel 2) de acciones US, y ejecución
real sin bróker fondeado. Alpaca paper da ejecución simulada; IEX da profundidad 1. Eso es el
máximo gratuito y legal.



## 5. Capacidades avanzadas: qué se puede hacer y qué no

### 5.1 Backtesting automático — **implementado**

`python trader-ops/run/backtest.py --symbols NVDA,AMD --days 30`

Parámetros disponibles:

- `--or-minutes` 5–60: tamaño del rango de apertura.
- `--target-r`: objetivo en múltiplos de R.
- `--stop-rule mid|low`: stop en el punto medio o en el mínimo del rango.
- `--slippage-bps`: deslizamiento por lado.
- `--split 0.7`: separa in-sample / out-of-sample por fechas.
- `--max-cost-r`: descarta trades con coste superior a ese múltiplo de R.
- `--features`: exporta CSV de features/labels para un futuro modelo.
- `--json` y `--csv`: guardan resultados.

Mide la **mecánica de precio** del ORB:

- rango 9:30–9:45 ET;
- entrada en el primer cierre de 5 min por encima del máximo;
- stop en el mid, redondeado abajo;
- objetivo 2R;
- flat 15:55 ET;
- costes de MyInvestor;
- tamaño por riesgo máximo.

**No** reproduce noticias, Time Machine, Wilson ni EV históricos: esos filtros no se pueden
reconstruir sin datos que no tenemos. El backtest mide el patrón bruto, no la señal filtrada.
Es el punto de partida para saber si el patrón tiene alguna ventaja antes de seguir añadiendo capas.

Límites: Yahoo guarda 5 min durante ~60 días. Para más histórico hace falta un proveedor de pago.

#### Resultado del primer backtest (19/11/2026)

Universo: NVDA, AMD, CRCL, INTC, LLY, UNH, MNSO, AAPL, MSFT, TSLA.
Periodo: ~42 sesiones disponibles en el rango de 60 días de Yahoo.

| Corte | Trades | Acierto | R neto | PnL | Factor beneficio |
| --- | --- | --- | --- | --- | --- |
| Todos | 292 | 18,8 % | **−310,3R** | −14.950 USD | 0,10 |
| Coste ≤ 0,5R | 42 | 33,3 % | **−17,0R** | −811 USD | 0,30 |

**Lectura honesta**: el ORB **bruto** (sin noticias, sin Time Machine, sin Wilson, sin EV)
pierde dinero en esta muestra. La causa principal es el coste: con rangos de apertura muy
estrechos, el stop está a 0,3–0,5 % y el viaje de ida y vuelta (0,84 %) cuesta 1–2R por
operación (media 0,72R; 20 % de los trades con coste >1R). Incluso el subconjunto con
coste ≤ 0,5R sigue negativo.

Esto **no** invalida los filtros del sistema, pero tampoco los valida: demuestra que el patrón
bruto no es una ventaja por sí solo. Los filtros (calidad, EV, Time Machine, histórico) son la
única posible fuente de edge, y todavía no están medidos en una muestra propia.

Conclusión operativa: **no escalar**. El backtest es una herramienta para medir, no una prueba
de rentabilidad.

Estudio de filtros sobre el mismo periodo (IS/OOS 70/30):

| Subconjunto | Total | IS | OOS |
| --- | --- | --- | --- |
| Todos | −310R | −220R | −90R |
| Coste ≤0,5R | −17R | −5R | −12R |
| Rango ≥1 % | −227R | −150R | −77R |
| Antes de 11:00 | −239R | −178R | −61R |
| Coste ≤0,5R y antes de 11:00 | −15R | −4,5R | −10R |

**Ningún subconjunto es positivo out-of-sample.** No hay una ventaja clara que se pueda aislar con
estos datos. Los filtros de noticias, Time Machine, Wilson y EV no están en el backtest; podrían
cambiar el resultado, pero hoy no hay evidencia de que lo hagan.

### 5.2 Multi-estrategia — **interfaz + dos variantes**

`lib/estrategias.py` define una interfaz común y un registro. Hoy hay dos:

- `orb`: stop en el mid del rango.
- `orb_low`: stop en el mínimo del rango (variante, no una estrategia nueva).

Ambas se pueden backtestear con `--strategy orb|orb_low`. En la muestra del 19/11, **las dos
pierden**; la variante no arregla el patrón bruto. Añadir una estrategia nueva significa:

1. implementar `simular_dia(...)`;
2. registrarla;
3. backtestearla con split IS/OOS;
4. pasarla a papel con estado separado.

No se mezcla con el pipeline vivo hasta que pase su propia muestra.

### 5.3 Ejecución — **Alpaca paper; real no**

`lib/brokers.py` implementa:

- `Broker` (nulo): cualquier orden lanza error. Modo por defecto.
- `PaperBroker`: rellena al precio actual, guarda la orden en `state/paper_orders.json`,
  idempotencia y **nunca envía nada**.
- `AlpacaPaperBroker`: órdenes en la cuenta **paper** de Alpaca (`paper-api.alpaca.markets`),
  con `client_order_id` para idempotencia. Endpoint real **no existe en el código**.

Claves: `secrets/alpaca.json`

```json
{"api_key": "TU_KEY", "secret_key": "TU_SECRET"}
```

Cuenta gratis en alpaca.markets; se usa el entorno **paper**, no el real. La ejecución real
sigue cerrada: exige cuenta fondeada, límites duros, kill switch y aprobación explícita.

```powershell
# Simulacro: no envia nada
python trader-ops\run\orden.py --broker alpaca_paper --side buy --symbol NVDA --qty 1 --limit 100
# Envio a la cuenta PAPER de Alpaca
python trader-ops\run\orden.py --broker alpaca_paper --side buy --symbol NVDA --qty 1 --limit 100 --confirm
```

### 5.4 Nivel 2 — **IEX top-of-book; profundidad no**

`lib/proveedores.py` implementa:

- `ninguno`: falla explícito.
- `alpaca_iex`: bid/ask y tamaños del feed IEX (gratis), **profundidad 1**, no libro completo.
- `polygon`: interfaz para L2 de pago; sin clave/plan no funciona.

Claves: las mismas de `secrets/alpaca.json` para IEX; `secrets/polygon.json` para el proveedor
de pago. **No existe nivel 2 completo gratis para acciones US**: es una limitación de licencias,
no de código. El sistema no inventa profundidad.

```powershell
python trader-ops\run\libro.py --symbol NVDA --proveedor alpaca_iex
```

### 5.5 Machine learning — **baseline, sin señal**

`lib/ml.py` implementa una regresión logística sin dependencias, con estandarización,
regularización L2 y validación walk-forward. `run/ml.py` la ejecuta sobre el CSV de features.

Resultado con 50 trades (35 train / 15 test):

```text
Accuracy 0.800 · base 0.133 · AUC 0.269
```

La accuracy engaña por desbalance; el **AUC < 0.5** dice que el modelo ordena peor que el azar.
No hay señal. No se usa en producción; con 300–500 trades se puede repetir.

### 5.5b Pre/post — **análisis, no ejecución**

`run/prepost.py` analiza el premarket y el after-hours con Yahoo (`includePrePost=true`):
último precio, máximo, mínimo, variación y volumen (si Yahoo lo da). No ejecuta nada.
MyInvestor no permite órdenes fuera del horario regular.

```powershell
python trader-ops\run\prepost.py --symbols NVDA,AMD --modo pre
python trader-ops\run\prepost.py --radar --top 30 --modo pre
python trader-ops\run\prepost.py --radar --top 30 --modo post
```

Bot: `/pre T` y `/post T` muestran un valor; `/pre` y `/post` leen el último radar guardado.
Estado separado en `state/pre/` y `state/post/`; **no se suma al P&L intradía**.

### 5.6 Matriz de huecos (nada oculto)

| Capacidad | Código | Tests | En vivo | Puerta |
| --- | --- | --- | --- | --- |
| Backtest | `lib/backtest.py`, `run/backtest.py` | sí | no aplica | ninguna |
| Multi-estrategia | `lib/estrategias.py` | sí | solo ORB | backtest + papel |
| Ejecución papel | `lib/brokers.py` | sí | no | integrar en el flujo |
| Ejecución Alpaca paper | `lib/brokers.py`, `run/orden.py` | sí | **no** | clave + cuenta paper |
| Ejecución real | no existe | — | **no** | bróker fondeado + aprobación |
| Nivel 2 IEX | `lib/proveedores.py`, `run/libro.py` | sí | **no** | clave Alpaca |
| Nivel 2 completo | interfaz Polygon | sí | **no** | proveedor de pago |
| ML | `lib/ml.py`, `run/ml.py` | sí | **no** | 300–500 trades; hoy AUC 0.269 |
| Pre/post | `lib/prepost.py`, `run/prepost.py`, `/pre`, `/post` | sí | **no** | solo análisis |
| Europa | solo documento | no | **no** | proyecto separado |

Un hueco documentado y con puerta no es un fallo oculto: es una decisión de ingeniería.

### 5.7 Broker: qué hace falta para automatizar

Javier opera en **MyInvestor** y ahí se queda la ejecución mientras no haya una razón medida para
cambiar. Esta tabla responde a la pregunta "¿y si cambio de bróker?" sin humo:

| Bróker | API de órdenes | Cuenta de papel | Datos | Veredicto |
| --- | --- | --- | --- | --- |
| **MyInvestor** | **no** (app/web; el MCP es solo lectura) | no | ficha con retraso; el ticket manda | válido para validar a mano; **insuficiente** para latencia |
| **Interactive Brokers** | sí (TWS API y Client Portal Web API) | **sí** | L1 incluido; L2 por suscripción | **candidato nº1** si se automatiza |
| **Saxo Bank** | sí (OpenAPI) | sí | según cuenta | candidato europeo |
| **Alpaca** | sí | **sí, gratis** | IEX en tiempo real, gratis | solo **medición**; cuenta real según país (no verificado para España) |
| **DEGIRO** | no hay API pública oficial | no | — | descartado |
| **Tradier / TradeStation** | sí | sí | — | orientados a EE. UU. | descartado para residencia española |

Lo que la automatización **sí** resuelve: latencia de ejecución, disciplina (no se salta el plan),
registro automático del fill y del R, y límites duros que el humano incumple cuando está delante
de la pantalla.

Lo que la automatización **no** resuelve: **la ventaja**. Un bróker con API sobre una estrategia con
expectativa negativa pierde dinero más rápido y con mejor latencia. El orden correcto es
**medir → validar → automatizar**, nunca al revés.

Regla de decisión, ya escrita en el contrato:

1. No se cambia de bróker ni se abre cuenta real hasta tener **30–50 operaciones cerradas** con
   **R neto positivo** y drawdown conocido.
2. Si se decide automatizar, el primer paso es **IBKR en papel** con el mismo adaptador
   (`lib/brokers.py`), sin dinero y sin cambiar el flujo.
3. El código actual **no tiene endpoint real** de ningún bróker: no hay forma de enviar una orden
   real ni por error. Eso se mantiene hasta que Javier lo autorice por escrito.

---

## 6. Flujos de premarket y postmarket

### Lo que se puede hacer

- **Análisis premarket**: gaps, volumen pre, noticias, plan para la apertura.
- **Análisis postmarket**: cierre, after-hours, candidatos para el día siguiente.

### Lo que no se puede hacer con MyInvestor

- Comprar o vender a precio de premarket/after-hours.
- Capturar el hueco con una orden a ese precio.
- Garantizar ejecución en un mercado con poca liquidez.

Por tanto, un flujo pre/post con MyInvestor es **análisis y planificación**, no ejecución.
La ejecución sería a la apertura o al día siguiente.

### Datos

- Yahoo permite `includePrePost=true` en el chart (usado con CRCL).
- CNBC y Finnhub no siempre cubren horario extendido.
- El pre/post tiene spreads más anchos; los filtros de calidad deben ser más estrictos.

### Aislamiento

Si se implementa:

- estado separado: `trader-ops/state/pre/`, `state/post/`;
- informes separados;
- configuración separada;
- comandos con prefijo (`/pre`, `/post`) o bot/token separado;
- **nunca** sumar su P&L al flujo intradía.

---

## 7. Europa + EE. UU.

Es un proyecto aparte, no una pestaña más:

- Xetra tiene otro horario, otro spread y otra liquidez;
- el skill actual no acepta `NVD.DE` en las herramientas de barras;
- MyInvestor permite operar valores europeos, pero la ejecución y los costes son distintos;
- la fiscalidad y el horario cambian;
- haría falta un flujo europeo con su propio backtest y su propia muestra.

Orden sensato: validar EE. UU. → premarket → postmarket → Europa.

---

## 8. Arquitectura de flujos separados

| Capa | Reutilizable | Específico |
| --- | --- | --- |
| Config | `cfg` | `config_pre.json`, `config_post.json` |
| Diario | `diario` | prefijo de eventos |
| Alertas | `alertas` | niveles y símbolos propios |
| Telegram | `telegram` | comandos con prefijo o bot aparte |
| Informes | `informe` | plantilla propia |
| Estrategia | interfaz `estrategias` | hipótesis y filtros nuevos |
| Datos | `datos` | fuente pre/post y horarios |

Regla: **un flujo, un estado, un P&L, una muestra**. Si se mezclan, no se sabe qué funciona.

---

## 9. Validación

Antes de considerar un flujo "vivo":

1. **Backtest** con costes y supuestos conservadores.
2. **Papel** durante 30–50 operaciones.
3. **R neto** positivo y drawdown aceptable.
4. **Registro** completo: entrada, stop, objetivo, fill, coste, R.
5. **Revisión independiente** del código y de los números.
6. Solo entonces, ejecución real con capital pequeño y límites duros.

El freno por evidencia del sistema ya exige 12 cerradas; para dinero real, 30–50 es el mínimo
razonable.

### 9b. El ORB, medido en un universo amplio (20/11/2026)

Para descartar que el resultado negativo fuera de la muestra pequeña (2 valores, 60 días), se
repitió con **40 valores líquidos de 10 sectores, 60 sesiones, 1.264 operaciones**:

| Configuración | Trades | Acierto | R neto | In-sample | Out-of-sample |
| --- | ---: | ---: | ---: | ---: | ---: |
| ORB, con costes, objetivo 2R | 1.264 | 16,1 % | **−1.650R** | −1.176R | −474R |
| ORB, **sin costes**, objetivo 2R | 1.264 | 40,0 % | **−91R** | −47R | −44R |
| ORB, **sin costes**, objetivo 1R | 1.264 | 46,4 % | **−79R** | −40R | −39R |

Lectura: con objetivo 1R el punto de equilibrio está en el 50 % de acierto; el patrón da 46,4 %.
**El problema no son las comisiones: el patrón bruto ya pierde.** Un coste medio de 1,23R solo
convierte una pérdida pequeña en una pérdida enorme (59,4 % de los trades cuestan más de 1R).

Conclusión: la hipótesis "ruptura del rango de apertura, largo, objetivo 2R" **queda falsificada**
en este periodo. No se escala, no se automatiza y no se le añaden filtros para maquillarla: se
sustituye por otra hipótesis con su propio backtest.

### 9c. Otras dos hipótesis, medias con las mismas reglas

Mismo universo (40 valores), mismas 60 sesiones, mismo split 70/30, mismos costes:

| Hipótesis | Trades | Acierto | Neto con costes | Bruto | Out-of-sample |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hueco a la baja + recuperación (`gap_reclaim`) | 112 | 30,4 % | **−59,1R** | +3,8R | −3,8R |
| Swing RSI-2 sobre acciones (`swing.py`) | 384 | 55,2 % | **−0,247 %/trade** | +0,303 %/trade | bruto −0,106 %/trade |

Lectura:

- **`gap_reclaim`**: el bruto es cero estadístico (+0,03R por trade). El hueco no se cierra
  intradía: 57 de 112 salidas son por cierre de sesión. Sin ventaja.
- **RSI-2**: el efecto existe en bruto (+0,303 % por trade, 55 % de acierto) pero **el coste de
  MyInvestor (≈0,52-0,55 % ida y vuelta) se lo come entero**, y fuera de muestra el bruto ya es
  negativo. Con un bróker de 0,07 % seguiría sin ventaja fuera de muestra.

Conclusión de las tres: **ninguna hipótesis medida con datos gratis y ejecución manual supera
los costes con ventaja sostenida**. El cuello de botella no es el código; es la ventaja y el
coste por operación.

---

## 10. Veredicto (20/11/2026)

Lo que está **terminado y probado**, y no depende de dinero:

- motor intradía determinista, sin LLM, con trazabilidad de cada cifra;
- datos con contraste a tres fuentes y bloqueo si difieren >0,5 %;
- backtest configurable con costes, slippage y split IS/OOS;
- dos estrategias registradas, tres ejecuciones de papel (local, Alpaca, piloto bracket);
- radar pre/post automático, con estado **separado** del P&L intradía;
- IEX top-of-book, ML baseline walk-forward, 148 tests propios.

Lo que **no** está demostrado, y es lo único que importa para ganar:

- **La ventaja.** El ORB bruto pierde −310R en la muestra pequeña y **−1.650R en 1.264 trades de
  40 valores**; incluso **sin costes** pierde (−79R a 1R, −91R a 2R) con 46,4 % de acierto frente al
  50 % que necesita. La hipótesis está **falsificada**, no "pendiente de muestra". El ML da AUC
  0,269, que es ruido.
- Por tanto, **no** es una terminal Bloomberg ni una máquina de ventaja. Es una herramienta de
  disciplina, medición y alertas construida con estándar profesional.

Lo que **no se puede comprar con código** (y hay que decirlo):

| Carencia | Por qué | Qué la resuelve |
| --- | --- | --- |
| Profundidad L2 real | no existe gratis para acciones US | suscripción Polygon/Databento |
| Ejecución en segundos | MyInvestor no tiene API de órdenes | bróker con API (IBKR/Saxo) |
| Ventaja estadística | muestra de 60 días y 0 trades propios | 30–50 trades cerrados y más historia |
| Datos institucionales | free tiene retraso y sin SLA | proveedor de pago |

La frase que resume el proyecto: **la ingeniería está terminada; la ventaja está en evaluación.**

---

## 11. Próximos pasos (ordenados, sin humo)

**Ahora, gratis, sin cambiar de bróker:**

1. **Usar el sistema a diario** con la rutina de §12 y registrar **cada** operación con `/entre` y
   `/sali`. Sin registro no hay muestra y sin muestra no hay decisión.
2. **Cerrar 30–50 operaciones.** Es el único gate que desbloquea todo lo demás.
3. **Medir** R neto, acierto, expectancy, profit factor y drawdown máximo (§9).
4. **Piloto de papel** (`run/piloto.py`) para generar muestra sin riesgo y comparar el plan teórico
   con el fill real.

**Después, solo si la muestra es positiva:**

5. Segunda estrategia **con hipótesis propia** (no una variante del ORB), con su backtest y su papel.
6. Automatización de ejecución: IBKR en papel primero, con límites duros, idempotencia y kill switch.
7. L2 de pago **solo si se mide** que el spread es lo que mata las entradas.
8. ML con 300–500 trades; hoy no hay señal y no se usa.
9. Europa como proyecto separado: otro horario, otro bróker, otros datos y otra fiscalidad.

**Nunca:** ejecución real sin muestra, sin límites y sin aprobación explícita de Javier.

---

## 12. Rutina diaria (la que se usa de verdad)

| Hora (Madrid) | Acción | Comando |
| --- | --- | --- |
| 12:50 | encender y comprobar salud | `saludo.py`, `/estado` |
| 13:10 | radar premarket automático | tarea `DayTraderOps-PreRadar` → Telegram |
| 15:00 | briefing y candidatos | `/briefing`, `/scan` |
| 15:25 | vigilante rapido de niveles | tarea `DayTraderOps-Vigia` (30 s) |
| 15:30 | apertura; niveles del ORB | `/apertura`, `/guia` |
| 15:50–21:30 | señales y gestión | SEÑAL A, `/posiciones`, `/alertas` |
| 21:55 | cerrar antes del cierre | `/guia`, `/vender` |
| 22:00 | informe automático | tarea `DayTraderOps` |
| 22:05 | radar postmarket | `DayTraderOps-PostRadar` → Telegram |

Regla de oro: si el sistema no da SEÑAL A, **no se opera**. El silencio es una decisión, no un fallo.
