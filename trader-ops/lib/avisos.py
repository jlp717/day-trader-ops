"""Deduplicacion de mensajes: la misma clave no se envia dos veces el mismo dia.

Clave = texto estable (p.ej. 'briefing:2026-11-18' o 'senal:TSLA:10:15').
Persistente en trader-ops/state/avisos.json; se poda solo.
"""
import hashlib

from . import cfg
from . import zonatiempo as zt

PATH = cfg.STATE / "avisos.json"


def _key_hash(key):
    return hashlib.sha1((key or "").encode("utf-8", "replace")).hexdigest()[:16]


def ya_enviado(key, day=None):
    day = day or zt.madrid().date().isoformat()
    doc = cfg.read_json(PATH, {}) or {}
    return _key_hash(key) in (doc.get(day) or [])


def marcar(key, day=None):
    day = day or zt.madrid().date().isoformat()
    doc = cfg.read_json(PATH, {}) or {}
    import datetime as _dt
    try:
        cutoff = (_dt.date.fromisoformat(day) - _dt.timedelta(days=1)).isoformat()
    except ValueError:
        cutoff = day
    doc = {k: v for k, v in doc.items() if k >= cutoff}
    doc.setdefault(day, [])
    h = _key_hash(key)
    if h not in doc[day]:
        doc[day].append(h)
    cfg.write_json(PATH, doc)
    return True


def send_once(bot, key, text, buttons=None, silent=False):
    """Envia solo si la clave no se envio hoy. Devuelve message_id o None."""
    if ya_enviado(key):
        return None
    mid = bot.send(text, buttons=buttons, silent=silent)
    marcar(key)
    return mid
