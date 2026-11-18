# MERCADOS — donde se calcula y donde se ejecuta NVDA

Datos del **2026-11-18 06:0x Madrid** (Yahoo, 60 sesiones de 5 min y 20 de diarias).
Artefacto: `trader-ops/state/mercados_nvda.json`. Reproducible con `/mercados NVDA`.

## 1. Lo que se comparo

| | NVDA (Nasdaq) | NVD.DE (Xetra) |
| --- | --- | --- |
| Divisa | USD | EUR |
| Ultimo precio | 155,46 USD | 139,40 EUR = **153,19 USD** (EUR/USD 1,0989) |
| Volumen medio 20 d | 220,6 M acciones | 383.373 acciones |
| Dolares negociados/dia | **34.295 M USD** | **53,4 M EUR** (58,7 M USD) |
| Rango proxy 5 min (mediana H-L) | 0,498 % | 0,298 % |
| Sesiones de 5 min usadas | 59 | 60 |
| Horario (Madrid) | 15:30–22:00 | 09:00–17:30 |

**Liquidez: NVDA mueve 584 veces mas dolares al dia que NVD.DE.**
El "spread proxy" es la mediana del rango (maximo−minimo) de las barras de 5 min, **no el bid-ask**
(Yahoo no da bid-ask gratis). NVD.DE sale mas bajo porque se mueve menos, no porque sea mas barato
operarlo: con 53 M EUR/dia, una orden de 3.000 USD ya es relevante.

## 2. Precio y seguimiento

- Diferencia de precio tras convertir: **−1,46 %** (NVD.DE cotiza un 1,46 % por debajo de NVDA en USD).
- Correlacion de retornos de 5 min emparejados por hora de pared: **0,859**. Alta, pero no es el mismo activo.
- **Hueco de apertura europeo frente al cierre americano previo**: mediana **−3,02 %**
  (p5 −6,83 %, p95 −0,28 %, n=60). Es decir: entre el cierre de Nueva York y la apertura de Xetra,
  el precio europeo se ha movido una mediana de 3 puntos porcentuales. Eso no es un hueco explotable:
  es la prima/descuento estructural del listado europeo mas el movimiento overnight.

## 3. ¿La señal es replicable en Europa?

Regla ORB (primer cierre de 5 min por encima del maximo de las 3 primeras barras) aplicada a cada
sesion, en cada mercado:

| | dias |
| --- | --- |
| Dias comunes | 58 |
| Dispara en **ambos** | 30 |
| Dispara **solo en EE. UU.** | 1 |
| Dispara **solo en Europa** | 24 |

Que dispare "solo en Europa" 24 veces no es una ventaja: el rango europeo es 9:00–9:15 CET, tres horas
antes del americano, y el motor del skill **no calcula ese rango** (filtra las barras a 9:30–16:00 NY).
Son señales distintas sobre el mismo subyacente, no la misma señal ejecutada en otro sitio.

## 4. Horarios reales (fuente oficial)

- **NYSE/Nasdaq**: 9:30–16:00 ET. En Madrid: **15:30–22:00** (la diferencia es 6 h en invierno y
  6 h en verano porque ambos cambian de hora, pero no el mismo dia: entre el 25-oct y el 1-nov y en
  marzo hay una semana con 5 h). MyInvestor lo publica como "15.30 a 22.00 h de España".
- **Xetra**: 9:00–17:30 CET, **9:00–17:30 Madrid** (misma zona).
- Cierre anticipado NYSE (13:00 ET = 19:00 Madrid): 27-nov-2026, 24-dic-2026.
- Festivos: tabla NYSE verificada hoy en nyse.com para 2026–2028 (Accion de Gracias 26-nov-2026,
  cierre anticipado el 27). Xetra: tabla propia en `lib/calendario.py`, marcada como no verificada
  hoy contra Deutsche Boerse.

## 5. MyInvestor: que se puede hacer de verdad

Fuente: `myinvestor.es/inversion/broker`, leido **2026-11-18**.

- **Mercados disponibles**: NDQ (Nasdaq), NYS (NYSE), XTR (Xetra), FFT (Frankfurt), PAR, AEX, LSE,
  BME, etc. NVDA en NDQ y NVD.DE en XTR: los dos contratables.
- **Comisiones (acciones)**: **0,12 %** por operacion, **minimo 3 EUR**, **maximo 25 EUR**.
  **+0,30 % de cambio de divisa** si la cuenta esta en EUR y el valor en USD.
  Sin custodia, mantenimiento, inactividad ni cobro de dividendos.
- **Tipos de orden**: **limitada** y **"mejor de mercado"**. No hay bracket ni OCO.
- **Stop loss**: disponible en **NYSE, Nasdaq y Xetra**, vigencia maxima **60 dias**, y cuando se
  alcanza el precio **se lanza una venta a mejor de mercado**: el precio de venta **no esta garantizado**.
- **Sin fracciones de accion.**
- **Retencion de dividendos**: 15 % en origen con W-8BEN (no aplica a day trading).

### Como se reproduce un bracket sin bracket

1. Compra **limitada** al precio de entrada (o mejor de mercado si se acepta el deslizamiento).
2. Al ejecutarse, poner **stop loss** al precio del plan (el broker lo acepta en NDQ/NYS/XTR).
3. El objetivo **no se puede dejar como orden OCO**: se vigila con las alertas de este sistema y se
   vende a mano con una **limitada** al objetivo.
4. A las 15:55 ET, si sigue abierto: vender a mejor de mercado. Nunca dejar la posicion al dia siguiente.

Consecuencia practica: el stop del broker y el objetivo del plan **no son simetricos** en ejecucion.
El stop puede llenarse peor (medido: mediana 0,064 %, peor 0,185 % en NVDA). El objetivo, si se
ejecuta con limitada, puede no llenarse nunca.

## 6. Recomendacion

**Calcular y ejecutar en EE. UU. (NVDA, mercado NDQ).**

Razones, en orden:

1. El motor del skill es neoyorquino por construccion (rango 9:30–9:45 ET, calendario NYSE, flat 15:55 ET).
   Sobre el grafico europeo no calcula nada utilizable.
2. Liquidez 584 veces mayor: el tamaño de 8 acciones no mueve el precio en NVDA; en NVD.DE tampoco,
   pero el spread relativo y la profundidad son de otra liga.
3. El listado europeo lleva una prima/descuento del −1,46 % y un hueco overnight del −3 % de mediana:
   mezclar niveles USD con precios EUR sin conversion es un error garantizado.

**Europa solo como referencia**, y si algun dia se ejecuta alli:
- convertir **explicitamente** cada nivel con el EUR/USD del momento y marcarlo en el mensaje;
- no reutilizar el rango de 9:30–9:45 NY: habria que recalcular 9:00–9:15 CET con codigo propio;
- asumir que la señal no es la misma, solo el subyacente.

## 7. Alpaca: por que NO esta y que haria falta

No esta contemplado **a proposito**. La regla 1 del encargo dice: "Solo papel. Nunca ejecutes ni
prepares ordenes reales; no configures Alpaca ni claves de broker". El sistema cumple esa regla:
`"broker": "none"`, sin claves, y `ticket.py` solo imprime.

Que aportaria Alpaca (cuenta **paper**, sin dinero real):

- ejecucion automatica de la orden bracket (entrada + stop + objetivo OCO), que MyInvestor no tiene;
- registro de fills reales del simulador, con lo que el P&L y el deslizamiento dejarian de estimarse;
- un ledger objetivo para el registro vivo de señales.

Que costaria:

- una cuenta y **claves de broker** (secretos nuevos, fuera del repo);
- solo mercado EE. UU. (no Xetra), y comisiones distintas de MyInvestor;
- cambiar la regla 1, que es decision de Javier, no del agente.

**Recomendacion**: mantenerlo como esta (manual en MyInvestor, papel en el sistema). Si Javier
quiere medir ejecucion real, la opcion intermedia es Alpaca **solo paper** como libro de fills, nunca
dinero real, y con las claves en variables de entorno. Eso requiere su aprobacion explicita y un
cambio documentado de la regla 1.

## 8. Si ejecutas en Xetra (tu caso con NVDA)

Tu cuenta compra en euros y NVDA la tienes en Xetra (NVD.DE). Eso cambia el cálculo, no la señal:

| | Xetra (NVD.DE) | EE. UU. (NVDA en NDQ/NYS) |
| --- | --- | --- |
| Horario Madrid | 09:00–17:30 | 15:30–22:00 |
| Solape con la sesión NYSE | **15:30–17:30 (2 h)** | toda (6,5 h) |
| Divisa | EUR (sin cambio) | USD (0,30 % por lado) |
| Coste ida+vuelta (2.900 USD) | ~7 USD | ~24 USD |
| Flat by close del plan (21:55) | **Xetra lleva 4 h 25 m cerrado** | sí |

Consecuencias, sin adornos:

1. **Una SEÑAL A con disparo después de las 17:15 Madrid no es ejecutable en Xetra.** El plan pide
   aguantar hasta stop, objetivo o 15:55 ET; Xetra cierra antes.
2. **Si sales a las 17:30 para no dejarlo abierto, las odds del Time Machine ya no valen**: la
   simulación mide hasta las 15:55 ET (21:55 Madrid), no hasta las 11:30 ET.
3. **Entrar en Xetra y salir en Xetra el mismo día es un trade de 1 h 40 m como máximo**, con el
   stop del plan puesto. Es más barato (te ahorras 0,30 % por lado) pero es otro trade.

Recomendación por tipo de operación:

- **Day trading (lo que avisa el sistema)**: ejecuta en **EE. UU.** (NDQ/NYS). El plan, el stop, el
  objetivo y las odds están calculados para esa sesión. Pagas el cambio, pero el trade es el del modelo.
- **Tu NVDA actual**: es una posición de largo plazo comprada en Xetra. **No es una señal** y la regla
  de flat by close no se le aplica. Si quieres, regístrala con `/entre NVDA precio acciones` solo para
  tener avisos de stop/objetivo; si no, déjala fuera del libro de day trading.
- **Nunca mezcles**: un nivel en USD del plan no se traslada a EUR sin convertir y marcarlo.

El MCP de MyInvestor confirma que NVDA está en catálogo (XNAS/USD y NVD.DE/EUR), así que las dos vías
son contratables. La diferencia es de reloj, no de producto.


- **MCP de MyInvestor**: disponible y conectado el 2026-11-18 (`https://mcp.myinvestor.es/mcp`,
  herramienta `search_stocks` / `get_instruments`). Comprobado en vivo:
  `NVDA` → NVIDIA Corporation, ISIN US67066G1040, mercado primario **XNAS (Nasdaq)**, divisa **USD**,
  y la ficha añade que **también cotiza en NVD.DE (EUR)**. Un ticker inventado (`ZZZZQ`) no aparece.
  Queda por verificar valor por valor el resto de la lista, que se hace bajo demanda.
- No hay dato de bid-ask real: el "spread" es un proxy de rango y asi se etiqueta en cada mensaje.
- Los horarios de Xetra no se verificaron hoy contra la web oficial (tabla propia marcada).
- El MCP se usa **solo en lectura y bajo demanda** (una ficha por valor, cache 6 h). No se vuelca el
  catalogo ni se consulta en bucle: sus condiciones de uso no lo permiten.

## 9. Lo que no se pudo verificar

- **MCP de MyInvestor**: conectado y verificado el 2026-11-18: NVDA en XNAS/USD y NVD.DE/EUR; un ticker inventado no aparece. Uso solo lectura y bajo demanda.
- **Bid-ask real**: no hay dato gratis; se usa el proxy de rango y se etiqueta.
- **Calendario Xetra**: tabla propia, no verificada hoy contra Deutsche Boerse.
- **MCP y condiciones de uso**: prohibido volcar el catalogo o consultarlo en bucle.
