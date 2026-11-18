import html
import json
import re
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parent
READ = json.loads((AQUI / "salidas_readonly.json").read_text(encoding="utf-8"))


def pre(t):
    t = re.sub(r"</?(b|code|pre)>", "", t)
    t = html.unescape(t)
    return "<pre>%s</pre>" % html.escape(t.strip("\n"))


def bloque(cmd, cuando, texto, revisar):
    return ("<h3><code>%s</code></h3>\n<p><b>Cuándo</b>: %s</p>\n%s\n"
            "<p><b>Qué revisas</b>: %s</p>\n" % (html.escape(cmd), cuando, pre(texto), revisar))


PARTES = []
PARTES.append("""<h1 id="s22">22. Salidas exactas de los comandos</h1>
<p>Este capítulo es la referencia literal: qué escribe el sistema y qué tienes que mirar. Las salidas de estado
son reales del <b>18/11/2026 a las 09:12 Madrid</b>, con el mercado cerrado; los números cambiarán en sesión, pero
la estructura es la misma. Las salidas de <code>/entre</code>, <code>/sali</code>, <code>/stop</code>,
<code>/vender</code> y <code>/alerta</code> son una <b>simulación con estado temporal</b> del Día 8: no tocan tu
estado real y los ids de alerta cambian en cada ejecución.</p>
<div class="warn">
<b>El bot recorta a ~4.000 caracteres</b> para no superar el límite de Telegram. Ninguna de estas salidas llega a
ese límite; si un día se recorta, el detalle completo queda en <code>logs/diario.jsonl</code>.
</div>

<h2>22.1. Operar a mano: /entre, /sali, /stop, /vender, /alerta</h2>
<p><b>Sintaxis exacta</b> (lo que va después del comando, separado por espacios):</p>
<table>
<tr><th>Comando</th><th>Argumentos</th><th>Ejemplo</th></tr>
<tr><td><code>/entre</code></td><td><code>TICKER PRECIO_FILL ACCIONES STOP OBJETIVO</code></td><td><code>/entre SLS 20.12 87 19.55 21.26</code></td></tr>
<tr><td><code>/sali</code></td><td><code>TICKER PRECIO_FILL [ACCIONES]</code> (sin acciones = todo)</td><td><code>/sali SLS 21.26</code> · <code>/sali SLN 20.20 20</code></td></tr>
<tr><td><code>/stop</code></td><td><code>TICKER NUEVO_STOP</code></td><td><code>/stop SLS 19.80</code></td></tr>
<tr><td><code>/vender</code></td><td><code>TICKER NUEVO_OBJETIVO</code></td><td><code>/vender SLS 21.50</code></td></tr>
<tr><td><code>/alerta</code></td><td><code>TICKER NIVEL</code></td><td><code>/alerta SLS 21.00</code></td></tr>
<tr><td><code>/posiciones</code>, <code>/alertas</code>, <code>/pnl</code></td><td>sin argumentos</td><td><code>/posiciones</code></td></tr>
</table>
<p><b>De dónde sale cada valor</b>:</p>
<table>
<tr><th>Dato</th><th>De dónde</th></tr>
<tr><td><b>Ticker</b></td><td>La SEÑAL A (o tu decisión, si operas fuera de señal).</td></tr>
<tr><td><b>Precio del fill</b></td><td>La confirmación de MyInvestor, no la pantalla retrasada. Es el precio al que se ejecutó de verdad.</td></tr>
<tr><td><b>Acciones</b></td><td>El tamaño del plan (87 en el ejemplo). Si lo ajustas, recalcula el riesgo: (fill − stop) × acciones.</td></tr>
<tr><td><b>Stop</b></td><td>El plan: mid del rango, redondeado abajo (19,55).</td></tr>
<tr><td><b>Objetivo</b></td><td>El plan: 2R (21,26).</td></tr>
</table>
<div class="warn">
Si el valor no tiene una SEÑAL A de hoy, <code>/entre</code> lo registra igual, pero la última línea dirá
<b>FUERA DE SEÑAL A</b>. Es una operación manual: el sistema la apunta, no la valida.
</div>
""")

PARTES.append(bloque(
    "/ENTRE SLS 20.12 87 19.55 21.26",
    "inmediatamente después de que MyInvestor te confirme el fill de compra. No antes: el sistema registra lo que ha pasado, no lo que esperas.",
    """Registrada: SLS 87 acc a 20.12. Stop 19.55, objetivo 21.26.
Avisos armados: stop 19.55, objetivo 21.26. Solo hoy (fecha de Nueva York).
Estado: SEÑAL A vigente hoy desde las 16:05.""",
    "que la cantidad, el precio y los niveles sean exactamente los del fill; que diga <b>Avisos armados</b>; y que el estado sea SEÑAL A. Si aparece un <b>AVISO</b> de riesgo por encima de 50 USD, reduce cantidad o acepta el exceso a sabiendas."))

PARTES.append(bloque(
    "/POSICIONES",
    "para ver qué tienes abierto y con qué niveles. Úsalo antes de mover algo o cuando dudes.",
    """<b>Posiciones abiertas</b>
  SLS 87 acc desde 20.12 · stop 19.55 · objetivo 21.26""",
    "que la cantidad y los niveles coincidan con tu broker. Si no, corrige con <code>/sali</code> y vuelve a registrar, o ajusta con <code>/stop</code>/<code>/vender</code>."))

PARTES.append(bloque(
    "/ALERTAS",
    "para comprobar que los avisos de stop y objetivo están armados, y que no hay alertas viejas.",
    """<b>Alertas de hoy</b> (2)
  pos-8adb8c78-stop · SLS · stop 19.55
  pos-8adb8c78-target · SLS · target 21.26""",
    "que aparezcan las dos reglas de la posición (stop y target) y solo las que quieres. El id <code>pos-...</code> es interno; cambia con cada posición."))

PARTES.append(bloque(
    "/STOP SLS 19.80",
    "cuando quieras subir el stop de una posición abierta (por ejemplo, a break-even después de +1R).",
    """Stop de SLS movido a 19.80 y aviso rearmado. Antes: 19.55.""",
    "que el “Antes” sea el nivel viejo y el nuevo sea el que querías. <b>Esto mueve el aviso del sistema, no la orden stop loss de MyInvestor</b>: si tienes una orden en el broker, cámbiala también."))

PARTES.append(bloque(
    "/VENDER SLS 21.50",
    "cuando quieras mover el objetivo de una posición abierta, o dejar un aviso de venta si no tienes posición.",
    """Objetivo de SLS movido a 21.50 y aviso rearmado. Antes: 21.26.""",
    "que el nuevo objetivo sea el que quieres y que el “Antes” coincida. Si no tienes posición, el mismo comando deja un aviso para hoy y lo dice distinto (ver 22.4)."))

PARTES.append(bloque(
    "/ALERTA SLS 21.00",
    "para un nivel puntual que no es stop ni objetivo: “avísame si pasa de 21,00”. Solo hoy.",
    """Alerta puesta para hoy: SLS por encima de 21.00.""",
    "que el nivel y el sentido sean correctos. No es una orden: solo avisa. Si quieres que sea persistente, no existe: las alertas son de hoy."))

PARTES.append(bloque(
    "/SALI SLS 21.26",
    "inmediatamente después del fill de venta total.",
    """Cerrada SLS: 87 acc a 21.26, P&L bruto +99.18 USD (2.0 R). Alertas de stop y objetivo desarmadas. No descuenta comisiones ni FX.""",
    "que la cantidad sea toda la posición, que el P&L bruto cuadre con (salida − entrada) × acciones y que diga <b>Alertas desarmadas</b>. El neto es el bruto menos el coste del aviso (~17 USD en este ejemplo)."))

PARTES.append(bloque(
    "/SALI SLN 20.20 20   (cierre parcial)",
    "cuando vendas solo una parte. La cantidad es la que vendes, no la que queda.",
    """Cierre parcial de SLN: 20 acc a 20.20, P&L bruto +8.00 USD (1.0 R). Quedan 40 acc; stop 19.40 y objetivo 20.60 siguen armados. No descuenta comisiones ni FX.""",
    "que “Quedan” sea la cantidad correcta y que los avisos sigan armados. Si el parcial era para asegurar, puedes mover el stop del resto con <code>/stop</code>."))

PARTES.append(bloque(
    "/POSICIONES   (después del parcial)",
    "para confirmar que la posición reducida sigue viva y con sus niveles.",
    """<b>Posiciones abiertas</b>
  SLN 40 acc desde 19.80 · stop 19.40 · objetivo 20.60""",
    "que la cantidad sea la que queda (40), no la original (60). Si no, el parcial se registró mal."))

PARTES.append(bloque(
    "/PNL",
    "al final del día o cuando quieras el acumulado. Es bruto: no descuenta comisiones ni FX.",
    """<b>P&L</b>
Posiciones a mano: 1 cerradas, +99.18 USD bruto, 1 ganadoras / 0 perdedoras
Señales papel: 0 cerradas, 0 objetivos, 0 stops, R medio +0.00
El P&L a mano es bruto: no descuenta comisiones ni FX. El aviso de cada señal trae el coste.""",
    "que el número de cerradas y el P&L coincidan con tus operaciones. El P&L de “señales papel” es otro libro: el del sistema, no tus fills."))

PARTES.append("""<h2>22.2. Estado y contexto: /estado, /ahora, /reloj, /hoy, /resumen, /registro, /diario, /vigilar, /descartadas, /ayuda</h2>
<p>Salidas reales del 18/11 a las 09:12, mercado cerrado. En sesión cambian los números y algunas líneas; el
formato es el mismo.</p>
""")

READ_DESC = {
    "/estado": ("para saber si el orquestador está vivo, si hay pausa, cómo va el registro y las posiciones.", "que diga <b>vivo</b>, el latido reciente, <b>Pausa: no</b> y el freno en <b>no</b>. Si el latido es viejo, no operes."),
    "/ahora": ("para saber en qué fase estás, qué hace el sistema y cuál es el próximo evento.", "la fase, lo que se espera de ti y la cuenta atrás. Si dice “antes del premarket”, no hay nada que comprar."),
    "/reloj": ("para confirmar el desfase Madrid/NY y la sesión de hoy.", "que el desfase sea 6 h (o 5 h en semanas de cambio) y que la sesión sea la correcta."),
    "/hoy": ("para ver candidatos antes de abrir o rupturas después de las 15:50.", "que la fecha del scan sea de hoy/ayer y que la tabla tenga los valores que esperas. Un candidato no es una compra."),
    "/resumen": ("para saber si hay SEÑAL A, posiciones y límites del día.", "que diga claramente si hay o no SEÑAL A; si no, no se compra nada."),
    "/registro": ("para ver el registro vivo de señales papel, no tus posiciones.", "cerradas, objetivos, stops, R medio y freno. Con 0 cerradas, no hay historial validado."),
    "/vigilar": ("para ver la watchlist fija con precio y edad del dato.", "que la edad sea razonable; si es de horas, es el último cierre."),
    "/descartadas": ("para ver las evaluaciones de hoy que no fueron SEÑAL A.", "el motivo exacto; si no hay, es que no se ha evaluado nada."),
    "/ayuda": ("para el menú completo de comandos y frases.", "que exista el comando que buscas; si no, no existe."),
}

for cmd in ("/estado", "/ahora", "/reloj", "/hoy", "/resumen", "/registro", "/vigilar", "/descartadas", "/ayuda"):
    cuando, revisar = READ_DESC[cmd]
    PARTES.append(bloque(cmd, cuando, READ[cmd], revisar))

PARTES.append("""<h3>Control y watchlist</h3>
""")
PARTES.append(bloque(
    "/PAUSA",
    "para dejar de recibir SEÑAL A nuevas sin parar el orquestador.",
    "Pausado: no se envian SEÑAL A nuevas. El orquestador sigue recogiendo datos.",
    "que sea una pausa, no un parón: premarket, briefing, flat e informe siguen llegando. Para silencio total, para las tareas de Windows."))
PARTES.append(bloque(
    "/REANUDAR",
    "para volver a permitir SEÑAL A.",
    "Reanudado.",
    "que el panel deje de mostrar PAUSADO."))
PARTES.append(bloque(
    "/VIGILA SLS",
    "para añadir un valor a la watchlist fija (briefing, noticias y evaluación fija).",
    "Vigilando SLS. Lista: NVDA, SLS · precio 19.15",
    "que la lista sea la que quieres. No es la lista ORB del día; es la watchlist persistente."))
PARTES.append(bloque(
    "/DEJAR SLS",
    "para quitar un valor de la watchlist fija.",
    "Ya no vigilo SLS. Lista: NVDA",
    "que quede solo lo que quieres vigilar siempre."))
PARTES.append(bloque(
    "/DIARIO",
    "para ver los últimos 15 eventos del día (comandos, evaluaciones, errores).",
    """<b>Diario de hoy</b> (1114 eventos)
  09:14 cmd entry
  09:14 cmd news
  09:14 bot_cmd ticker
  09:14 cmd risk
  09:14 bot_cmd risk
  09:14 cmd broker
  09:14 bot_cmd ticket
  09:14 cmd pelosi
  09:14 bot_cmd pelosi
  09:14 cmd scanner
  09:14 bot_cmd scan
  09:14 bot_cmd ensenar
  09:14 bot_cmd ensenar
  09:14 bot_cmd ensenar
  09:14 bot_cmd ayuda""",
    "que no haya <code>error</code>, <code>validacion_fallida</code> ni <code>telegram_error</code>. En esta sesión hay 1.114 eventos porque hemos ejecutado muchas pruebas; en un día normal hay menos."))

PARTES.append("""<h2>22.3. Análisis y señales: /ganadores, /elegir, /resultados, /noticias, /mercados, /apertura, /tm, /plan, /tamano, /ticker, /risk, /ticket, /pelosi, /scan, /ensenar</h2>
<p>Salidas reales del 18/11 a las 09:12, mercado cerrado. Las que dependen de un disparo
(<code>/plan</code>, <code>/tm</code>, <code>/tamano</code>) dicen “sin plan” hasta que exista rango; es correcto.</p>
""")

READ_DESC2 = {
    "/ganadores 5": ("para ver los que más subieron ayer (o hoy en sesión), con liquidez.", "que la cabecera diga “de ayer” o “de hoy”; que el % y el $/día sean coherentes. No es una recomendación."),
    "/elegir NVDA": ("para el análisis completo de un valor, con criterios y SEC.", "el veredicto: SIN SEÑAL hasta que haya rango; si hay plan, entrada/stop/objetivo/EV."),
    "/resultados NVDA": ("para el último trimestre presentado a la SEC.", "periodo, formulario y fecha; no es una previsión."),
    "/noticias NVDA": ("para titulares de 24 h.", "si hay noticias adversas; si no, “sin noticias nuevas”."),
    "/mercados NVDA": ("para comparar EE. UU. con Xetra.", "si falla, el sistema lo dice: Yahoo no da barras intradía de NVD.DE. No inventa."),
    "/apertura NVDA": ("para el coste de esperar: hueco, primeros 15 min y % del movimiento.", "las medianas y la muestra; recuerda que es histórico, no una promesa."),
    "/tm NVDA": ("para el Time Machine de un valor.", "si no hay disparo, “sin datos suficientes”; es normal antes de abrir."),
    "/plan NVDA": ("para el plan de salida si hay disparo.", "si dice “waiting”, no hay plan; no se inventa."),
    "/tamano NVDA": ("para el tamaño propuesto y la pérdida máxima.", "si no hay plan, no hay tamaño."),
    "/ticker NVDA": ("para el resumen de la cadena, más corto que /elegir.", "setup, noticias y resultados; no aplica criterios."),
    "/risk": ("para PASS/BLOCK de las órdenes propuestas.", "si no hay órdenes, lo dice; no es el risk de tus posiciones manuales."),
    "/ticket": ("para el ticket en papel de la última orden propuesta.", "si no hay ticket, pide /plan y /tamano; nunca se envía."),
    "/pelosi": ("para PTR nuevos de Pelosi.", "contexto, nunca señal; llega tarde."),
    "/scan NVDA": ("para escanear solo ese valor ahora.", "precio y setup; no escribe la watchlist."),
    "/ensenar orb": ("para explicar un concepto.", "la definición; no es una señal."),
    "/ensenar r": ("para explicar R.", "que no te devuelva ORB por error; debe decir R."),
    "/ensenar senal a": ("para explicar SEÑAL A.", "la definición y el recuento de hoy."),
}

for cmd in ("/ganadores 5", "/elegir NVDA", "/resultados NVDA", "/noticias NVDA", "/mercados NVDA",
            "/apertura NVDA", "/tm NVDA", "/plan NVDA", "/tamano NVDA", "/ticker NVDA", "/risk",
            "/ticket", "/pelosi", "/scan NVDA", "/ensenar orb", "/ensenar r", "/ensenar senal a"):
    cuando, revisar = READ_DESC2[cmd]
    PARTES.append(bloque(cmd, cuando, READ[cmd], revisar))

PARTES.append(bloque(
    "/SEGUIR 5",
    "para añadir los 5 primeros ganadores de la lista actual a la lista ORB de hoy. Después de las 13:00 y, sobre todo, después de las 15:30.",
    """Ganadores anadidos al escaneo ORB: SLN, SLS, SGRY, REPL, GDYN.
Lista total: 5 valores. Se escanean cada 5 min y pasan por noticias, plan, Time Machine, tamano, risk y criterios.
No es una recomendacion ni una compra: si alguno rompe el rango y pasa todo, llegara como SEÑAL A.""",
    "que los tickers sean los que quieres y que la lista no se haya quedado corta. Antes de las 13:00, el premarket sobrescribe la lista; no lo uses todavía."))

PARTES.append(bloque(
    "/EVALUAR 1",
    "para ejecutar la cadena completa de los N primeros ganadores y ordenarlos por veredicto y EV. A partir de las 15:50, cuando ya existe rango.",
    """<b>Evaluacion bajo demanda</b> · 09:19 · 1 ganadores (de ayer)
No envia aviso ni toca el plan vivo. Solo mide.

#  Valor  Veredicto     EV R    n   obj MC
1  SLN    SIN SEÑAL       n/d    0   n/d

Motivo principal:
  SLN: the NYSE opens at 9:30 and the 15-minute range is set at 9:45

Esto es el veredicto de los criterios, no una recomendacion. Si un valor sale SEÑAL A aqui pero no llego aviso, no se opera: el aviso automatico manda.
Analisis completo de uno: /elegir NVDA""",
    "que la cabecera diga “de ayer” o “de hoy”; que los veredictos tengan sentido; y que “SIN SEÑAL” antes de abrir es normal. No es una compra."))

PARTES.append("""<h3>Precios multi-fuente</h3>
""")
PARTES.append(bloque(
    "/ELEGIR MNSO",
    "para analizar un ticker concreto bajo demanda, aunque no esté en la lista ORB. Antes de las 15:50 devuelve SIN SEÑAL; después, si rompe el rango, puede dar plan y veredicto.",
    """<b>MNSO · analisis completo</b> (bajo demanda, no envia aviso)
Setup: waiting. the NYSE opens at 9:30 and the 15-minute range is set at 9:45
Precio ahora: 12.18 (dato de hace 44679s · dato viejo: es el ultimo cierre, no un precio en vivo)
Noticias: sin adversas
Riesgo de resultados (proxy titular/10-Q): sin senal hoy/manana
Veredicto: <b>SIN SEÑAL</b> todavia. Sin ruptura no hay plan, tamaño ni probabilidades.
Que falta: que una vela de 5 min cierre por encima del maximo del rango (9:30-9:45 ET) dentro de la ventana de entrada.""",
    "que el ticker sea el correcto y que el precio sea el último cierre si el mercado está cerrado. SIN SEÑAL antes de abrir es normal: no hay rango. No es una compra."))

PARTES.append(bloque(
    "/INCLUIR MNSO",
    "para añadir un ticker concreto a la lista ORB de hoy, aunque no sea ganador ni esté en el scanner. No es una compra.",
    """Añadido al escaneo ORB de hoy: MNSO.
Lista total: 151 valores. Se escanea cada 5 min y pasa por noticias, plan, Time Machine, tamaño, risk y criterios.
No es una compra: si rompe el rango y pasa todo, llegará como SEÑAL A.
Si lo haces antes de las 13:00, el premarket reconstruye la lista y se pierde.""",
    "que el ticker sea el correcto y que la lista no se haya quedado corta. Antes de las 13:00 se pierde; úsalo después del premarket."))

PARTES.append(bloque(
    "/REF SLS 20.13 TV",
    "para guardar el precio que ves en TradingView (o Börse Frankfurt/Investing/MyInvestor) y compararlo con Yahoo.",
    """Referencia guardada: SLS 20.13 USD · TradingView · 09:55:02 Madrid.
Consulta /precios SLS para compararla con Yahoo y el plan.""",
    "que la fuente, el precio y la hora sean los que has visto. Yahoo ya entra solo; no lo apuntes a mano."))
PARTES.append(bloque(
    "/PRECIOS SLS",
    "para juntar Yahoo, tus referencias y el plan vigente; si hay diferencia >0,5 %, avisa.",
    """Precios SLS
Yahoo: 20.12 USD · 2026-12-01T15:05:20Z · hace 15s · NMS
TradingView: 20.13 USD · 09:55:02 Madrid · hace 0s
Diferencia entre fuentes: 0.15% (OK)
Plan vigente: no hay plan para SLS. El plan sale de la SEÑAL A.
Para /entre: usa el fill de MyInvestor, no esta tabla. Stop/objetivo salen del plan.""",
    "que las fuentes y horas sean las correctas; si dice AVISO >0,5 %, no operes a mercado. Si no hay plan, no hay entrada."))
PARTES.append(bloque(
    "/REF NVD.DE 139.40 BORSE",
    "para guardar el precio de Xetra que ves en la app oficial Börse Frankfurt.",
    """Referencia guardada: NVD.DE 139.40 EUR · Börse Frankfurt/Xetra · 09:55:02 Madrid.
Consulta /precios NVD.DE para compararla con Yahoo y el plan.""",
    "que sea Xetra y EUR, no Frankfurt/USD. Si el ticket de MyInvestor es otro venue, la diferencia puede ser real."))
PARTES.append(bloque(
    "/PRECIOS NVD.DE",
    "para comparar Yahoo con la referencia oficial de Xetra antes de vender o comprar.",
    """Precios NVD.DE
Yahoo: 139.35 EUR · 2026-12-01T15:05:20Z · hace 18s · GER
Börse Frankfurt/Xetra: 139.40 EUR · 09:55:02 Madrid · hace 0s
Diferencia entre fuentes: 0.04% (OK)
Plan vigente: no hay plan para NVD.DE. El plan sale de la SEÑAL A.
Para /entre: usa el fill de MyInvestor, no esta tabla. Stop/objetivo salen del plan.""",
    "que la referencia sea de Börse Frankfurt/Xetra y la hora reciente. Si el precio de MyInvestor es 144,94, no uses mercado: limitada al precio que aceptas."))

PARTES.append("""<h2>22.4. Errores y casos límite (salidas exactas)</h2>
""")

ERRORES = [
    ("/SALI SLS 21.26   (sin posición)", "cuando no hay posición abierta de ese valor.",
     "No hay posicion abierta en SLS.",
     "no hay nada que cerrar; no insistas. Revisa <code>/posiciones</code>."),
    ("/ENTRE SLS 20.12 87 20.50 21.26   (stop por encima)", "cuando el stop está por encima de la entrada.",
     "El stop (20.5) tiene que estar por debajo de la entrada (20.12).",
     "corrige el stop; el sistema no acepta un stop que no sea de pérdida."),
    ("/ENTRE SLS 20.12 87 19.55 21.26   (duplicado)", "cuando ya hay una posición abierta del mismo valor.",
     "Ya hay una posicion abierta en SLS. Cierrala o reduce con /sali antes de abrir otra. No se promedian posiciones a ciegas.",
     "no se promedia; cierra o reduce primero. Si quieres otra entrada, es otra operación y otro registro."),
    ("/STOP SLS 19.80   (sin posición)", "cuando no hay posición abierta: deja un aviso de stop para hoy.",
     """Stop vigilado para hoy: SLS si cae a 19.80. Te aviso cuando pase.
Recuerda: en MyInvestor el stop se pone como orden aparte (NYSE/Nasdaq/Xetra, max 60 dias).""",
     "que sea un aviso, no una posición. No hay P&L ni tamaño asociado. Si luego compras, registra con <code>/entre</code>."),
    ("/VENDER SLS 21.50   (sin posición)", "cuando no hay posición abierta: deja un aviso de venta para hoy.",
     "Aviso de venta puesto para hoy: SLS cuando llegue a 21.50. Te aviso y decides.",
     "que sea un aviso, no una orden. No se ejecuta nada en el broker."),
    ("/ALERTAS   (solo avisos sueltos)", "después de usar /stop o /vender sin posición.",
     """<b>Alertas de hoy</b> (2)
  tg-stop-sls-19-8-2026-11-18 · SLS · stop 19.80
  tg-venta-sls-21-5-2026-11-18 · SLS · target 21.50""",
     "que los ids empiecen por <code>tg-</code> (aviso suelto) y no por <code>pos-</code> (posición)."),
]
for cmd, cuando, texto, revisar in ERRORES:
    PARTES.append(bloque(cmd, cuando, texto, revisar))

PARTES.append("""<h2>22.5. Qué revisar en cada salida (chuleta)</h2>
<table>
<tr><th>Si ves…</th><th>Significa…</th><th>Qué haces</th></tr>
<tr><td><b>Avisos armados</b></td><td>El sistema vigila stop y objetivo</td><td>Comprueba <code>/alertas</code>; no hace falta más</td></tr>
<tr><td><b>AVISO: riesgo real … supera 50</b></td><td>Tu fill/stop dan más riesgo del tope</td><td>Reduce cantidad o acepta el exceso; queda registrado</td></tr>
<tr><td><b>Quedan N acc</b></td><td>Cierre parcial correcto</td><td>Los avisos siguen para el resto</td></tr>
<tr><td><b>No hay posicion abierta</b></td><td>No hay nada que cerrar</td><td>No insistas; revisa <code>/posiciones</code></td></tr>
<tr><td><b>El stop tiene que estar por debajo</b></td><td>Nivel inválido</td><td>Corrige el stop</td></tr>
<tr><td><b>Ya hay una posicion abierta</b></td><td>No se promedia</td><td>Cierra o reduce primero</td></tr>
<tr><td><b>Stop vigilado para hoy</b></td><td>Es un aviso, no una posición</td><td>No hay P&L; si compras, registra con <code>/entre</code></td></tr>
<tr><td><b>P&L bruto</b></td><td>No descuenta comisiones/FX</td><td>Resta el coste del aviso</td></tr>
<tr><td><b>SIN SEÑAL</b></td><td>No hay rango/ruptura</td><td>No compres; espera</td></tr>
<tr><td><b>SEÑAL CADUCADA</b></td><td>El precio se fue &gt;0,5R</td><td>No persigas</td></tr>
</table>

<h1 id="s23">23. Test final: ¿sabes qué hacer en cada momento?</h1>
<p>Si puedes responder estas 12 situaciones sin mirar, el manual está entendido. Si fallas una, vuelve a la
sección indicada.</p>
<table>
<tr><th>#</th><th>Situación</th><th>Qué haces</th><th>Sección</th></tr>
<tr><td>1</td><td>Son las 12:50 y no ha llegado el premarket.</td><td>Nada. <code>/ahora</code> y esperar. No se compra un candidato.</td><td>§5.1</td></tr>
<tr><td>2</td><td>13:00: llega el premarket con 150 candidatos.</td><td>Leer, <code>/hoy</code>, <code>/ganadores</code>, <code>/seguir</code> si quieres. Los candidatos no son compras.</td><td>§5.2</td></tr>
<tr><td>3</td><td>15:50–21:30: no llega ningún aviso.</td><td>Nada. Sin SEÑAL A no hay operación.</td><td>§5.5</td></tr>
<tr><td>4</td><td>SEÑAL A: entrada 20,12, stop 19,55, precio actual 20,30.</td><td>Está dentro de 0,5R: limitada 20,32, fill, <code>/entre</code>, alertas.</td><td>§9.10</td></tr>
<tr><td>5</td><td>SEÑAL A: precio actual 20,80.</td><td>No comprar: se fue más de 0,5R.</td><td>§9.10</td></tr>
<tr><td>6</td><td>SEÑAL A: precio actual 19,50 (stop 19,55).</td><td>No comprar: señal invalidada.</td><td>§9.10</td></tr>
<tr><td>7</td><td>Tienes posición y el precio toca el objetivo.</td><td>Limitada de venta al target, <code>/sali</code>, cancelar stop loss del broker si lo pusiste.</td><td>§9.14</td></tr>
<tr><td>8</td><td>Tienes posición y el precio toca el stop.</td><td>Vender (stop loss o manual), <code>/sali</code>, no reentrar por el mismo setup.</td><td>§10</td></tr>
<tr><td>9</td><td>Compraste 5, vendiste 3, quedan 2 y son las 21:40.</td><td>Vender las 2 a las 21:55. Si las mantienes, es swing fuera del sistema; watchlist y plan nuevo, no predicción.</td><td>§9.16</td></tr>
<tr><td>10</td><td>MyInvestor 144,94 y TradingView 139,40 (NVD.DE).</td><td>No mercado. Limitada al precio que aceptas; si no llena en 1–2 min, cancela. Comprueba venue/divisa.</td><td>§9.17</td></tr>
<tr><td>11</td><td>Día entero sin SEÑAL A.</td><td>No operar. Es un resultado válido; <code>/porque</code> y <code>/descartadas</code>.</td><td>§5.9</td></tr>
<tr><td>12</td><td>Datos de hace 420 s.</td><td>No operar. <code>/estado</code>, <code>smoke.py</code>, esperar dato fresco.</td><td>§5.10</td></tr>
</table>
<div class="ok">
<b>Si has respondido las 12</b>: sabes cuándo comprar, cuándo no, cómo registrar, cómo salir, qué hacer con las
2 que sobreviven y cómo evitar el precio retrasado. Si no, la sección indicada tiene la respuesta exacta.
</div>
""")

html_out = "\n".join(PARTES)
(AQUI / "parte5.html").write_text(html_out, encoding="utf-8")
print("parte5.html", len(html_out), "bytes")
