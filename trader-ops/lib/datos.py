"""Datos de mercado para medir frescura, latencia y calidad. Solo Yahoo, con cache y pausa.

No sustituye al skill: sirve para (a) saber si el dato esta fresco, (b) calcular
liquidez y spread con numeros propios, (c) convertir EUR/USD. Todo queda en el diario.
"""
import datetime as dt
import gzip
import json
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

from . import cfg
from . import diario
from . import zonatiempo as zt

UA = "Mozilla/5.0 (compatible; day-trader-ops/1.0; paper-trading)"
HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")
PAUSE = 0.3
BACKOFF = 5.0
CACHE_TTL_QUOTE = 60          # segundos
CACHE_TTL_DAILY = 6 * 3600
_LAST_CALL = [0.0]


class DataError(Exception):
    pass


def _cache_path(key):
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
    return cfg.CACHE / ("%s.json" % safe[:120])


def _cache_get(key, ttl):
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        doc = cfg.read_json(p, None)
    except Exception:
        return None
    if not doc or "fetched_at" not in doc:
        return None
    age = time.time() - float(doc["fetched_at"])
    if age > ttl:
        return None
    return doc.get("payload")


def _cache_put(key, payload):
    cfg.write_json(_cache_path(key), {"fetched_at": time.time(), "payload": payload})


def _polite():
    gap = time.time() - _LAST_CALL[0]
    if gap < PAUSE:
        time.sleep(PAUSE - gap)
    _LAST_CALL[0] = time.time()


def http_json(path, timeout=20, retries=1):
    """GET a Yahoo path (empieza por /) probando query2 y query1."""
    last = None
    for attempt in range(retries + 1):
        for host in HOSTS:
            full = "https://%s%s" % (host, path)
            req = urllib.request.Request(full, headers={"User-Agent": UA, "Accept": "application/json"})
            try:
                _polite()
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as exc:
                last = "HTTP %d" % exc.code
                try:
                    exc.close()
                except Exception:
                    pass
                if exc.code == 429:
                    time.sleep(BACKOFF)
                    continue
                if exc.code >= 500:
                    continue
                raise DataError("%s en %s" % (last, full.split("?")[0]))
            except (urllib.error.URLError, OSError, ValueError) as exc:
                last = str(exc)
                continue
        if attempt < retries:
            time.sleep(2)
    raise DataError("sin respuesta (%s)" % last)


def yahoo_symbol(symbol):
    """Simbolo tal cual para Yahoo; solo normaliza clases USA con punto."""
    s = symbol.strip().upper()
    if "." in s and not s.split(".")[-1].isalpha():
        return s
    if "." in s and len(s.split(".")[-1]) == 1:
        return s.replace(".", "-")
    return s


def chart(symbol, range_="1d", interval="5m", ttl=CACHE_TTL_QUOTE):
    """Barras normalizadas. {symbol, currency, exchange, meta, bars:[{t,o,h,l,c,v}]}"""
    ysym = yahoo_symbol(symbol)
    key = "chart_%s_%s_%s" % (ysym, range_, interval)
    hit = _cache_get(key, ttl)
    if hit:
        return hit
    url = "/v8/finance/chart/%s?range=%s&interval=%s" % (
        urllib.parse.quote(ysym), range_, interval)
    doc = http_json(url)
    res = ((doc.get("chart") or {}).get("result") or [None])[0]
    if not res:
        err = (doc.get("chart") or {}).get("error") or {}
        raise DataError("Yahoo sin datos para %s: %s" % (symbol, err.get("description") or "desconocido"))
    meta = res.get("meta") or {}
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0] or {}
    bars = []
    for i, ts in enumerate(res.get("timestamp") or []):
        def at(k):
            arr = q.get(k) or []
            return arr[i] if i < len(arr) else None
        if at("close") is None:
            continue
        bars.append({"t": int(ts), "o": at("open"), "h": at("high"), "l": at("low"),
                     "c": float(at("close")), "v": int(at("volume") or 0)})
    out = {"symbol": meta.get("symbol") or ysym, "currency": meta.get("currency"),
           "exchange": meta.get("exchangeName"), "meta": meta, "bars": bars}
    _cache_put(key, out)
    return out


def quote(symbol):
    """Ultimo precio + hora del dato + edad en segundos. Sin inventar."""
    doc = chart(symbol, "1d", "5m", ttl=30)
    meta = doc["meta"]
    last = meta.get("regularMarketPrice")
    t = meta.get("regularMarketTime")
    if last is None and doc["bars"]:
        last = doc["bars"][-1]["c"]
        t = doc["bars"][-1]["t"]
    if last is None:
        raise DataError("sin precio para %s" % symbol)
    moment = dt.datetime.fromtimestamp(int(t), tz=zt.UTC) if t else None
    age = (zt.now_utc() - moment).total_seconds() if moment else None
    return {"symbol": doc["symbol"], "price": float(last), "currency": doc["currency"],
            "exchange": doc["exchange"], "data_time": zt.iso_utc(moment) if moment else None,
            "age_seconds": None if age is None else int(age), "bars": len(doc["bars"])}


def _spark(symbols, range_="1mo", interval="1d"):
    """Cierres y volumen diarios de hasta 20 simbolos. Cache 6 h."""
    if not symbols:
        return {}
    out = {}
    for i in range(0, len(symbols), 20):
        batch = symbols[i:i + 20]
        key = "spark_%s_%s_%s" % (range_, interval, "_".join(batch))
        hit = _cache_get(key, CACHE_TTL_DAILY)
        if hit:
            out.update(hit)
            continue
        url = "/v7/finance/spark?symbols=%s&range=%s&interval=%s" % (
            ",".join(urllib.parse.quote(yahoo_symbol(s)) for s in batch), range_, interval)
        doc = http_json(url)
        got = {}
        for item in ((doc.get("spark") or {}).get("result") or []):
            resp = (item.get("response") or [None])[0]
            if not resp:
                continue
            sym = (item.get("symbol") or "").upper().replace("-", ".")
            q = ((resp.get("indicators") or {}).get("quote") or [{}])[0] or {}
            closes = [c for c in (q.get("close") or []) if c is not None]
            vols = [v for v in (q.get("volume") or []) if v is not None]
            got[sym] = {"closes": closes[-25:], "volumes": vols[-25:],
                        "meta": resp.get("meta") or {}}
        _cache_put(key, got)
        out.update(got)
    return out


def calidad(symbol, min_bars=20):
    """Metricas de calidad con datos propios: precio, volumen medio, dolares y spread proxy.

    `spread_pct` es un PROXY: mediana de (maximo-minimo)/cierre de las barras de 5 min.
    No es el bid-ask real; se marca como proxy en todos los mensajes.
    """
    intra = chart(symbol, "1d", "5m", ttl=CACHE_TTL_QUOTE)
    bars5 = intra["bars"]
    daily = chart(symbol, "1mo", "1d", ttl=CACHE_TTL_DAILY)
    today_ny = zt.ny().date()
    vols = []
    for b in daily["bars"]:
        day_ny = dt.datetime.fromtimestamp(b["t"], tz=zt.UTC).astimezone(zt.NEW_YORK).date()
        if day_ny >= today_ny:
            continue          # la barra de hoy no esta cerrada
        if b.get("v"):
            vols.append(b["v"])
    vols = vols[-20:]
    if not bars5:
        raise DataError("sin barras intradia para %s" % symbol)
    price = bars5[-1]["c"]
    avg_vol = statistics.fmean(vols) if vols else None
    widths = [((b["h"] - b["l"]) / b["c"] * 100.0) for b in bars5 if b.get("h") and b.get("l") and b["c"]]
    spread = statistics.median(widths) if widths else None
    intraday_dollar = sum(b["c"] * b["v"] for b in bars5)
    return {
        "symbol": symbol.upper(),
        "price": round(price, 4),
        "currency": intra["currency"],
        "avg_volume_20d": int(avg_vol) if avg_vol else None,
        "dollar_volume_20d": int(avg_vol * price) if avg_vol else None,
        "dollar_volume_today": int(intraday_dollar),
        "spread_pct_proxy": round(spread, 4) if spread is not None else None,
        "bars_5m": len(bars5),
        "days_daily": len(vols),
        "spread_is_proxy": True,
    }


def eurusd(ttl=3600):
    doc = chart("EURUSD=X", "5d", "1d", ttl=ttl)
    if not doc["bars"]:
        raise DataError("sin EUR/USD")
    return float(doc["bars"][-1]["c"])


def convert(amount, from_ccy, to_ccy):
    if not from_ccy or not to_ccy or from_ccy.upper() == to_ccy.upper():
        return float(amount)
    fx = eurusd()
    f, t = from_ccy.upper(), to_ccy.upper()
    if f == "EUR" and t == "USD":
        return float(amount) * fx
    if f == "USD" and t == "EUR":
        return float(amount) / fx
    raise DataError("conversion no soportada %s->%s" % (from_ccy, to_ccy))


# ---------------------------------------------------------------- costes MyInvestor
# Fuente oficial: myinvestor.es/inversion/broker (leido 2026-11-18)
#   acciones: 0,12 % por operacion, minimo 3 EUR, maximo 25 EUR
#   cambio de divisa: 0,30 % por operacion
MYINVESTOR = {"comision_pct": 0.0012, "min_eur": 3.0, "max_eur": 25.0, "fx_pct": 0.0030,
              "fuente": "myinvestor.es/inversion/broker (2026-11-18)"}


def coste_ida_vuelta_usd(notional_usd, currency="USD", cuenta_eur=True, eurusd_rate=None):
    """Coste total estimado de comprar y vender, en USD. Devuelve el desglose.

    La comision del broker se cobra en EUR: se convierte siempre a USD.
    El 0,30 % de cambio de divisa solo aplica si la cuenta esta en EUR y el valor no.
    """
    fx_rate = eurusd_rate or eurusd()
    comision_eur = min(max(MYINVESTOR["comision_pct"] * notional_usd / fx_rate, MYINVESTOR["min_eur"]),
                       MYINVESTOR["max_eur"])
    comision_usd = comision_eur * fx_rate
    fx_usd = (MYINVESTOR["fx_pct"] * notional_usd) if (cuenta_eur and currency.upper() != "EUR") else 0.0
    una = comision_usd + fx_usd
    return {"por_lado_usd": round(una, 2), "total_usd": round(2 * una, 2),
            "comision_usd": round(2 * comision_usd, 2), "fx_usd": round(2 * fx_usd, 2),
            "eurusd": round(fx_rate, 4), "fuente": MYINVESTOR["fuente"],
            "cuenta_eur": bool(cuenta_eur), "moneda_valor": currency.upper()}


def edad_dato_symbol(symbol):
    """Edad del ultimo dato en segundos, medido contra el reloj UTC."""
    q = quote(symbol)
    return q["age_seconds"], q
