"""Ganadores del dia: los que mas suben, calculados por nosotros. Sin screener de pago.

Dos vistas:
  premarket()  cierres diarios de todo el universo -> % del ultimo dia completo
  intradia()   barras de hoy de los mas liquidos -> % desde el cierre anterior

Filtro de calidad obligatorio antes de mirar el %: precio >= 5 USD y >= 20 M USD/dia.
Un ganador iliquido no es una oportunidad: es una trampa.
"""
import datetime as dt
import statistics
import urllib.parse

from . import cfg
from . import datos
from . import zonatiempo as zt

MIN_PRICE = 5.0
MIN_DOLLAR_VOL = 20_000_000
CACHE_PREMARKET = 6 * 3600
CACHE_INTRADIA = 600


def _universo(limit=None):
    path = cfg.TRADER / "universe.txt"
    syms = []
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                s = line.split("|")[0].strip().upper()
                if s:
                    syms.append(s)
    if not syms:
        doc = cfg.read_json(cfg.STATE / "scan_daily.json", {}) or {}
        syms = [h["symbol"] for h in (doc.get("hits") or []) if h.get("symbol")]
    return syms[:limit] if limit else syms


def _spark_pct(symbols, rng, interval, ttl):
    """{sym: {pct, price, dollar_vol}} con cache por lote."""
    out = {}
    for i in range(0, len(symbols), 20):
        batch = symbols[i:i + 20]
        key = "spark_%s_%s_%s" % (rng, interval, "_".join(batch))
        hit = datos._cache_get(key, ttl)
        if hit:
            out.update(hit)
            continue
        url = "/v7/finance/spark?symbols=%s&range=%s&interval=%s" % (
            ",".join(urllib.parse.quote(datos.yahoo_symbol(s)) for s in batch), rng, interval)
        try:
            doc = datos.http_json(url)
        except datos.DataError:
            continue
        got = {}
        for item in ((doc.get("spark") or {}).get("result") or []):
            resp = (item.get("response") or [None])[0]
            if not resp:
                continue
            sym = (item.get("symbol") or "").upper().replace("-", ".")
            q = ((resp.get("indicators") or {}).get("quote") or [{}])[0] or {}
            closes = [float(c) for c in (q.get("close") or []) if c is not None]
            vols = [float(v) for v in (q.get("volume") or []) if v is not None]
            meta = resp.get("meta") or {}
            if len(closes) < 2:
                continue
            prev = meta.get("chartPreviousClose") or meta.get("previousClose") or closes[-2]
            last = closes[-1]
            if not prev:
                continue
            vol = statistics.fmean(vols[-20:]) if vols else (meta.get("regularMarketVolume") or 0)
            got[sym] = {"price": last, "pct": (last / float(prev) - 1) * 100.0,
                        "dollar_vol": float(vol) * last, "prev": float(prev)}
        datos._cache_put(key, got)
        out.update(got)
    return out


def _filtrar(dic, top, min_price=MIN_PRICE, min_dv=MIN_DOLLAR_VOL):
    filas = []
    for sym, d in dic.items():
        if d["price"] < min_price or d["dollar_vol"] < min_dv:
            continue
        filas.append({"symbol": sym, "pct": round(d["pct"], 2), "price": round(d["price"], 2),
                      "dollar_vol": int(d["dollar_vol"])})
    filas.sort(key=lambda x: -x["pct"])
    return filas[:top]


def premarket(top=20, limit=None):
    """Ganadores del ultimo dia completo, sobre el universo. Cache 6 h."""
    syms = _universo(limit)
    dic = _spark_pct(syms, "1mo", "1d", CACHE_PREMARKET)
    return {"vista": "premarket", "as_of": zt.iso_utc(), "universo": len(syms),
            "con_datos": len(dic), "filas": _filtrar(dic, top)}


def intradia(top=20, base=300):
    """Ganadores de hoy entre los mas liquidos (300 por dolares del scan diario).

    Usa barras de 5 min del dia y el cierre previo del meta. Cache 10 min.
    """
    doc = cfg.read_json(cfg.STATE / "scan_daily.json", {}) or {}
    hits = doc.get("hits") or []
    syms = [h["symbol"] for h in hits][:base] or _universo(base)
    dic = _spark_pct(syms, "1d", "5m", CACHE_INTRADIA)
    return {"vista": "intradia", "as_of": zt.iso_utc(), "universo": len(syms),
            "con_datos": len(dic), "filas": _filtrar(dic, top)}


def texto(doc, top=15):
    filas = doc.get("filas") or []
    cab = "Ganadores %s · %s · %s valores con datos" % (
        "de ayer" if doc.get("vista") == "premarket" else "de hoy",
        zt.madrid().strftime("%H:%M"), doc.get("con_datos"))
    if not filas:
        return cab + "\nSin datos suficientes (o ninguno pasa el filtro de liquidez)."
    lineas = [cab, "#  Valor   %       precio   $/dia", ]
    for i, f in enumerate(filas[:top], 1):
        lineas.append("%-2d %-6s %+6.2f%% %9.2f %6.1fM" % (
            i, f["symbol"], f["pct"], f["price"], f["dollar_vol"] / 1e6))
    lineas.append("")
    lineas.append("Subir mucho no es una ventaja: es el punto de partida. Cada uno debe pasar "
                  "noticias, plan, Time Machine y risk antes de ser SEÑAL A.")
    return "\n".join(lineas)
