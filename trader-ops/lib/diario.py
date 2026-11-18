"""Diario: registro append-only de todo lo que el sistema ejecuta y envia.

Formato: una linea JSON por evento en logs/diario.jsonl.
Cada evento lleva hora UTC y hora Madrid, el comando, la salida (recortada),
su hash y los artefactos que produjo. El validador usa estos hashes para
comprobar que cada cifra de un aviso procede de una salida real.
"""
import hashlib
import json
import os
import threading
import uuid
from pathlib import Path

from . import cfg
from . import zonatiempo as zt

_LOCK = threading.Lock()
MAX_STORED_OUTPUT = 20000


def _hash(text):
    return hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()[:16]


def append(event, **fields):
    """Anade un evento. Devuelve el evento escrito (con id)."""
    moment = fields.pop("moment", None) or zt.now_utc()
    doc = {
        "id": uuid.uuid4().hex[:12],
        "ts_utc": zt.iso_utc(moment),
        "ts_madrid": zt.iso_madrid(moment),
        "event": event,
    }
    doc.update({k: v for k, v in fields.items() if v is not None})
    if "output" in doc:
        text = doc["output"] or ""
        doc["output_hash"] = _hash(text)
        if len(text) > MAX_STORED_OUTPUT:
            doc["output"] = text[:MAX_STORED_OUTPUT] + "\n...[recortado]"
    with _LOCK:
        cfg.LOGS.mkdir(parents=True, exist_ok=True)
        with open(cfg.DIARIO, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
    return doc


def read_all(path=None):
    path = Path(path or cfg.DIARIO)
    out = []
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def last(n=50, event=None):
    rows = [r for r in read_all() if event is None or r.get("event") == event]
    return rows[-n:]


def last_command(name=None, since_iso=None):
    for row in reversed(read_all()):
        if row.get("event") != "cmd":
            continue
        if name and row.get("name") != name:
            continue
        if since_iso and row.get("ts_utc", "") < since_iso:
            continue
        return row
    return None


def outputs_today(day=None):
    """Todas las salidas de comando del dia (Madrid)."""
    day = day or zt.madrid().date().isoformat()
    return [r for r in read_all() if r.get("event") == "cmd" and r.get("ts_madrid", "").startswith(day)]


def save_artifact(name, doc):
    """Guarda un JSON de evidencia en trader-ops/state/ y devuelve (ruta, hash)."""
    path = cfg.STATE / name
    cfg.write_json(path, doc)
    text = json.dumps(doc, indent=2, ensure_ascii=False)
    h = _hash(text)
    append("artifact", name=name, path=str(path), artifact_hash=h)
    return str(path), h


def load_artifact(name, default=None):
    return cfg.read_json(cfg.STATE / name, default)


def prune(days=120, keep_events=()):
    """Recorta el diario dejando los ultimos `days` dias. Mantiene eventos clave."""
    rows = read_all()
    if not rows:
        return 0
    cutoff = (zt.madrid().date()).toordinal() - days
    kept, dropped = [], 0
    for r in rows:
        try:
            ord_ = __import__("datetime").date.fromisoformat(r["ts_madrid"][:10]).toordinal()
        except Exception:
            kept.append(r)
            continue
        if ord_ >= cutoff or r.get("event") in keep_events:
            kept.append(r)
        else:
            dropped += 1
    if dropped:
        tmp = cfg.DIARIO.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for r in kept:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, cfg.DIARIO)
    return dropped
