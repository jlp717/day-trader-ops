# CRITERIOS — que se avisa, que no, y por que

Escrito **antes** de la primera sesion y no se relaja despues.
Los umbrales viven en `trader-ops/lib/criterios.py` (`UMBRALES`). Si cambian, cambia este
documento en el mismo commit y queda en el diario.

## 1. Una SEÑAL A exige TODO esto

| # | comprobacion | umbral | de donde sale |
| --- | --- | --- | --- |
| 1 | setup disparado | `entry.py` = `triggered`, cierre de barra de 5 min por encima del maximo del rango | trader-entry |
| 2 | ventana | 09:45–15:30 ET (12:30 en cierre anticipado) | `config.json` |
| 3 | noticias adversas | ninguna en 24 h (halt, quiebra, delisting, restatement, offering, recall, breach, hack, lawsuit, investigation, fraude, guidance cut, miss) | trader-news |
| 4 | resultados | ningun titular/8-K de resultados en 30 h | trader-news (limitacion: no hay calendario de resultados gratuito; se bloquea de mas) |
| 5 | plan de salida | stop < entrada < objetivo, R:R >= `min_reward_risk` (1.0) | trader-exit |
| 6 | risk | `trader-risk` PASS con el tamaño real | trader-risk |
| 7 | frescura | edad del ultimo dato <= **300 s** | datos.quote |
| 8 | calidad | precio >= **5 USD**, volumen medio 20 d x precio >= **20 M USD/dia**, rango proxy 5 min <= **0,80 %** | datos.calidad |
| 9 | contratable | ticker US simple; mercado en el catalogo documentado de MyInvestor (NDQ/NYS) | MERCADOS.md |
| 10 | Time Machine | P(objetivo primero) > P(stop primero) **y** > break-even 1/(1+R) | trader-timemachine |
| 11 | historico | n >= **12** disparos, objetivos > stops, **limite inferior de Wilson** de la tasa de objetivo > break-even | calculado aqui |
| 12 | EV | `min(EV_MC, EV_hist) - coste_R` > 0 | calculado aqui |
| 13 | ruido | <= 2 A/hora, <= 2 A/valor/dia, <= 3 A/dia, enfriamiento 30 min | registro |
| 14 | presupuesto | suma de perdidas maximas de las A del dia + esta <= `max_daily_loss_usd` (100 USD) | config |
| 15 | deriva | precio actual <= entrada + 0,5R y > stop; si no, **SEÑAL CADUCADA** | segunda lectura |

`VIGILAR`: solo falla historial/ruido/presupuesto/noticias/resultados → se guarda, no se envia.
`DESCARTADA`: falla cualquier critico, con el motivo exacto.

## 2. Por que 2R y no 1R

El objetivo estandar es **2R**. Razon aritmetica, no estetica:

- Con 1R, el break-even es 50 % de objetivo-primero. Con 2R, 33,3 %.
- El coste de ida y vuelta en este broker es **fijo en dolares**, asi que en multiplos de R pesa
  la mitad con 2R que con 1R.

Medido en el ensayo (TSLA, 19-oct-2026, 8 acciones, 2.913 USD):

| concepto | valor |
| --- | --- |
| perdida maxima al stop | 46,88 USD = 1,00R |
| comision MyInvestor 0,12 % x 2 (min 3 EUR) | 6,99 USD |
| cambio de divisa 0,30 % x 2 (cuenta en EUR) | 17,48 USD |
| **coste total** | **24,47 USD = 0,522R** |
| con cuenta en USD (sin FX) | 6,99 USD = 0,149R |

Con 1R, el coste se come **la mitad del R**. Con 2R, una cuarta parte. Esa es la razon del 2R, y
tambien la razon de que casi nada pase el filtro: es la realidad del broker, no un fallo del filtro.
Si Javier confirma cuenta en USD, se pone `"cuenta_eur": false` y el liston baja a lo que de verdad
cuesta operar.

## 3. Frecuencias, no promesas

- La "probabilidad" del Time Machine es la frecuencia con la que el objetivo se toco antes que el
  stop en 10.000 repeticiones construidas con las ultimas 59 sesiones completas. No es una
  probabilidad de ganar.
- El historico es la misma regla sobre sesiones reales; se muestra con n y con intervalo de Wilson
  al 95 %.
- El mensaje nunca dice "probable": dice "objetivo primero X %, stop Y %, n = N".

## 4. Sesgo de seleccion, dicho en cada informe

El scanner recorre ~5.900 valores y devuelve los que cumplen una regla. Quedarse con los mejores
es un sesgo. Por eso cada informe diario dice: valores escaneados, candidatos, evaluados, A, VIGILAR
y descartadas. Y cada mensaje lleva el n del historico del valor concreto.

## 5. Ruido y riesgo

- Maximo 2 A por hora, 2 por valor y dia, 3 por dia.
- Enfriamiento de 30 minutos entre A.
- Presupuesto: la suma de perdidas maximas de las A del dia no puede pasar de 100 USD.
- Al llegar al limite, no se envian mas A ese dia; se sigue informando.

## 6. Freno por evidencia

El registro vivo cuenta objetivos, stops y R medio de las A enviadas. Cuando haya **12 cerradas**:

- Si el R medio <= 0, se dejan de enviar A y se avisa. Solo Javier lo reactiva (`/reanudar` no basta:
  hay que editar `state/registro.json` o pedirlo en OpenCode).
- Si la tasa de objetivo es claramente inferior a la que prometia el Time Machine (mas de 15 puntos
  porcentuales por debajo), tambien se avisa y se para.

Mientras haya menos de 12 cerradas, cada aviso lleva **SIN HISTORIAL VALIDADO**.

## 7. Contrato de calidad del aviso

Antes de enviar, `lib/texto.validar` comprueba:

a) **Trazabilidad**: cada cifra con origen debe aparecer literalmente en la salida del comando que
   la produjo (guardada en `logs/diario.jsonl` con su hash). Si no, no se envia y se registra
   `validacion_fallida`.
b) **Frescura**: edad <= 300 s.
c) **Segunda lectura**: inmediatamente antes de enviar se vuelve a pedir precio; si se alejo mas de
   0,5R o ya esta en el stop, se envia como **SEÑAL CADUCADA** (o no se envia).
d) **Ruido y riesgo**: los limites de §5.
e) **Confianza honesta**: n, tasa, Wilson y registro vivo en cada mensaje.
f) **Freno**: §6.
g) **Resumen diario**: siempre, incluso con cero señales.

## 8. Lo que este sistema NO hace

- No envia ordenes. No hay broker conectado (`"broker": "none"`).
- No usa el LLM para decidir ni para redactar cifras. El bot y el orquestador son deterministas.
- No relaja filtros si no hay señales. Cero señales es un resultado valido y se reporta como tal.
