# ROADMAP — fases del sistema

Fecha: 20/11/2026. Este documento responde a una pregunta concreta: **qué está hecho, qué se está
haciendo y qué queda**, sin mezclar deseos con realidad.

Reglas que no cambian: solo papel, el skill vendido no se toca, cada flujo tiene su estado y su
P&L, y ninguna fase se considera "viva" sin muestra propia.

Leyenda: **DONE** = cerrado y con test · **IN PROGRESS** = hay código, falta validación o
integración · **PARTIAL** = hay una parte gratis/legal, la otra no · **BLOCKED** = depende de algo
externo o de una decisión humana · **SEPARATE** = otro proyecto, no una pestaña más.

---

## 1. Tabla de fases

| Fase | Estado | Qué hay | Qué falta / puerta |
| --- | --- | --- | --- |
| **0. Base de papel** | **DONE** | motor, Telegram, paneles, manual, 144 tests | nada |
| **1. Datos y contraste** | **DONE** | Yahoo + CNBC + Finnhub; cross-check 0,5 % | nada crítico |
| **2. Medición / backtest** | **DONE** como herramienta | ORB configurable, costes, slippage, IS/OOS, features | validar la estrategia con 30–50 trades |
| **3. Multi-estrategia** | **DONE (medida)** | `orb`, `orb_low`, `gap_reclaim`, swing RSI-2 | las tres hipótesis nuevas pierden con costes; falta una con ventaja |
| **4. Ejecución de papel** | **IN PROGRESS** | `PaperBroker` local; `AlpacaPaperBroker` disponible pero no se usa (broker: MyInvestor) | integrarla en el flujo o dejarla manual |
| **5. Nivel 2 / microestructura** | **PARTIAL** | IEX top-of-book gratis (bid/ask/tamaño) | L2 completo: proveedor de pago |
| **6. Machine learning** | **BASELINE DONE** | logística walk-forward, features, AUC 0,269 | 300–500 trades; hoy no hay señal |
| **7. Pre/post market** | **ANÁLISIS DONE** | `run/prepost.py`, radar, `/pre`, `/post`, estado separado | ejecución: MyInvestor no la permite |
| **7c. Radar automático** | **DONE** | tareas `DayTraderOps-PreRadar` (13:10) y `-PostRadar` (22:05), envío Telegram | nada |
| **7d. Vigilante rápido** | **DONE** | `run/vigia.py`: niveles cada 30 s, tarea `DayTraderOps-Vigia` (15:25), se cierra solo | nada |
| **8. Europa** | **SEPARATE** | documentado | otro horario, bróker, datos y fiscalidad |
| **9. Ejecución real** | **BLOCKED** | interfaz y modo papel | bróker fondeado + límites + aprobación |
| **10. Ops y documentación** | **DONE** | README, REFERENCIA, manual 91 pág., tareas | nada |

---

## 2. Lo que está cerrado de verdad

### Fase 0 — Base

- Orquestador, bot, watchdog y paneles.
- Registro, alertas, informes, manual.
- 144 tests propios + 315 del skill.
- Vendor intacto en `vendor/day-trader-skill` (snapshot, sin `.git` anidado).

### Fase 1 — Datos

- Yahoo: velas 5m/1d, pre/post con `includePrePost`.
- CNBC: segundo testigo público.
- Finnhub: tercer testigo con clave gratuita.
- Si difieren >0,5 %: no se envía señal y se avisa con los valores.

### Fase 2 — Backtest

- `run/backtest.py` con rango, target, stop mid/low, slippage, split IS/OOS, filtro por coste,
  CSV/JSON y features.
- Resultado inicial: **el ORB bruto pierde** (292 trades, 18,8 %, −310R). El subconjunto con
  coste ≤0,5R también pierde (42 trades, 33,3 %, −17R).
- **Prueba de robustez (20/11)**: 40 valores, 60 sesiones, **1.264 trades → −1.650R**. **Sin costes
  también pierde** (−79R a 1R y −91R a 2R) con 46,4 % de acierto frente al 50 % necesario.
  **Hipótesis falsificada**: el problema no son las comisiones, es el patrón.
- Conclusión: el patrón bruto no es una ventaja; los filtros son la única esperanza y no están
  validados.

### Fase 4 — Papel (parcial)

- `PaperBroker` local: rellena, audita e idempotencia.
- `AlpacaPaperBroker`: cuenta **paper** verificada (ACTIVE, 100.000 USD simulados).
- `run/orden.py`: dry-run y envío paper con `--confirm`.
- **No integrado** en el bot: el flujo vivo sigue siendo manual. Esa integración es la fase 4b.

### Fase 5 — Microestructura (parcial)

- `run/libro.py --proveedor alpaca_iex`: bid/ask y tamaños (IEX, profundidad 1).
- Spread calculado; aviso si es anómalo.
- **L2 completo no es gratis** para acciones US. Polygon/Databento son de pago. No se inventa.

### Fase 6 — ML (baseline)

- `lib/ml.py` + `run/ml.py`: logística sin dependencias, estandarización, L2, walk-forward.
- Resultado: accuracy 0,800, base 0,133, **AUC 0,269**. La accuracy engaña por desbalance; no hay
  señal.
- No se usa en producción. Con 300–500 trades se repite.

### Fase 7 — Pre/post (análisis)

- `run/prepost.py`: último precio, máximo, mínimo, variación y volumen (si Yahoo lo da).
- No ejecuta. MyInvestor no permite órdenes extendidas.

---

## 3. Lo que queda, en orden

### 4b. Piloto automático de papel (siguiente)

Objetivo: que el sistema pueda ejecutar **en papel** una SEÑAL A sin intervención, con las mismas
reglas y un kill switch.

Requisitos antes de escribirlo:

- 30–50 operaciones cerradas en manual, con R neto.
- Decidir broker: `PaperBroker` local o Alpaca paper.
- Límites duros: 1 orden por señal, 50 USD de riesgo, 150/día.
- Idempotencia por `client_order_id`.
- Kill switch y `--dry` por defecto.
- Auditoría de cada orden y conciliación con el fill.
- Revisión independiente.

No se hace antes de la muestra: automatizar una hipótesis no validada es escalar el error.

### 3b. Segunda estrategia real

`orb_low` es una variante, no una estrategia nueva. Para una segunda de verdad:

1. hipótesis escrita;
2. features y reglas;
3. backtest IS/OOS;
4. papel separado;
5. muestra propia.

Sin eso, "multi-estrategia" es solo arquitectura.

### 5b. Nivel 2 completo

Solo si se mide que el spread/impacto importa. Proveedores: Polygon (L2), Databento. Clave en
`secrets/polygon.json`; hoy no hay contrato. No es un gap de código: es una licencia.

### 6b. ML de producción

Con 300–500 trades etiquetados, walk-forward y costes. Hoy el baseline no supera el azar
(AUC 0,269); no se usa.

### 7b. Pre/post integrado

Análisis ya existe. Integrarlo en el bot con comandos `/pre` y `/post` y estado separado es
posible; la ejecución sigue bloqueada por MyInvestor.

### 8. Europa

Proyecto separado: Xetra, horario, spread, bróker, fiscalidad y datos. No se mezcla con EE. UU.

### 9. Ejecución real

Bloqueada. Requiere bróker fondeado, límites, kill switch, auditoría y aprobación explícita. El
código actual no tiene endpoint real; Alpaca es solo paper.

---

## 4. Criterio de "hecho"

Una fase no está hecha por tener código. Está hecha cuando:

1. tiene tests;
2. tiene evidencia de ejecución real (no simulada) o de backtest;
3. tiene límites y reversión;
4. tiene muestra suficiente;
5. pasa una revisión independiente.

Con 0 operaciones cerradas, **ninguna fase de estrategia está validada**. La fase 2 está hecha
como herramienta; la estrategia, no.

---

## 5. Claves y archivos

| Cosa | Dónde |
| --- | --- |
| Alpaca paper | `secrets/alpaca.json` (`api_key`, `secret_key`) |
| Finnhub | `secrets/finnhub.json` |
| Polygon (futuro) | `secrets/polygon.json` |
| Telegram / SEC | `secrets/telegram.json`, `secrets/sec.json` |
| Backtest | `run/backtest.py` |
| Papel | `run/orden.py`, `lib/brokers.py` |
| Libro IEX | `run/libro.py`, `lib/proveedores.py` |
| ML | `run/ml.py`, `lib/ml.py` |
| Pre/post | `run/prepost.py`, `lib/prepost.py` |
| Referencia | `REFERENCIA.md` |

---

## 6. Próximos 30 días

1. Mantener el bot vivo y cerrar 30–50 operaciones en papel.
2. Medir R neto, acierto y drawdown; no añadir capas.
3. Usar el backtest para probar subconjuntos (coste, hora, rango), no para buscar el mejor pasado.
4. Observar pre/post a diario; no ejecutar.
5. Decidir 4b (piloto paper) solo con muestra positiva.
6. No tocar ejecución real, L2 de pago ni Europa hasta que 1–5 estén cerrados.

La frase que resume el estado: **la ingeniería está lista; la ventaja no está demostrada.** El
siguiente trabajo es medir, no acumular funciones.
