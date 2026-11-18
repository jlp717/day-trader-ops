"""Referencias de precio puestas por el usuario (Börse Frankfurt, TradingView, MyInvestor...).

El sistema no puede consultar automaticamente TradingView, Börse Frankfurt ni Investing.com:
no tienen API publica gratuita y sus terminos prohiben el scraping. Lo que si puede hacer es
guardar el precio que TU ves en esas fuentes, con hora y nombre, y juntarlo con el Yahoo automatico
en /precios y en /entre.

    /ref NVD.DE 139.40 borse
    /precios NVD.DE

Las referencias caducan a los 30 minutos por defecto (configurable al consultarlas).
"""
import datetime as dt

from . import cfg
from . import zonatiempo as zt

PATH = cfg.STATE / "referencias.json"
MAX_AGE_MIN = 30
FUENTES = {
    "borse": "Börse Frankfurt/Xetra",
    "bf": "Börse Frankfurt/Xetra",
    "xetra": "Börse Frankfurt/Xetra",
    "tv": "TradingView",
    "tradingview": "TradingView",
    "investing": "Investing.com",
    "mx": "MyInvestor",
    "myinvestor": "MyInvestor",
    "manual": "Manual",
}


def _load():
    doc = cfg.read_json(PATH, {}) or {}
    doc.setdefault("refs", [])
    return doc


def _save(doc):
    cfg.write_json(PATH, doc)


def _age(iso):
    try:
        t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=zt.UTC)
    return int((zt.now_utc() - t).total_seconds())


def add(symbol, price, source="manual", currency=None, note=None):
    """Guarda la ultima referencia de esa fuente para el valor. Devuelve el dict."""
    sym = str(symbol or "").upper().strip()
    src = FUENTES.get(str(source or "manual").lower(), None)
    if not src:
        raise ValueError("fuente no valida; usa: %s" % ", ".join(sorted(set(FUENTES))))
    p = float(price)
    if not (0 < p < 1e7):
        raise ValueError("precio no valido")
    doc = _load()
    # una sola referencia por valor+fuente: la ultima manda
    doc["refs"] = [r for r in doc["refs"]
                   if not (r.get("symbol") == sym and r.get("source") == src)]
    row = {"symbol": sym, "price": round(p, 4), "source": src,
           "currency": (currency or ("EUR" if "." in sym else "USD")).upper(),
           "ts_utc": zt.iso_utc(), "ts_madrid": zt.iso_madrid()}
    if note:
        row["note"] = str(note)[:160]
    doc["refs"].append(row)
    # poda: nada de mas de 7 dias
    vivos = []
    for r in doc["refs"]:
        age = _age(r.get("ts_utc"))
        if age is not None and age < 7 * 86400:
            vivos.append(r)
    doc["refs"] = vivos
    _save(doc)
    return row


def get(symbol, max_age_min=MAX_AGE_MIN):
    """Referencias vigentes del valor, la mas reciente primero."""
    sym = str(symbol or "").upper().strip()
    out = []
    for r in _load()["refs"]:
        if r.get("symbol") != sym:
            continue
        age = _age(r.get("ts_utc"))
        if age is None or age > max_age_min * 60:
            continue
        row = dict(r)
        row["age_s"] = age
        out.append(row)
    out.sort(key=lambda x: x["age_s"])
    return out


def resumen(symbol, max_age_min=MAX_AGE_MIN):
    """Lineas cortas para /precios o /entre."""
    rows = get(symbol, max_age_min)
    if not rows:
        return []
    return ["%s %s %s (hace %ss)" % (r["source"], r["price"], r["currency"], r["age_s"])
            for r in rows]
