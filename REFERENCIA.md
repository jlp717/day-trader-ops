# REFERENCIA — sistema de trading en papel, límites y hoja de ruta

Documento de referencia del proyecto. Recoge lo acordado hasta el 19/11/2026 y separa lo que
**ya existe**, lo que **se puede construir** y lo que **no se debe construir todavía**.

Léelo antes de tocar el motor. El contrato operativo sigue siendo `AGENTS.md`; este documento
explica el porqué y el para qué.

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

## 2. Estado actual (19/11/2026)

| Pieza | Estado |
| --- | --- |
| Motor ORB | funcionando, solo papel |
| Escaneo | 5 min, 150 candidatos |
| Datos | Yahoo (principal), CNBC y Finnhub (contraste) |
| Ejecución | manual en MyInvestor |
| Registro propio | **0 cerradas**; freno por evidencia activo por falta de muestra |
| Tests | 132 propios + 315 del skill |
| Backtesting | **sí**: `run/backtest.py` (OR minutes, target R, stop mid/low, slippage, split IS/OOS, features) |
| Multi-estrategia | `lib/estrategias.py`: `orb` y `orb_low`; solo ORB en vivo |
| Ejecución | **papel**: `lib/brokers.py` (Null/Paper); real **no** |
| Nivel 2 | **interfaz**: `lib/proveedores.py`; sin datos |
| Machine learning | **export de features**; sin modelo |

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

### 5.3 Ejecución real — **interfaz y modo papel; real no**

`lib/brokers.py` implementa:

- `Broker` (nulo): cualquier orden lanza error. Es el modo por defecto.
- `PaperBroker`: rellena al precio actual, guarda la orden en `state/paper_orders.json`,
  soporta clave de idempotencia y **nunca envía nada al mercado**.

La ejecución real sigue cerrada. Requisitos si algún día se abre:

- bróker con API de órdenes (no MyInvestor; no scraping);
- cuenta separada, capital pequeño;
- sandbox/paper del bróker primero;
- límites duros por operación, día y drawdown;
- kill switch;
- idempotencia para no duplicar órdenes;
- auditoría de cada orden;
- revisión independiente del código que toca dinero.

Con 0 operaciones cerradas, automatizar sería escalar una hipótesis no validada.

### 5.4 Datos de nivel 2 — **interfaz; sin datos**

`lib/proveedores.py` define la interfaz y un proveedor `ninguno` que falla de forma explícita.
No se inventan libros de órdenes. El nivel 2 es de pago (Polygon, Databento, etc.) y no está en
Yahoo/CNBC/Finnhub free. Sin una razón medida (por ejemplo, medir el impacto del spread en el
ORB), no compensa el coste.

### 5.5 Machine learning — **features sí; modelo no**

`run/backtest.py --features salida.csv` exporta features y etiquetas reproducibles:

- fecha, hora, símbolo;
- rango de apertura y su porcentaje;
- entrada, stop, objetivo, riesgo;
- coste en R, motivo de salida, R neto.

No se entrena ningún modelo. Con 33 disparos históricos y 0 propios, cualquier modelo aprendería
ruido. Antes hacen falta 300–500 operaciones etiquetadas, validación walk-forward y costes
modelados.

### 5.6 Matriz de huecos (nada oculto)

| Capacidad | Código | Tests | En vivo | Puerta |
| --- | --- | --- | --- | --- |
| Backtest | `lib/backtest.py`, `run/backtest.py` | sí | no aplica | ninguna |
| Multi-estrategia | `lib/estrategias.py` | sí | solo ORB | backtest + papel |
| Ejecución papel | `lib/brokers.py` | sí | no | integrar en el flujo |
| Ejecución real | interfaz nula | sí | **no** | bróker API + aprobación |
| Nivel 2 | `lib/proveedores.py` | sí | **no** | proveedor de pago |
| ML | export de features | sí | **no** | 300–500 trades + walk-forward |
| Pre/post | solo documento | no | **no** | proyecto separado |
| Europa | solo documento | no | **no** | proyecto separado |

Un hueco documentado y con puerta no es un fallo oculto: es una decisión de ingeniería.

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

---

## 10. Veredicto

- El sistema actual es **bueno en disciplina y trazabilidad**, no en alpha.
- El backtesting es el siguiente paso correcto: mide el patrón antes de añadir capas.
- Multi-estrategia es arquitectura; no crea ventaja por sí sola.
- Ejecución real, nivel 2 y ML **no** son el siguiente paso; serían saltarse la validación.
- Pre/post y Europa son **posibles**, pero son proyectos separados y con limitaciones de ejecución.
- La prioridad es una: **cerrar 30–50 operaciones, medir R neto y decidir con datos**.

---

## 11. Próximos pasos

1. Ejecutar el backtest del ORB en un universo amplio y revisar los resultados.
2. Comparar el backtest bruto con la señal filtrada.
3. Si el patrón no tiene ventaja ni bruto, no añadir capas: replantear.
4. Si la tiene, medir el efecto de cada filtro por separado.
5. Solo después: premarket, postmarket y Europa, cada uno con su estado y su muestra.
