"""En que momento del dia estamos y que se espera de ti. Sin opiniones de mercado.

Lo usan el bot (/ahora), el panel de terminal y el panel web.
"""
import datetime as dt

from . import calendario, cfg, registro
from . import zonatiempo as zt


def fase(now=None):
    """Devuelve (clave, titulo, que_hace_el_sistema, que_espera_de_ti, que_puedes_ignorar)."""
    now = now or zt.madrid()
    day = now.date()
    start, end, why = calendario.session_madrid(day)
    if not start:
        return ("sin_mercado", "Dia sin mercado (%s)" % why,
                "Nada. El orquestador duerme hasta la proxima sesion.",
                "Nada.",
                "Todo. No hay nada que hacer hoy.")
    flat = calendario.flat_by_madrid(day, cfg.config().get("flat_by", "15:55"))
    cutoff = zt.et_to_madrid(cfg.config().get("no_entries_after", "15:30"), day)
    pre = start - dt.timedelta(minutes=150)
    brief = start - dt.timedelta(minutes=30)
    t = now
    if t < pre:
        return ("antes_premarket", "Antes del premarket",
                "Nada todavia. A las %s lanza el scanner completo, noticias, resultados y Pelosi." % pre.strftime("%H:%M"),
                "Nada. Puedes mirar el briefing cuando llegue.",
                "Todo hasta que llegue el mensaje de premarket.")
    if t < brief:
        return ("premarket", "Premarket",
                "Scanner completo, noticias, resultados y Pelosi. Prepara la lista de candidatos.",
                "Nada obligatorio. Si quieres, /hoy para ver la lista.",
                "Los candidatos que no te interesen.")
    if t < start:
        return ("antes_abrir", "Antes de abrir",
                "Briefing final con candidatos, coste de esperar y plan condicional.",
                "Lee el briefing y decide si hoy operas o no.",
                "Los detalles del scanner: ya estan resumidos.")
    if t < start + dt.timedelta(minutes=20):
        return ("apertura", "Apertura: formando el rango",
                "Espera a que se cierre el rango 9:30-9:45 ET. No hay nada que avisar.",
                "Nada. No se entra antes de que el rango exista.",
                "Todo. Cualquier movimiento antes de las 15:45 es ruido para el sistema.")
    if t < cutoff:
        return ("ventana", "Ventana de entrada",
                "Escaneo ORB cada 5 minutos; por cada ruptura corre la cadena completa y avisa solo si es SEÑAL A.",
                "Si llega una SEÑAL A: decide y opera a mano. Si no llega, no hay nada que hacer.",
                "Las rupturas que no pasan los filtros.")
    if t < flat:
        return ("ultimos30", "Ultimos 30 minutos de entradas",
                "Ya no se abren entradas nuevas. Sigue vigilando stops y objetivos de lo abierto.",
                "Gestiona lo que tengas abierto.",
                "Cualquier ruptura nueva: llega tarde y no se opera.")
    if t < end:
        return ("cierre", "Cierre / flat by close",
                "Aviso de flat by close y, al cierre, informe del dia.",
                "Cierra a mano lo que siga abierto. No se mantiene nada.",
                "Todo lo demas.")
    return ("post", "Post-cierre",
            "Informe del dia y silencio hasta manana. Vigilante activo.",
            "Nada. Si quieres, /resumen o /registro.",
            "Todo. El sistema no opera fuera de horario.")


def siguiente_evento(now=None):
    """(titulo, datetime Madrid) del proximo hito de hoy, o el proximo dia."""
    now = now or zt.madrid()
    for delta in (0, 1, 2, 3, 7):
        day = (now + dt.timedelta(days=delta)).date()
        start, end, why = calendario.session_madrid(day)
        if not start:
            continue
        flat = calendario.flat_by_madrid(day, cfg.config().get("flat_by", "15:55"))
        hitos = [
            ("premarket (scanner)", start - dt.timedelta(minutes=150)),
            ("briefing", start - dt.timedelta(minutes=30)),
            ("apertura NYSE", start),
            ("primer escaneo ORB", start + dt.timedelta(minutes=20)),
            ("ultima entrada", zt.et_to_madrid(cfg.config().get("no_entries_after", "15:30"), day)),
            ("flat by close", flat),
            ("cierre e informe", end),
        ]
        for titulo, when in hitos:
            if when > now:
                return titulo, when
    return None, None


def cuenta_atras(when, now=None):
    if not when:
        return "n/d"
    now = now or zt.madrid()
    secs = int((when - now).total_seconds())
    if secs < 0:
        return "pasado"
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "%dh %02dm" % (h, m)
    if m:
        return "%dm %02ds" % (m, s)
    return "%ds" % s


def texto(now=None):
    """Bloque corto para el bot: fase + que haces tu + proximo evento."""
    now = now or zt.madrid()
    clave, titulo, hace, espera, ignora = fase(now)
    titulo_ev, when = siguiente_evento(now)
    lineas = ["<b>Ahora:</b> %s · %s" % (zt.short_stamp(now), titulo)]
    lineas.append("El sistema: %s" % hace)
    lineas.append("Tu: %s" % espera)
    lineas.append("Puedes ignorar: %s" % ignora)
    if titulo_ev:
        lineas.append("Proximo: %s a las %s (en %s)" % (
            titulo_ev, when.astimezone(zt.MADRID).strftime("%H:%M"), cuenta_atras(when, now)))
    return "\n".join(lineas)
