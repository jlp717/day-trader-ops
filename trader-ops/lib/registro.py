"""Registro vivo de senales SEÑAL A y su resultado.

No es un backtest: es lo que el sistema dijo y lo que paso despues, en papel.
Si este registro, con muestra suficiente, da EV <= 0, el freno por evidencia
corta las SEÑAL A (criterios.UMBRALES y CRITERIOS.md).
"""
import uuid

from . import cfg
from . import criterios
from . import zonatiempo as zt

PATH = cfg.STATE / "registro.json"


def _load():
    doc = cfg.read_json(PATH, None) or {}
    doc.setdefault("senales", [])
    return doc


def _save(doc):
    cfg.write_json(PATH, doc)


def add(symbol, plan, veredicto, mensaje_id=None, extra=None):
    doc = _load()
    sig = {
        "id": uuid.uuid4().hex[:10],
        "ts_utc": zt.iso_utc(),
        "ts_madrid": zt.iso_madrid(),
        "symbol": symbol.upper(),
        "estado": "abierta",
        "plan": {k: plan.get(k) for k in ("entry", "stop", "target", "risk_per_share",
                                          "reward_risk", "target_r", "flat_by", "date")},
        "veredicto": veredicto,
        "mensaje_id": mensaje_id,
    }
    if extra:
        sig.update(extra)
    doc["senales"].append(sig)
    _save(doc)
    return sig


def close(sig_id, estado, precio=None, nota=None):
    doc = _load()
    for s in doc["senales"]:
        if s["id"] != sig_id:
            continue
        plan = s.get("plan") or {}
        entry = float(plan.get("entry") or 0)
        stop = float(plan.get("stop") or 0)
        risk = float(plan.get("risk_per_share") or (entry - stop) or 0)
        if estado == "objetivo":
            r = (float(plan.get("target") or 0) - entry) / risk if risk else None
        elif estado == "stop":
            r = -1.0
        elif precio and risk:
            r = (float(precio) - entry) / risk
        else:
            r = None
        s.update({"estado": estado, "cerrada_utc": zt.iso_utc(), "precio_cierre": precio,
                  "R": round(r, 3) if r is not None else None, "nota": nota})
        _save(doc)
        return s
    return None


def get(sig_id):
    for s in _load()["senales"]:
        if s["id"] == sig_id:
            return s
    return None


def open_signals():
    return [s for s in _load()["senales"] if s.get("estado") == "abierta"]


def all_signals():
    return list(_load()["senales"])


def stats():
    rows = _load()["senales"]
    cerradas = [s for s in rows if s.get("estado") in ("objetivo", "stop", "cerrada")]
    rs = [float(s["R"]) for s in cerradas if s.get("R") is not None]
    return {
        "total": len(rows),
        "abiertas": len([s for s in rows if s.get("estado") == "abierta"]),
        "cerradas": len(cerradas),
        "objetivos": len([s for s in cerradas if s.get("estado") == "objetivo"]),
        "stops": len([s for s in cerradas if s.get("estado") == "stop"]),
        "r_medio": round(sum(rs) / len(rs), 3) if rs else 0.0,
        "r_total": round(sum(rs), 2) if rs else 0.0,
    }


def freno_activo():
    """Freno por evidencia: con muestra suficiente y R medio <= 0, no mas SEÑAL A."""
    s = stats()
    if s["cerradas"] < criterios.UMBRALES["min_history_triggered"]:
        return False, "muestra insuficiente (%d cerradas)" % s["cerradas"]
    if s["r_medio"] <= 0:
        return True, "registro vivo con %d cerradas y R medio %+.2f <= 0" % (s["cerradas"], s["r_medio"])
    return False, "registro vivo con R medio %+.2f" % s["r_medio"]


def cuenta_hoy(day=None):
    day = day or zt.madrid().date().isoformat()
    rows = [s for s in _load()["senales"] if s.get("ts_madrid", "").startswith(day)]
    return {"total": len(rows), "abiertas": len([s for s in rows if s.get("estado") == "abierta"]),
            "riesgo_usd": sum(float((s.get("plan") or {}).get("risk_per_share") or 0) *
                              float(s.get("shares") or 0) for s in rows)}


def ultima_por_symbol(symbol):
    rows = [s for s in _load()["senales"] if s["symbol"] == symbol.upper()]
    return rows[-1] if rows else None


def marcar_resultados(precios):
    """Cierra senales cuyo target o stop se toco segun un dict {SYM: precio}."""
    out = []
    for s in open_signals():
        px = precios.get(s["symbol"])
        if px is None:
            continue
        plan = s.get("plan") or {}
        if px >= float(plan.get("target") or 0):
            out.append(close(s["id"], "objetivo", px))
        elif px <= float(plan.get("stop") or 0):
            out.append(close(s["id"], "stop", px))
    return [o for o in out if o]
