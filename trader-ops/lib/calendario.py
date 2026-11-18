"""Calendario de mercados. Fuente NYSE: nyse.com/markets/hours-calendars (leido 2026-11-18).

Fechas verificadas hoy en la pagina oficial:
- Thanksgiving 2026: jueves 26-nov; cierre anticipado 13:00 ET el viernes 27-nov.
- Christmas 2026: viernes 25-dic; cierre anticipado 13:00 ET el jueves 24-dic.
- 2028: sin festivo el 1-ene (cae sabado); cierre anticipado 3-jul-2028 y 24-nov-2028.
Xetra: tabla propia a partir del calendario publicado por Deutsche Boerse; se marca
`verificado=False` para que el orquestador lo diga en vez de inventar.
"""
import datetime as dt

from . import zonatiempo as zt

# ---------------------------------------------------------------- NYSE

NYSE_HOLIDAYS = {
    # 2026
    "2026-01-01": "Ano Nuevo",
    "2026-01-19": "Martin Luther King",
    "2026-02-16": "Washington's Birthday",
    "2026-04-03": "Viernes Santo",
    "2026-05-25": "Memorial Day",
    "2026-06-19": "Juneteenth",
    "2026-07-03": "Independencia (observado)",
    "2026-09-07": "Labor Day",
    "2026-11-26": "Accion de Gracias",
    "2026-12-25": "Navidad",
    # 2027
    "2027-01-01": "Ano Nuevo",
    "2027-01-18": "Martin Luther King",
    "2027-02-15": "Washington's Birthday",
    "2027-03-26": "Viernes Santo",
    "2027-05-31": "Memorial Day",
    "2027-06-18": "Juneteenth (observado)",
    "2027-07-05": "Independencia (observado)",
    "2027-09-06": "Labor Day",
    "2027-11-25": "Accion de Gracias",
    "2027-12-24": "Navidad (observado)",
    # 2028
    "2028-01-17": "Martin Luther King",
    "2028-02-21": "Washington's Birthday",
    "2028-04-14": "Viernes Santo",
    "2028-05-29": "Memorial Day",
    "2028-06-19": "Juneteenth",
    "2028-07-04": "Independencia",
    "2028-09-04": "Labor Day",
    "2028-11-23": "Accion de Gracias",
    "2028-12-25": "Navidad",
}

NYSE_EARLY_CLOSE = {
    "2026-11-27": "dia despues de Accion de Gracias",
    "2026-12-24": "Nochebuena",
    "2027-11-26": "dia despues de Accion de Gracias",
    "2028-07-03": "vispera de Independencia",
    "2028-11-24": "dia despues de Accion de Gracias",
}

NYSE_YEARS_KNOWN = (2026, 2027, 2028)

# ---------------------------------------------------------------- Xetra (tabla propia)

XETRA_HOLIDAYS = {
    "2026-01-01": "Ano Nuevo",
    "2026-04-03": "Viernes Santo",
    "2026-04-06": "Lunes de Pascua",
    "2026-05-01": "Dia del Trabajo",
    "2026-05-25": "Lunes de Pentecostes",
    "2026-12-24": "Nochebuena",
    "2026-12-25": "Navidad",
    "2026-12-31": "Fin de ano",
    "2027-01-01": "Ano Nuevo",
    "2027-03-26": "Viernes Santo",
    "2027-03-29": "Lunes de Pascua",
    "2027-05-01": "Dia del Trabajo",
    "2027-05-17": "Lunes de Pentecostes",
    "2027-12-24": "Nochebuena",
    "2027-12-31": "Fin de ano",
}
XETRA_YEARS_KNOWN = (2026, 2027)
XETRA_OPEN = dt.time(9, 0)
XETRA_CLOSE = dt.time(17, 30)

NYSE_OPEN = dt.time(9, 30)
NYSE_CLOSE = dt.time(16, 0)
NYSE_EARLY = dt.time(13, 0)


def _d(day):
    return day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day))


def nyse_session(day):
    """(abre, cierra, motivo) en hora de Nueva York, o (None, None, motivo) si cerrado."""
    d = _d(day)
    iso = d.isoformat()
    if d.weekday() >= 5:
        return None, None, "fin de semana"
    if iso in NYSE_HOLIDAYS:
        return None, None, "festivo NYSE: " + NYSE_HOLIDAYS[iso]
    if d.year not in NYSE_YEARS_KNOWN:
        return NYSE_OPEN, NYSE_CLOSE, "ano %d sin calendario verificado" % d.year
    if iso in NYSE_EARLY_CLOSE:
        return NYSE_OPEN, NYSE_EARLY, "cierre anticipado: " + NYSE_EARLY_CLOSE[iso]
    return NYSE_OPEN, NYSE_CLOSE, "sesion normal"


def xetra_session(day):
    d = _d(day)
    iso = d.isoformat()
    if d.weekday() >= 5:
        return None, None, "fin de semana"
    if iso in XETRA_HOLIDAYS:
        return None, None, "festivo Xetra: " + XETRA_HOLIDAYS[iso]
    if d.year not in XETRA_YEARS_KNOWN:
        return None, None, "ano %d sin calendario Xetra verificado" % d.year
    return XETRA_OPEN, XETRA_CLOSE, "sesion normal"


def is_trading_day(day, market="US"):
    if market.upper() in ("US", "NYSE", "NASDAQ"):
        return nyse_session(day)[0] is not None
    return xetra_session(day)[0] is not None


def next_trading_day(day, market="US", include_today=False):
    d = _d(day)
    if not include_today:
        d += dt.timedelta(days=1)
    for _ in range(30):
        if is_trading_day(d, market):
            return d
        d += dt.timedelta(days=1)
    return None


def session_madrid(day, market="US"):
    """(inicio, fin, motivo) en hora de Madrid para ese dia."""
    if market.upper() in ("US", "NYSE", "NASDAQ"):
        o, c, why = nyse_session(day)
        zone_from, zone_to = zt.NEW_YORK, zt.MADRID
    else:
        o, c, why = xetra_session(day)
        zone_from, zone_to = zt.BERLIN, zt.MADRID
    if o is None:
        return None, None, why
    d = _d(day)
    start = dt.datetime.combine(d, o, tzinfo=zone_from).astimezone(zone_to)
    end = dt.datetime.combine(d, c, tzinfo=zone_from).astimezone(zone_to)
    return start, end, why


def flat_by_madrid(day, flat_by="15:55", market="US"):
    """'flat by close' del skill (hora NY) -> datetime Madrid, con cierre anticipado."""
    d = _d(day)
    o, c, _ = nyse_session(d)
    if o is None:
        return None
    h, m = [int(x) for x in str(flat_by).split(":")[:2]]
    at = dt.datetime.combine(d, dt.time(h, m))
    if c and at >= dt.datetime.combine(d, c):
        shift = dt.datetime.combine(d, NYSE_CLOSE) - dt.datetime.combine(d, c)
        at = at - shift
    return at.replace(tzinfo=zt.NEW_YORK).astimezone(zt.MADRID)


def upcoming(reference=None, days=20):
    """Proximos eventos (festivos y cierres anticipados) de ambos mercados."""
    ref = (reference or zt.madrid()).date()
    out = []
    for i in range(days):
        d = ref + dt.timedelta(days=i)
        _, _, why_us = nyse_session(d)
        if why_us.startswith("festivo") or why_us.startswith("cierre"):
            out.append((d, "NYSE", why_us))
        _, _, why_x = xetra_session(d)
        if why_x.startswith("festivo"):
            out.append((d, "Xetra", why_x))
    return out
