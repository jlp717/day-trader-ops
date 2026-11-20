"""Niveles manuales por simbolo: stops y objetivos que no dependen del skill.

Sirve para posiciones que no estan registradas con `/entre` o para vigilar un nivel
sin fecha de caducidad. Se guardan en `state/niveles.json` y los comprueba el
vigilante rapido cada 30 s. No envia ordenes.
"""
from . import cfg
from . import zonatiempo as zt

PATH = cfg.STATE / "niveles.json"


def _load():
    doc = cfg.read_json(PATH, {}) or {}
    if not isinstance(doc.get("niveles"), list):
        doc["niveles"] = []
    return doc


def _save(doc):
    cfg.write_json(PATH, doc)


def poner(symbol, stop=None, target=None, nota=None):
    sym = str(symbol or "").upper().strip()
    if not sym:
        raise ValueError("simbolo vacio")
    doc = _load()
    fila = next((x for x in doc["niveles"] if x.get("symbol") == sym), None)
    if fila is None:
        fila = {"symbol": sym}
        doc["niveles"].append(fila)
    if stop is not None:
        fila["stop"] = round(float(stop), 4)
    if target is not None:
        fila["target"] = round(float(target), 4)
    if nota:
        fila["nota"] = str(nota)[:120]
    fila["ts_madrid"] = zt.madrid().isoformat(timespec="seconds")
    if fila.get("stop") is not None and fila.get("target") is not None:
        if float(fila["stop"]) >= float(fila["target"]):
            raise ValueError("el stop debe estar por debajo del objetivo")
    _save(doc)
    return fila


def quitar(symbol):
    sym = str(symbol or "").upper().strip()
    doc = _load()
    antes = len(doc["niveles"])
    doc["niveles"] = [x for x in doc["niveles"] if x.get("symbol") != sym]
    if len(doc["niveles"]) != antes:
        _save(doc)
        return True
    return False


def todos():
    return _load()["niveles"]


def comprobar(precios, day=None):
    """[(fila, tipo, precio, nivel)] de los niveles tocados hoy y no avisados."""
    day = day or zt.madrid().date().isoformat()
    doc = _load()
    hits = []
    for fila in doc["niveles"]:
        px = precios.get(fila.get("symbol"))
        if px is None:
            continue
        for tipo in ("stop", "target"):
            nivel = fila.get(tipo)
            if nivel is None:
                continue
            if (fila.get("sonado") or {}).get(tipo) == day:
                continue
            hit = float(px) <= float(nivel) if tipo == "stop" else float(px) >= float(nivel)
            if hit:
                fila.setdefault("sonado", {})[tipo] = day
                hits.append((fila, tipo, float(px), float(nivel)))
    if hits:
        _save(doc)
    return hits


def texto():
    filas = todos()
    if not filas:
        return "Sin niveles manuales. Usa: /nivel TLK 11.20 12.38 (stop y objetivo)."
    out = ["<b>Niveles manuales</b>"]
    for f in filas:
        out.append("  %s  stop %s · objetivo %s%s" % (
            f["symbol"],
            ("%.2f" % f["stop"]) if f.get("stop") is not None else "n/d",
            ("%.2f" % f["target"]) if f.get("target") is not None else "n/d",
            ("  · %s" % f["nota"]) if f.get("nota") else ""))
    return "\n".join(out)
