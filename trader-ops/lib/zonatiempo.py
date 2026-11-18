"""Reloj. Madrid y Nueva York con zoneinfo, nunca con diferencias fijas.

La diferencia Madrid-NY es 6 h la mayor parte del ano, pero pasa por 5 h
(ultima semana de octubre a la primera de noviembre, y en marzo al reves)
porque los cambios de hora no coinciden. Aqui se calcula siempre.
"""
import datetime as dt
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")
NEW_YORK = ZoneInfo("America/New_York")
BERLIN = ZoneInfo("Europe/Berlin")
UTC = dt.timezone.utc

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
DIAS = ("lun", "mar", "mie", "jue", "vie", "sab", "dom")


def now_utc():
    return dt.datetime.now(UTC)


def to_zone(moment, zone):
    return moment.astimezone(zone)


def madrid(moment=None):
    return (moment or now_utc()).astimezone(MADRID)


def ny(moment=None):
    return (moment or now_utc()).astimezone(NEW_YORK)


def berlin(moment=None):
    return (moment or now_utc()).astimezone(BERLIN)


def hhmm(moment, zone):
    return moment.astimezone(zone).strftime("%H:%M")


def stamp(moment=None):
    """'2026-11-18 05:22 Madrid / 23:22 NY (17-nov)' — para mensajes."""
    m = moment or now_utc()
    a, b = m.astimezone(MADRID), m.astimezone(NEW_YORK)
    same_day = a.date() == b.date()
    return "%s Madrid / %s NY%s" % (
        a.strftime("%Y-%m-%d %H:%M"),
        b.strftime("%H:%M"),
        "" if same_day else " (%s)" % b.strftime("%d-%b"),
    )


def short_stamp(moment=None):
    """'05:22 Madrid / 23:22 NY'."""
    m = moment or now_utc()
    return "%s Madrid / %s NY" % (m.astimezone(MADRID).strftime("%H:%M"), m.astimezone(NEW_YORK).strftime("%H:%M"))


def human(moment, zone):
    """'mie 18-nov 15:30' en la zona dada."""
    m = moment.astimezone(zone)
    return "%s %d-%s %s" % (DIAS[m.weekday()], m.day, MESES[m.month - 1], m.strftime("%H:%M"))


def iso_utc(moment=None):
    return (moment or now_utc()).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_madrid(moment=None):
    return (moment or now_utc()).astimezone(MADRID).isoformat(timespec="seconds")


def parse_hhmm(text, zone=MADRID, day=None):
    """'15:30' -> datetime en la zona y dia dados (por defecto hoy en Madrid)."""
    h, m = [int(x) for x in str(text).split(":")[:2]]
    base = (day or (now_utc().astimezone(zone).date()))
    return dt.datetime.combine(base, dt.time(h, m), tzinfo=zone)


def et_to_madrid(hhmm_text, day):
    """Hora de pared de Nueva York -> datetime en Madrid, ese dia."""
    h, m = [int(x) for x in str(hhmm_text).split(":")[:2]]
    local = dt.datetime.combine(day, dt.time(h, m), tzinfo=NEW_YORK)
    return local.astimezone(MADRID)


def madrid_to_et(hhmm_text, day):
    h, m = [int(x) for x in str(hhmm_text).split(":")[:2]]
    local = dt.datetime.combine(day, dt.time(h, m), tzinfo=MADRID)
    return local.astimezone(NEW_YORK)


def offset_hours(moment=None):
    """Diferencia Madrid-NY en horas (5 o 6)."""
    m = moment or now_utc()
    a = m.astimezone(MADRID).utcoffset()
    b = m.astimezone(NEW_YORK).utcoffset()
    return int((a - b).total_seconds() // 3600)


def yahoo_epoch(moment):
    """datetime -> segundos epoch (para comparar con timestamps de Yahoo)."""
    return int(moment.timestamp())
