"""Reglas de alerta de precio: leer, armar, comprobar y quitar.

Dos motores, mismo contrato de regla:

- EE. UU. (sin sufijo): `trader/alerts.json`, lo comprueba `alerts.py check` del skill.
- Xetra (con sufijo, p.ej. `NVD.DE`): `trader-ops/state/alertas_xetra.json`, lo comprueba
  este modulo con `datos.quote`, porque el skill convierte `.` en `-` y Yahoo no lo encuentra.

Formato estable del skill (commit fijado):

    {"rules": [{"id": "...", "symbol": "NVDA", "type": "stop", "price": 154.0,
                "date": "2026-11-18"}]}

`date` es fecha de Nueva York: una regla de posicion no debe disparar manana.
Nunca se envia nada desde aqui: solo se escribe el archivo de reglas.
"""
import re

from . import cfg
from . import datos
from . import zonatiempo as zt

REGLAS = cfg.TRADER / "alerts.json"
ESTADO = cfg.TRADER / "state" / "alerts.json"
XETRA = cfg.STATE / "alertas_xetra.json"

TICKER = re.compile(r"^[A-Z]{1,5}$")
TICKER_XETRA = re.compile(r"^[A-Z]{1,5}\.[A-Z]{1,2}$")
TIPOS = ("stop", "target", "above", "below")


def _load(path=REGLAS):
    doc = cfg.read_json(path, None) or {}
    doc.setdefault("rules", [])
    return doc


def _save(doc, path=REGLAS):
    cfg.write_json(path, doc)


def hoy_ny():
    return zt.ny().date().isoformat()


def es_xetra(symbol):
    return bool(TICKER_XETRA.match(str(symbol or "").upper().strip()))


def precio_valido(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if 0 < x < 1e7 else None


def _valida(sym, tipo, precio, rid):
    if not (TICKER.match(sym) or TICKER_XETRA.match(sym)):
        return "%s no es un ticker valido (ej. NVDA o NVD.DE)" % (sym or "?")
    if tipo not in TIPOS:
        return "tipo de alerta no valido: %s" % tipo
    if precio_valido(precio) is None:
        return "precio no valido: %r" % (precio,)
    if not str(rid or "").strip():
        return "falta el id de la regla"
    return None


def armar(symbol, tipo, precio, rid, label=None, date=None, note=None):
    """Anade una regla al motor que corresponda. Devuelve (ok, motivo)."""
    sym = str(symbol or "").upper().strip()
    err = _valida(sym, tipo, precio, rid)
    if err:
        return False, err
    path = XETRA if es_xetra(sym) else REGLAS
    doc = _load(path)
    if any(r.get("id") == rid for r in doc["rules"]):
        return True, "ya existia"
    rule = {"id": str(rid), "symbol": sym, "type": tipo,
            "price": round(float(precio), 4), "date": date or hoy_ny()}
    if label:
        rule["label"] = str(label)[:60]
    if note:
        rule["note"] = str(note)[:200]
    doc["rules"].append(rule)
    _save(doc, path)
    return True, "armada"


def quitar(rid):
    """Borra la regla de los dos motores y su estado de timbre."""
    rid = str(rid or "")
    if not rid:
        return False
    borrado = False
    for path in (REGLAS, XETRA):
        doc = _load(path)
        antes = len(doc["rules"])
        doc["rules"] = [r for r in doc["rules"] if r.get("id") != rid]
        if len(doc["rules"]) != antes:
            _save(doc, path)
            borrado = True
        if doc.get("rung", {}).pop(rid, None) is not None:
            _save(doc, path)
    est = cfg.read_json(ESTADO, {}) or {}
    rung = est.get("rung") or {}
    if rid in rung:
        del rung[rid]
        est["rung"] = rung
        cfg.write_json(ESTADO, est)
    return borrado


def quitar_varias(ids):
    return sum(1 for rid in (ids or []) if quitar(rid))


def _vigentes(path, day):
    return [r for r in _load(path)["rules"]
            if not r.get("date") or str(r["date"]) == day]


def reglas_skill(day=None):
    return _vigentes(REGLAS, day or hoy_ny())


def reglas_xetra(day=None):
    return _vigentes(XETRA, day or hoy_ny())


def reglas(day=None):
    day = day or hoy_ny()
    return reglas_skill(day) + reglas_xetra(day)


def comprobar_xetra(now=None):
    """[(regla, precio)] de las reglas Xetra que tocan y no han sonado hoy."""
    now = now or zt.now_utc()
    doc = _load(XETRA)
    day = zt.ny(now).date().isoformat()
    rung = doc.get("rung") or {}
    rings = []
    for r in doc["rules"]:
        if r.get("date") and str(r["date"]) != day:
            continue
        rid = r.get("id")
        if rid in rung:
            continue
        if r.get("type") not in ("stop", "target", "above", "below"):
            continue
        try:
            q = datos.quote(r["symbol"])
            px = float(q["price"])
        except (datos.DataError, KeyError, TypeError, ValueError):
            continue
        p = float(r["price"])
        hit = (px <= p) if r["type"] in ("stop", "below") else (px >= p)
        if hit:
            rung[rid] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            rings.append((r, px))
            etiqueta = {"stop": "stop", "target": "objetivo"}.get(r["type"], r["type"])
            r["message"] = "%s esta a %.2f %s (nivel %s de %s)." % (
                r["symbol"], px, q.get("currency") or "", etiqueta, p)
    if rings:
        doc["rung"] = rung
        _save(doc, XETRA)
    return rings


def de_posicion(pos):
    """Ids de alerta de una posicion, aunque sea antigua y no los tenga guardados."""
    ids = list((pos or {}).get("alert_ids") or [])
    pid = (pos or {}).get("id")
    if pid:
        for tipo in ("stop", "target"):
            rid = "pos-%s-%s" % (pid, tipo)
            if rid not in ids:
                ids.append(rid)
    return ids
