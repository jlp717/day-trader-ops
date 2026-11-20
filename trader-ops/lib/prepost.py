"""Analisis de premarket y postmarket con Yahoo (includePrePost).

No ejecuta nada y no se mezcla con el flujo intradia. MyInvestor no permite
ordenes fuera del horario regular: esto solo prepara el plan para la apertura
o para el dia siguiente.
"""
import datetime as dt
import json
import os
import urllib.parse

from . import cfg
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
            out["rango_pct"] = (out["high"] - out["low"]) / ref * 100.0
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


def symbols_from_scan(top=30):
    """Candidatos por dolares del ultimo scan diario, o la watchlist si no hay."""
    doc = cfg.read_json(cfg.STATE / "scan_daily.json", {}) or {}
    hits = doc.get("hits") or []
    filas = sorted(hits, key=lambda h: float(h.get("price") or 0) * float(h.get("volume") or 0),
                   reverse=True)
    out = []
    for h in filas:
        s = str(h.get("symbol") or "").upper()
        if s and s not in out:
            out.append(s)
        if len(out) >= int(top):
            break
    if not out:
        out = [str(x).upper() for x in (cfg.config().get("watch") or ["NVDA"])]
    return out


def radar(symbols, modo="pre", limit=30):
    """Resumen pre/post de una lista, ordenado por movimiento absoluto."""
    filas = []
    for sym in list(symbols)[:int(limit)]:
        try:
            r = resumen(sym, modo)
        except Exception:
            continue
        if r.get("ref") and r.get("high") is not None and r.get("low") is not None:
            r["rango_pct"] = (r["high"] - r["low"]) / r["ref"] * 100.0
        else:
            r["rango_pct"] = None
        filas.append(r)
    filas.sort(key=lambda r: abs(r.get("pct") or 0.0), reverse=True)
    return filas


def guardar(path, filas):
    p = str(path)
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(filas, f, ensure_ascii=False, indent=2)
    return p


def cargar(path):
    if not os.path.exists(str(path)):
        return []
    try:
        with open(str(path), encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []


def texto(filas, modo="pre"):
    if not filas:
        return "Sin datos de %s. Genera el radar con run/prepost.py --radar." % modo
    out = ["Radar %s · %d valores" % (modo, len(filas)),
           "symbol  last      high      low       %         rango    volumen"]
    for r in filas[:20]:
        out.append("%-6s  %8s  %8s  %8s  %7s  %7s  %9s" % (
            r["symbol"],
            ("%.2f" % r["last"]) if r["last"] is not None else "n/d",
            ("%.2f" % r["high"]) if r["high"] is not None else "n/d",
            ("%.2f" % r["low"]) if r["low"] is not None else "n/d",
            ("%+.2f%%" % r["pct"]) if r["pct"] is not None else "n/d",
            ("%.2f%%" % r["rango_pct"]) if r.get("rango_pct") is not None else "n/d",
            ("%.0f" % r["volume"]) if r["volume"] is not None else "n/d"))
    out.append("Solo análisis: MyInvestor no ejecuta fuera del horario regular.")
    return "\n".join(out)
