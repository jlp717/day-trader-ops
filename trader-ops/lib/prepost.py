"""Analisis de premarket y postmarket con Yahoo (includePrePost).

No ejecuta nada y no se mezcla con el flujo intradia. MyInvestor no permite
ordenes fuera del horario regular: esto solo prepara el plan para la apertura
o para el dia siguiente.
"""
import datetime as dt
import urllib.parse

from . import datos
from . import zonatiempo as zt

PRE_INI = dt.time(4, 0)
PRE_FIN = dt.time(9, 30)
POST_INI = dt.time(16, 0)
POST_FIN = dt.time(20, 0)


def _ny(ts):
    return dt.datetime.fromtimestamp(int(ts), tz=zt.NEW_YORK)


def _fetch(symbol):
    sym = str(symbol).upper().strip()
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s"
           "?range=1d&interval=5m&includePrePost=true" % urllib.parse.quote(sym))
    doc = datos.http_json_url(url)
    res = ((doc.get("chart") or {}).get("result") or [None])[0]
    if not res:
        raise datos.DataError("Yahoo sin datos para %s" % sym)
    meta = res.get("meta") or {}
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0] or {}
    closes = q.get("close") or []
    vols = q.get("volume") or []
    bars = []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        v = vols[i] if i < len(vols) and vols[i] is not None else 0
        bars.append({"t": int(t), "c": float(c), "v": float(v)})
    return sym, bars, (float(prev) if prev else None)


def resumen(symbol, modo="pre"):
    sym, bars, prev = _fetch(symbol)
    return _resumen(sym, bars, prev, modo)


def _resumen(sym, bars, prev, modo="pre"):
    modo = str(modo).lower()
    if modo == "pre":
        ini, fin = PRE_INI, PRE_FIN
    elif modo == "post":
        ini, fin = POST_INI, POST_FIN
    else:
        raise ValueError("modo debe ser pre o post")
    seleccion = [b for b in bars if ini <= _ny(b["t"]).time() < fin]
    regulares = [b for b in bars if dt.time(9, 30) <= _ny(b["t"]).time() < dt.time(16, 0)]
    ref = prev
    if modo == "post" and regulares:
        ref = regulares[-1]["c"]
    volumen = sum(b["v"] for b in seleccion)
    out = {"symbol": sym, "modo": modo, "n": len(seleccion), "ref": ref,
           "high": None, "low": None, "last": None, "pct": None,
           "volume": volumen if volumen else None}
    if seleccion:
        out["high"] = max(b["c"] for b in seleccion)
        out["low"] = min(b["c"] for b in seleccion)
        out["last"] = seleccion[-1]["c"]
        if ref:
            out["pct"] = (out["last"] / ref - 1.0) * 100.0
    return out


def imprimir(filas):
    print("symbol  modo  n   last      high      low       %       volumen")
    for r in filas:
        print("%-6s  %-4s %2d  %8s  %8s  %8s  %6s  %10s" % (
            r["symbol"], r["modo"], r["n"],
            ("%.2f" % r["last"]) if r["last"] is not None else "n/d",
            ("%.2f" % r["high"]) if r["high"] is not None else "n/d",
            ("%.2f" % r["low"]) if r["low"] is not None else "n/d",
            ("%.2f%%" % r["pct"]) if r["pct"] is not None else "n/d",
            ("%.0f" % r["volume"]) if r["volume"] is not None else "n/d"))
