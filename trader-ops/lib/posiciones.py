"""Posiciones reales (introducidas a mano por Javier) y su seguimiento.

El sistema no opera: registra lo que Javier dice que hizo y mide el deslizamiento
frente al plan (entrada, stop, objetivo, hora de salida).
"""
import time
import uuid

from . import alertas
from . import cfg
from . import zonatiempo as zt

PATH = cfg.STATE / "posiciones.json"


def _load():
    doc = cfg.read_json(PATH, None) or {}
    doc.setdefault("posiciones", [])
    return doc


def _save(doc):
    cfg.write_json(PATH, doc)


def abrir(symbol, precio, qty, stop=None, target=None, nota=None, plan=None):
    doc = _load()
    plan = plan or {}
    entry_plan = float(plan.get("entry") or precio)
    if stop is not None:
        risk = abs(float(precio) - float(stop))
    else:
        risk = float(plan.get("risk_per_share") or 0)
    pid = uuid.uuid4().hex[:8]
    pos = {
        "id": pid,
        "symbol": symbol.upper(),
        "qty": float(qty),
        "entrada": float(precio),
        "entrada_plan": entry_plan,
        "stop": float(stop) if stop else plan.get("stop"),
        "target": float(target) if target else plan.get("target"),
        "abierta_utc": zt.iso_utc(),
        "abierta_madrid": zt.iso_madrid(),
        "estado": "abierta",
        "nota": nota or "",
        "deslizamiento_entrada": round(float(precio) - entry_plan, 4),
        "riesgo_por_accion": round(float(risk), 4) if risk else None,
        "alert_ids": [],
        "alert_error": None,
    }
    # avisos exactos de stop y objetivo. Si el valor no admite alertas (.DE),
    # se guarda el motivo en la posicion en vez de prometer algo que no existe.
    for tipo in ("stop", "target"):
        px = pos.get(tipo)
        if not px:
            continue
        rid = "pos-%s-%s" % (pid, tipo)
        ok, motivo = alertas.armar(pos["symbol"], tipo, px, rid,
                                   label="%s %s" % (pos["symbol"], tipo), note="posicion %s" % pid)
        if ok:
            pos["alert_ids"].append(rid)
        else:
            pos["alert_error"] = motivo
    doc["posiciones"].append(pos)
    _save(doc)
    return pos


def abierta_de(symbol):
    """Primera posicion abierta del valor, o None."""
    sym = symbol.upper()
    for p in abiertas():
        if p["symbol"] == sym:
            return p
    return None


def cambiar(symbol, stop=None, target=None):
    """Mueve el stop o el objetivo de una posicion abierta y rearma sus avisos."""
    doc = _load()
    pos = None
    for p in doc["posiciones"]:
        if p["symbol"] == symbol.upper() and p.get("estado") == "abierta":
            pos = p
            break
    if not pos:
        return None
    cambios = []
    for tipo, valor in (("stop", stop), ("target", target)):
        if valor is None:
            continue
        nuevo = float(valor)
        viejo = pos.get(tipo)
        pos[tipo] = nuevo
        rid = "pos-%s-%s" % (pos["id"], tipo)
        alertas.quitar(rid)
        ok, motivo = alertas.armar(pos["symbol"], tipo, nuevo, rid,
                                   label="%s %s" % (pos["symbol"], tipo),
                                   note="posicion %s" % pos["id"])
        ids = [x for x in (pos.get("alert_ids") or []) if x != rid]
        if ok:
            ids.append(rid)
        else:
            pos["alert_error"] = motivo
        pos["alert_ids"] = ids
        cambios.append({"tipo": tipo, "antes": viejo, "ahora": nuevo, "aviso": ok, "motivo": motivo})
    _save(doc)
    return {"pos": pos, "cambios": cambios}


def cerrar(symbol, precio, qty=None, motivo="manual"):
    """Cierra total o parcialmente. Devuelve el resultado de ESTE cierre.

    Compatibilidad: `pnl_usd` y `R` son los del cierre actual. La posicion
    guardada acumula en `parciales` y en `pnl_realizado_usd`.
    """
    doc = _load()
    abiertas_ = [p for p in doc["posiciones"] if p["symbol"] == symbol.upper() and p.get("estado") == "abierta"]
    if not abiertas_:
        return None
    pos = abiertas_[0]
    q = float(qty or pos["qty"])
    q = max(0.0, min(q, float(pos["qty"])))
    if q <= 0:
        return None
    entry = float(pos["entrada"])
    r = None
    if pos.get("riesgo_por_accion"):
        r = (float(precio) - entry) / float(pos["riesgo_por_accion"])
    pnl = round((float(precio) - entry) * q, 2)
    parcial = {
        "fecha_utc": zt.iso_utc(),
        "fecha_madrid": zt.iso_madrid(),
        "precio": float(precio),
        "qty": q,
        "motivo": motivo,
        "pnl_usd": pnl,
        "R": round(r, 3) if r is not None else None,
    }
    pos.setdefault("parciales", []).append(parcial)
    pos["pnl_realizado_usd"] = round(
        sum(float(x.get("pnl_usd") or 0) for x in pos["parciales"]), 2)
    restante = round(float(pos["qty"]) - q, 6)
    if restante <= 1e-9:
        pos.update({
            "estado": "cerrada",
            "salida": float(precio),
            "salida_utc": zt.iso_utc(),
            "salida_madrid": zt.iso_madrid(),
            "qty_cerrada": float(pos["qty"]),
            "motivo": motivo,
            "R": round(r, 3) if r is not None else None,
            "deslizamiento_stop": (round(float(precio) - float(pos["stop"]), 4)
                                   if motivo == "stop" and pos.get("stop") else None),
        })
        alertas.quitar_varias(alertas.de_posicion(pos))
        pos["alert_ids"] = []
    else:
        pos["qty"] = restante
    _save(doc)
    res = dict(pos)
    res.update({"qty_cerrada": q, "pnl_usd": pnl,
                "R": round(r, 3) if r is not None else None,
                "parcial": restante > 1e-9, "restante": restante, "motivo": motivo})
    return res


def abiertas():
    return [p for p in _load()["posiciones"] if p.get("estado") == "abierta"]


def todas():
    return list(_load()["posiciones"])


def pnl():
    rows = _load()["posiciones"]
    eventos = []
    for p in rows:
        parciales = p.get("parciales") or []
        if parciales:
            eventos.extend(parciales)
        elif p.get("estado") == "cerrada" and p.get("pnl_usd") is not None:
            eventos.append({"pnl_usd": p.get("pnl_usd"), "R": p.get("R")})
    total = sum(float(x.get("pnl_usd") or 0) for x in eventos)
    rs = [float(x["R"]) for x in eventos if x.get("R") is not None]
    return {"operaciones": len(eventos), "pnl_usd": round(total, 2),
            "r_total": round(sum(rs), 2) if rs else 0.0,
            "ganadoras": len([x for x in eventos if float(x.get("pnl_usd") or 0) > 0]),
            "perdedoras": len([x for x in eventos if float(x.get("pnl_usd") or 0) < 0])}


def hoy():
    """Posiciones abiertas o cerradas hoy (Madrid)."""
    day = zt.madrid().date().isoformat()
    return [p for p in _load()["posiciones"]
            if (p.get("abierta_madrid") or "").startswith(day)
            or any((x.get("fecha_madrid") or "").startswith(day) for x in (p.get("parciales") or []))]


def riesgo_comprometido():
    """Riesgo USD de las posiciones abiertas (qty restante x riesgo por accion)."""
    total = 0.0
    for p in abiertas():
        total += float(p.get("qty") or 0) * float(p.get("riesgo_por_accion") or 0)
    return round(total, 2)


def cerca_de_stop(precios, tolerancia_pct=0.5):
    """[(pos, precio, distancia_pct)] de posiciones a menos de `tolerancia_pct` del stop."""
    out = []
    for p in abiertas():
        px = precios.get(p["symbol"])
        if px is None or not p.get("stop"):
            continue
        dist = (float(px) - float(p["stop"])) / float(px) * 100.0
        if 0 <= dist <= tolerancia_pct:
            out.append((p, float(px), round(dist, 3)))
    return out
