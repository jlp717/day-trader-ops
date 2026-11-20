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
| Tests | **201 propios** + 315 del skill |
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

Nada de esto toca el flujo de EE. UU.: el día que exista, Europa vivirá en `state/eu/`, con
sus propios comandos, su P&L y su muestra. Las herramientas del skill **no** se usan para
Europa (convierten `NVD.DE` en `NVD-DE` y fallan); el motor propio sí acepta el sufijo.
Mientras no exista ese módulo, Europa es solo documentación y no se anuncia como hecho.

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

### 9d. Las salidas: fijo, breakeven y trailing (20/11/2026)

La pregunta era: si llegamos al objetivo y sigue subiendo, ¿no deberíamos perseguir el precio?
Se implementaron tres políticas de salida y se midieron sobre los mismos 1.264 trades del ORB
(40 valores, 60 sesiones, **sin costes** para aislar el efecto de la salida):

| Salida | Acierto | R neto | Drawdown máx. | Duración media |
| --- | ---: | ---: | ---: | ---: |
| Objetivo fijo 1R | 46,4 % | −78,9R | −85,8R | 125 min |
| Objetivo fijo 2R | 40,0 % | −90,8R | −93,6R | 177 min |
| Breakeven a 1R + trailing 1R | 45,9 % | −78,4R | −80,2R | 160 min |
| Trailing desde 0,5R | 32,0 % | −67,2R | −67,6R | 116 min |

Lectura: el trailing **mejora la forma** (menos drawdown, menos pérdida, operaciones más cortas)
pero **no cambia el signo**. Con una entrada sin ventaja, ninguna salida gana dinero; con una
entrada con ventaja, la salida amplifica o recorta esa ventaja, no la crea.

Esto responde también a la otra duda: sí, un stop te saca y a veces el precio se da la vuelta.
El stop no está para acertar, está para que una operación mala no se convierta en una ruina. Si
se quiere participar de la continuación, la herramienta correcta es el trailing, y su coste es
más operaciones pequeñas y menos aciertos.

El skill original usa **objetivo 1R** en su propio ejemplo y su Time Machine concluye "close to
a coin flip". Su README lo dice sin rodeos: "Most people who day trade lose money". No vende
ventaja: vende proceso.

---

## 10. Veredicto (20/11/2026)

Lo que está **terminado y probado**, y no depende de dinero:

- motor intradía determinista, sin LLM, con trazabilidad de cada cifra;
- datos con contraste a tres fuentes y bloqueo si difieren >0,5 %;
- backtest configurable con costes, slippage y split IS/OOS;
- dos estrategias registradas, tres ejecuciones de papel (local, Alpaca, piloto bracket);
- radar pre/post automático, con estado **separado** del P&L intradía;
- IEX top-of-book, ML baseline walk-forward, 185 tests propios.

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

---

## 13. Estado por fases: listo, en desarrollo y pendiente de mercado real

### Listo (código, tests y documentación)

| Pieza | Evidencia |
| --- | --- |
| Motor intradía determinista y trazable | 201 tests propios |
| Tesis de aguante (estructura, fundamentos, zona de venta) | `lib/tesis.py`, `/tesis` |
| Adaptador IBKR solo papel (cuenta DU) | `lib/ibkr.py`, `ibkr_paper` |
| Datos Yahoo + CNBC + Finnhub con contraste 0,5 % | `lib/datos.py`, `lib/proveedores.py` |
| Backtest con costes, slippage, IS/OOS y tres tipos de salida | `lib/backtest.py`, `lib/estrategias.py` |
| Tres hipótesis medidas y documentadas | ORB, `gap_reclaim`, swing RSI-2 (§9b–9d) |
| Radar pre/post automático y separado | tareas 13:10 y 22:05 |
| Vigilante de niveles cada 30 s | `run/vigia.py`, tarea 15:25 |
| Niveles manuales persistentes | `lib/niveles.py`, `/nivel` |
| Ejecución de papel (local y Alpaca) | `lib/brokers.py`, `run/orden.py`, `run/piloto.py` |
| ML baseline walk-forward | `lib/ml.py` (sin señal: AUC 0,269) |

### En desarrollo

Nada de código. La fase abierta es la **validación**, y no avanza escribiendo: avanza operando.

### Pendiente de mercado real (no se puede simular)

| Pendiente | Por qué no está hecho |
| --- | --- |
| 30–50 operaciones cerradas propias | hoy hay 0; requiere sesiones reales |
| R neto, acierto y drawdown reales | dependen de los fills de MyInvestor |
| Deslizamiento real vs plan | solo se mide con ejecuciones reales |
| Vigilante probado en vivo | hoy solo pruebas offline y mercado cerrado |
| Decidir si el trailing ayuda **a tu operativa** | el backtest dice que mejora la forma, no el signo |

### Pendiente de dinero o de una decisión tuya

| Pendiente | Qué necesita |
| --- | --- |
| Nivel 2 completo | suscripción Polygon/Databento |
| Automatización de ejecución | IBKR (API) + cuenta de papel + límites |
| Europa | proyecto separado: horario, bróker, datos, fiscalidad |
| Ejecución real | bróker fondeado + 30–50 trades + aprobación explícita |

### Bloqueado por el bróker

- **Automatizar con MyInvestor**: no hay API de órdenes.
- **Operar pre/post**: MyInvestor no permite órdenes extendidas.

Un pendiente con motivo no es un fallo oculto: es una decisión de ingeniería.

---

## 14. Tesis: dos horizontes separados (corto y largo)

La pregunta era: "si baja mucho, ¿me alarma o aguanto?". La respuesta correcta no es una:
son **dos preguntas distintas** y antes se mezclaban en una sola palabra ("rota").

| Horizonte | Qué mide | Qué decide |
| --- | --- | --- |
| **Corto plazo** (días-semanas) | precio vs SMA200, SMA50 vs SMA200, caída desde máximos, RSI | el stop, el aviso del vigilante y si se opera hoy |
| **Largo plazo** (meses-años) | fundamentos (ingresos, margen, ROE), pendiente de la SMA200, caída | si la tesis de inversión sigue viva |

Veredictos de corto: **a favor / neutral / en contra**.
Veredictos de largo: **viva / en riesgo / rota**, con puntuación sobre 6 (o sobre 3 si no hay
fundamentales).

Esto responde al caso típico: una empresa puede tener el **corto en contra** y el **largo vivo**.
El sistema lo dice así, sin recomendar vender: "no te acompaña en el corto; para recomponer
necesita cerrar por encima de X (+Y %)". Eso es información, no una orden.

Además, `/tesis T` añade:

- **noticias** de los últimos 7 días (Finnhub, gratis) con etiquetas simples: resultados, guía,
  upgrade/downgrade, acuerdo/proveedor, riesgo legal, fusión, empleo;
- **pares** aproximados del sector (Finnhub; la calidad del plan free es limitada);
- **nivel de recomposición**: cuánto le falta al precio para recuperar la SMA200.

Límites, dichos claro: **no predice**. Una empresa con fundamentos excelentes puede caer un 50 %
más; una con la estructura rota puede recuperarse. Lo que hace es impedir que un retroceso normal
te saque por nervios y darte un criterio escrito. No vende por ti.

```text
/tesis NVDA              los dos horizontes, noticias y pares
/tesis NVDA aguantar     no alarmar mientras el corto no esté en contra
/tesis NVDA liberar      volver al comportamiento normal
```

---

## 15. Datos: qué es gratis y qué no (investigado el 20/11/2026)

| Necesidad | Gratis | Realidad |
| --- | --- | --- |
| Cotización US en tiempo real | **sí**: Finnhub free (feed IEX) y Alpaca IEX | segundos de retraso, sin SLA |
| Velas 1–5 min | **sí**: Yahoo | 15-60 s de retraso, no oficial |
| Nivel 2 (profundidad) por API | **no** | Polygon/Databento/Nasdaq TotalView son de pago |
| Nivel 2 en plataforma | **sí, con cuenta fondeada** | moomoo, Webull, Ironbeam, IBKR con suscripción: no hay API gratis |
| Noticias y fundamentales | **sí, limitado** | Finnhub free (métricas), SEC EDGAR, Yahoo |
| Datos institucionales con SLA | no | proveedor de pago |

Conclusión: **el L2 gratis no existe por API**. Existe dentro de plataformas de bróker
con cuenta fondeada, y eso no se puede integrar aquí sin cambiar de bróker y fondear.
Este proyecto se queda con IEX top-of-book (L1) y lo dice en cada pantalla.

---

## 16. Interactive Brokers: adaptador listo, sin cuenta y sin dinero

Se ha dejado preparado `lib/ibkr.py` + `IBKRPaperBroker` para que el día que se decida
automatizar no haya que reescribir nada:

- Usa el **Client Portal Web API** oficial (Gateway local en `https://localhost:5000`).
- **Solo papel**: la cuenta debe empezar por `DU`. Si empieza por `U`, el cliente se
  niega a enviar cualquier orden. No hay endpoint real en el código.
- No guarda credenciales: la sesión la tiene el Gateway de IBKR.
- Configuración opcional en `secrets/ibkr.json`:

```json
{"account_id": "DU1234567", "base_url": "https://localhost:5000/v1/api", "paper": true}
```

- Órdenes limitadas o de mercado, con confirmación de los mensajes de réplica de IBKR.

Estado: **código listo y probado con mocks** (185 tests). No se ha conectado a un
Gateway real porque no hay cuenta ni se ha instalado nada. Cuando la haya:

```powershell
python trader-ops
un\orden.py --broker ibkr_paper --side buy --symbol AAPL --qty 1 --limit 200
python trader-ops
un\orden.py --broker ibkr_paper --side buy --symbol AAPL --qty 1 --limit 200 --confirm
```

Sin `--confirm` no se envía nada; con `--confirm` iría a una cuenta **DU** (papel).

---

## 17. RAW NASDAQ LITE (nico66fx): indicador y versión Python

El indicador original está guardado en `tradingview/RAW_NASDAQ_LITE.pine` (Pine v6, tal cual,
sin modificar). Qué hace:

1. Toma la **primera vela de 5 minutos de Nueva York** (09:30–09:35 ET).
2. Calcula una media exponencial de los cierres de 5 min con **alfa 4/26**.
3. Si el cierre de esa vela está **por encima** de la media → **COMPRA**; por debajo → **VENTA**.
4. Una señal al día, sin repintar, cuando la vela ya ha cerrado. No calcula stops ni contratos.

### Cargarlo en TradingView (5 minutos, manual)

No automatizo tu app: no hay MCP oficial de TradingView y entrar en tu cuenta desde aquí sería
un riesgo que no voy a asumir. Se hace a mano, una vez:

1. Abre TradingView y un gráfico (MNQ1!, NQ1! o el valor que quieras).
2. Abajo, **Pine Editor**.
3. Abre `tradingview/RAW_NASDAQ_LITE.pine`, copia todo y pégalo en el editor.
4. **Guardar** → **Añadir al gráfico**.
5. En el gráfico, pon la temporalidad en **5 minutos** (o la que uses: el script baja a 5 min solo).
6. Para acciones: escribe el ticker (por ejemplo `NVDA`) en el mismo gráfico. El script usa
   `syminfo.tickerid`, así que funciona en cualquier símbolo; lo que cambia es si tiene ventaja.

### Versión Python (integrada en el bot)

`lib/raw.py` replica la misma regla y el bot la calcula sin depender de TradingView:

```text
/raw NVDA
python trader-ops/run/raw.py --symbol NVDA
python trader-ops/run/raw.py --backtest --days 60 --cost 0.52
```

### Medición honesta en acciones (20/11/2026)

40 valores líquidos, 60 sesiones, **2.400 días-valor**:

| Métrica | Sin costes | Con coste 0,52 % |
| --- | ---: | ---: |
| Señal COMPRA (n=1.216) | −0,181 %/sesión | **−0,701 %** |
| Base: comprar cualquier día a las 09:35 | −0,138 % | −0,658 % |
| Ventaja de la señal | **−0,042 puntos** | −0,043 puntos |

Lectura: en acciones, la señal **no bate a comprar cualquier día**. El indicador está pensado
para futuros del Nasdaq (MNQ/NQ), donde el intradía y el apalancamiento son otra cosa; trasladarlo
a acciones sin medirlo habría sido un error de principiante. Se queda como ** herramienta de
timing y niveles**, no como ventaja demostrada.

---
### Adaptación a Xetra (Europa)

Archivo listo para pegar: `tradingview/RAW_XETRA_LITE.pine`. Misma lógica, con estos cambios:

- zona horaria `Europe/Berlin` (la misma hora que Madrid todo el año);
- primera vela de **09:00–09:05 CET** en vez de 09:30–09:35 ET;
- etiquetas y panel con "09:00", "Xetra" y "09:00 España";
- atribución al autor original (nico66fx) y sin el canal de comunidad del original.

En Python: `--mercado eu` (o `/raw SAP.DE eu`), con universo propio de 20 valores líquidos
de Xetra y coste por defecto del 0,30 % (sin FX, pero con spreads más anchos).

Medición (20 valores, 60 sesiones, 1.200 días-valor):

| Métrica | Sin costes | Con coste 0,30 % |
| --- | ---: | ---: |
| Señal COMPRA (n=578) | +0,020 %/sesión (49,0 % acierto) | −0,280 % |
| Base: comprar cualquier día a las 09:05 | −0,031 % | −0,331 % |
| Ventaja de la señal | **+0,050 puntos** | +0,051 puntos |

Lectura: en Xetra el bruto es ligeramente positivo y bate a la base por 0,05 puntos por sesión,
pero **el coste se lo come**. No es una ventaja operable; sirve como timing y niveles, igual que
en EE. UU., donde el bruto ya era negativo (−0,04 puntos).

Ejemplo real del 20/11/2026 a las 09:40 Madrid: SAP.DE, SIE.DE y ALV.DE dieron **VENTA** en la
primera vela; el sistema es solo largo, así que hoy no se opera en esas tres.

---
### Versión completa (PRO): stop, objetivo, tamaño y filtros

La LITE solo da dirección. La completa añade stop en el mínimo de la primera vela, **distancia
mínima de stop (0,20 %)** para que un rango diminuto no genere un tamaño absurdo, objetivo a N×R,
tamaño por riesgo **con tope de capital**, multiplicador de contrato y filtro de tendencia diaria.

**EE. UU.** (40 valores, 60 sesiones, coste 0,52 %):

| Variante | n | Acierto | Media/op | Total | OOS |
| --- | ---: | ---: | ---: | ---: | ---: |
| stop 1R | 1.215 | 27,1 % | −0,554 % | −673 % | −227 % |
| stop 2R | 1.215 | 25,3 % | −0,579 % | −703 % | −239 % |
| stop 3R | 1.215 | 26,3 % | −0,574 % | −698 % | −236 % |
| 2R + tendencia | 590 | 22,9 % | −0,593 % | −350 % | −102 % |
| 2R + rango | 835 | 21,4 % | −0,610 % | −509 % | −156 % |
| 2R + volumen | 282 | 29,4 % | −0,510 % | −144 % | −42 % |
| 2R + tendencia + volumen | 142 | 27,5 % | −0,517 % | −73 % | −24 % |
| 2R + gap | 1.045 | 25,6 % | −0,571 % | −597 % | −201 % |
| 2R + cierre alto | 667 | 29,4 % | −0,582 % | −388 % | −131 % |
| 2R + gap + cierre alto | 526 | 30,8 % | −0,571 % | −300 % | −100 % |
| trailing | 1.215 | 20,3 % | −0,562 % | −683 % | −229 % |

**Xetra** (20 valores, 60 sesiones, coste 0,30 %):

| Variante | n | Acierto | Media/op | Total | OOS |
| --- | ---: | ---: | ---: | ---: | ---: |
| stop 1R | 578 | 31,5 % | −0,323 % | −187 % | −52 % |
| stop 2R | 578 | 35,1 % | −0,315 % | −182 % | −42 % |
| stop 3R | 578 | 29,2 % | −0,308 % | −178 % | −34 % |
| 2R + tendencia | 330 | 34,5 % | −0,322 % | −106 % | −21 % |
| 2R + rango | 538 | 36,1 % | −0,288 % | −155 % | −32 % |
| 2R + volumen | 0 | — | — | — | — |
| 2R + gap | 489 | 36,0 % | −0,303 % | −148 % | −37 % |
| 2R + cierre alto | 316 | 32,3 % | −0,330 % | −104 % | −16 % |
| 2R + gap + cierre alto | 241 | 33,2 % | −0,308 % | −74 % | −13 % |
| trailing | 578 | 24,9 % | −0,310 % | −179 % | −39 % |

Lectura: **ninguna variante es positiva neta en ninguna de las dos zonas.** El filtro de volumen es
el mejor en EE. UU. (−0,51 % frente a −0,58 %) y en Xetra deja 0 operaciones porque Yahoo no da
volumen en velas de 5 min de los valores alemanes. Los filtros de gap y de cierre alto tampoco
salvan la expectativa: recortan operaciones, no añaden acierto.

### Tabla por valor (tu cartera, 20/11/2026)

| Valor | Mercado | Indicador | Señal hoy | LITE 60d | PRO 2R 60d |
| --- | --- | --- | --- | ---: | ---: |
| DWNI.DE | Xetra | **XETRA** | VENTA | −0,873 % | −0,478 % |
| NVD.DE | Xetra | **XETRA** | COMPRA | −0,321 % | −0,254 % |
| AAD.DE | Xetra | **XETRA** | VENTA | −0,581 % | **+0,118 %** (n=28) |
| LEG.DE | Xetra | **XETRA** | COMPRA | −0,564 % | −0,259 % |
| CRCL | NYSE | **US** | COMPRA | −0,581 % | −0,912 % |
| TLK | NYSE | **US** | VENTA | −0,591 % | −0,627 % |
| SIRI | Nasdaq | **US** | VENTA | −0,299 % | −0,341 % |

La regla es la misma; **lo que cambia es la sesión**: la primera vela es 09:00 CET en Xetra y 09:30
ET en EE. UU. NVD.DE es Nvidia, pero cotiza en euros y en horario alemán: le toca el indicador de
Xetra, no el de EE. UU. AAD.DE es el único con media positiva, con 28 operaciones: **no es
significativo**, es un dato descriptivo, no una ventaja.

### Rigor de la implementación

- **Sin lookahead**: test que cambia barras posteriores y comprueba que la dirección no cambia.
- **Horario de verano e invierno**: test del 30/03 y del 26/10 en Berlín; la vela de las 09:00 se
  encuentra igual.
- **Stop mínimo del 0,20 %** y **tope de capital**: evitan tamaños imposibles (el caso NVD.DE daba
  499 acciones con 50 USD de riesgo; ahora da 71, limitado por la cuenta).
- **Coste por mercado**: 0,52 % en EE. UU. (FX incluido), 0,30 % en Xetra.
- **201 tests propios OK**, IS/OOS en todas las variantes.

---
### Muestra larga: 7 años de datos SIP (20/11/2026)

Yahoo solo entrega 60 sesiones de 5 minutos. Para medir de verdad, la regla se ejecutó con
**barras consolidadas SIP de Alpaca desde 2020** (10 valores líquidos, 1,1 millones de barras,
9.322 operaciones). Validación cruzada: para NVDA el 19/11, Yahoo y Alpaca dan el mismo cierre de
la primera vela (156,91) y la misma EMA (151,86).

| Variante | Operaciones | Acierto | Media/op | Intervalo bootstrap 95 % |
| --- | ---: | ---: | ---: | --- |
| stop 2R | 9.322 | 26,3 % | −0,521 % | [−0,539, −0,501] |
| 2R + tendencia SMA200 | 5.598 | 25,2 % | −0,520 % | [−0,542, −0,496] |
| 2R + volumen | 1.921 | 30,0 % | −0,527 % | [−0,582, −0,468] |

Lectura, y es la conclusión más importante de todo el proyecto:

- **En bruto, la regla es cero**: −0,521 % neto + 0,52 % de coste = **−0,001 % por operación**.
  Es una moneda al aire, ni más ni menos.
- **El coste es todo el resultado**: con 0,52 % de ida y vuelta, una moneda al aire se convierte
  en una pérdida segura. Los filtros cambian *qué* operaciones se hacen, no la expectativa.
- Los intervalos bootstrap no cruzan cero: la pérdida está medida con precisión, no es mala suerte
  de una muestra corta.
- Conclusión operativa: **no se opera con esta regla como sistema de ventaja**. Sirve como
  temporizador y para tener un plan escrito (entrada, stop, tamaño), no como máquina de ganar.

Las versiones `strategy` (`tradingview/RAW_STRATEGY_US.pine` y `RAW_STRATEGY_XETRA.pine`) permiten
reproducir esto en el Strategy Tester de TradingView, con comisiones incluidas.

---

