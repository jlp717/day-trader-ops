"""Tesis de aguante: dos horizontes separados, sin predicciones.

Responde a dos preguntas distintas, que antes se mezclaban:

- **Corto plazo (dias-semanas)**: ?la estructura de trading esta a favor o en
  contra? Es lo que decide un stop y lo que usa el vigilante.
- **Largo plazo (meses-anos)**: ?la tesis de inversion sigue viva? Se apoya en
  fundamentos (Finnhub), pendiente de la SMA200 y caida desde maximos.

Una empresa puede tener el corto en contra y el largo vivo: eso se dice tal cual,
sin recomendar vender. No predice: comprueba y pone niveles.

Reglas documentadas en `REFERENCIA.md` §14.
"""
from . import cfg
from . import datos
from . import zonatiempo as zt
import datetime as dt

ESTADO = cfg.STATE / "tesis.json"
CACHE = cfg.STATE / "tesis_cache.json"
CACHE_NEWS = cfg.STATE / "noticias_cache.json"
FINNHUB_METRIC = "https://finnhub.io/api/v1/stock/metric?symbol=%s&metric=all&token=%s"
FINNHUB_NEWS = ("https://finnhub.io/api/v1/company-news?symbol=%s&from=%s&to=%s&token=%s")
FINNHUB_PEERS = "https://finnhub.io/api/v1/stock/peers?symbol=%s&token=%s"
CACHE_TTL = 6 * 3600
NEWS_TTL = 30 * 60

ETIQUETAS = (
    ("upgrade", ("upgrade", "raises price target", "outperform", "overweight", "buy rating")),
    ("downgrade", ("downgrade", "cuts price target", "underperform", "underweight", "sell rating")),
    ("resultados", ("earnings", "quarterly", "revenue", "profit", "eps", "beats", "misses")),
    ("guia", ("guidance", "outlook", "forecast")),
    ("acuerdo", ("partnership", "contract", "deal", "collaborat", "supplier", "order")),
    ("riesgo", ("lawsuit", "probe", "investigation", "recall", "halt", "fraud", "sec ")),
    ("fusion", ("acquisition", "merger", "takeover", "stake")),
    ("empleo", ("layoff", "job cuts", "restructur")),
)


def _barras(symbol, rango="1y"):
    doc = datos.chart(symbol, rango, "1d", ttl=6 * 3600)
    return [b for b in (doc.get("bars") or []) if b.get("c") is not None]


def _sma(valores, n):
    out = [None] * len(valores)
    acc = 0.0
    for i, v in enumerate(valores):
        acc += float(v)
        if i >= n:
            acc -= float(valores[i - n])
        if i >= n - 1:
            out[i] = acc / n
    return out


def _rsi(closes, n=14):
    if len(closes) <= n:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        ch = float(closes[i]) - float(closes[i - 1])
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def estructura(symbol):
    """Metricas de tendencia y niveles. Lanza DataError si no hay historia."""
    bars = _barras(symbol)
    if len(bars) < 210:
        raise datos.DataError("historial insuficiente para %s (%d sesiones)" % (symbol, len(bars)))
    closes = [float(b["c"]) for b in bars]
    highs = [float(b["h"]) for b in bars if b.get("h") is not None]
    lows = [float(b["l"]) for b in bars if b.get("l") is not None]
    s20 = _sma(closes, 20)
    s50 = _sma(closes, 50)
    s200 = _sma(closes, 200)
    last = closes[-1]
    alto = max(highs[-252:]) if highs else max(closes)
    bajo = min(lows[-252:]) if lows else min(closes)
    caida = (last / alto - 1.0) * 100.0 if alto else 0.0
    pendiente = None
    if len(s200) >= 21 and s200[-1] is not None and s200[-21] is not None:
        pendiente = (s200[-1] / s200[-21] - 1.0) * 100.0
    atr = None
    if len(bars) >= 15:
        trs = []
        for i in range(len(bars) - 14, len(bars)):
            h = bars[i].get("h")
            l = bars[i].get("l")
            pc = closes[i - 1]
            if h is None or l is None:
                continue
            trs.append(max(float(h) - float(l), abs(float(h) - pc), abs(float(l) - pc)))
        if trs:
            atr = sum(trs) / len(trs)
    return {
        "symbol": str(symbol).upper(),
        "close": last,
        "sma20": s20[-1],
        "sma50": s50[-1],
        "sma200": s200[-1],
        "sma200_slope20_pct": pendiente,
        "high52": alto,
        "low52": bajo,
        "drawdown_pct": caida,
        "rsi14": _rsi(closes),
        "atr": atr,
        "atr_pct": (atr / last * 100.0) if atr and last else None,
        "fecha": zt.madrid().date().isoformat(),
    }


def fundamentos(symbol):
    """Metricas basicas de Finnhub. Devuelve {} si no hay clave o falla."""
    key = datos._finnhub_key() if hasattr(datos, "_finnhub_key") else None
    if not key:
        return {}
    sym = str(symbol).upper()
    cache = cfg.read_json(CACHE, {}) or {}
    guardado = cache.get(sym) or {}
    if guardado.get("ts") and (zt.now_utc().timestamp() - float(guardado["ts"])) < CACHE_TTL:
        return guardado.get("datos") or {}
    try:
        doc = datos.http_json_url(FINNHUB_METRIC % (sym, key))
        m = (doc or {}).get("metric") or {}
    except Exception:
        return {}
    out = {}
    for campo in ("peTTM", "revenueGrowthTTMYoy", "netProfitMarginTTM",
                  "roeTTM", "beta", "52WeekHigh", "52WeekLow"):
        if m.get(campo) is not None:
            out[campo] = m[campo]
    if out:
        cache[sym] = {"ts": zt.now_utc().timestamp(), "datos": out}
        cfg.write_json(CACHE, cache)
    return out


def _etiquetas(titular):
    t = str(titular or "").lower()
    return [nombre for nombre, palabras in ETIQUETAS
            if any(p in t for p in palabras)]


def noticias(symbol, dias=7, limite=8):
    """Titulares recientes de Finnhub con etiquetas simples. [] si no hay clave."""
    key = datos._finnhub_key() if hasattr(datos, "_finnhub_key") else None
    if not key:
        return []
    sym = str(symbol).upper()
    cache = cfg.read_json(CACHE_NEWS, {}) or {}
    guardado = cache.get(sym) or {}
    if guardado.get("ts") and (zt.now_utc().timestamp() - float(guardado["ts"])) < NEWS_TTL:
        return guardado.get("datos") or []
    hasta = zt.madrid().date()
    desde = hasta - dt.timedelta(days=int(dias))
    try:
        doc = datos.http_json_url(FINNHUB_NEWS % (
            sym, desde.isoformat(), hasta.isoformat(), key))
    except Exception:
        return []
    filas = []
    for n in (doc if isinstance(doc, list) else [])[:int(limite)]:
        titular = str(n.get("headline") or "").strip()
        if not titular:
            continue
        filas.append({
            "headline": titular[:180],
            "source": str(n.get("source") or "")[:40],
            "ts": n.get("datetime"),
            "url": str(n.get("url") or "")[:300],
            "tags": _etiquetas(titular),
        })
    filas.sort(key=lambda x: x.get("ts") or 0, reverse=True)
    cache[sym] = {"ts": zt.now_utc().timestamp(), "datos": filas}
    cfg.write_json(CACHE_NEWS, cache)
    return filas


def pares(symbol):
    """Competidores segun Finnhub. [] si el plan no lo permite."""
    key = datos._finnhub_key() if hasattr(datos, "_finnhub_key") else None
    if not key:
        return []
    try:
        doc = datos.http_json_url(FINNHUB_PEERS % (str(symbol).upper(), key))
    except Exception:
        return []
    return [str(x).upper() for x in (doc if isinstance(doc, list) else [])][:6]


def _corto(e):
    motivos = []
    veredicto = "a favor"
    if e["close"] < (e["sma200"] or 0):
        veredicto = "en contra"
        motivos.append("cierre %.2f bajo la SMA200 %.2f" % (e["close"], e["sma200"]))
    if e["sma50"] and e["sma200"] and e["sma50"] < e["sma200"]:
        veredicto = "en contra"
        motivos.append("SMA50 %.2f bajo la SMA200 %.2f" % (e["sma50"], e["sma200"]))
    if e["drawdown_pct"] <= -25:
        veredicto = "en contra"
        motivos.append("caida de %.1f %% desde el maximo de 52 semanas" % abs(e["drawdown_pct"]))
    elif e["drawdown_pct"] <= -15 and veredicto == "a favor":
        veredicto = "neutral"
        motivos.append("caida de %.1f %% desde el maximo" % abs(e["drawdown_pct"]))
    if not motivos:
        motivos.append("precio sobre SMA200 y SMA50 sobre SMA200")
    zona_venta = bool(e["high52"] and e["close"] >= e["high52"] * 0.98
                      and (e["rsi14"] or 0) >= 70)
    if zona_venta:
        motivos.append("extendido: a %.1f %% del maximo con RSI14 %.0f" % (
            (e["close"] / e["high52"] - 1.0) * 100.0, e["rsi14"] or 0))
    return {"veredicto": veredicto, "motivos": motivos,
            "zona_venta": zona_venta,
            "stop": round((e["sma200"] or e["close"]) * 0.97, 2)}


def _largo(e, f):
    puntos = []
    score = 0
    if e["close"] > (e["sma200"] or 0):
        score += 1
        puntos.append("precio sobre la SMA200")
    else:
        puntos.append("precio bajo la SMA200")
    pend = e.get("sma200_slope20_pct")
    if pend is not None and pend > 0.5:
        score += 1
        puntos.append("SMA200 girando al alza (%.1f %% en 20 sesiones)" % pend)
    elif pend is not None and pend < -0.5:
        puntos.append("SMA200 con pendiente negativa (%.1f %%)" % pend)
    elif pend is not None:
        puntos.append("SMA200 plana (%.1f %% en 20 sesiones)" % pend)
    if e["drawdown_pct"] > -30:
        score += 1
        puntos.append("caida contenida (%.1f %%)" % abs(e["drawdown_pct"]))

    if f:
        rev = f.get("revenueGrowthTTMYoy")
        margen = f.get("netProfitMarginTTM")
        roe = f.get("roeTTM")
        if rev is not None:
            if float(rev) > 0:
                score += 1
            puntos.append("ingresos %+.1f %% interanual" % float(rev))
        if margen is not None:
            if float(margen) > 0:
                score += 1
            puntos.append("margen neto %.1f %%" % float(margen))
        if roe is not None:
            if float(roe) > 0:
                score += 1
            puntos.append("ROE %.1f %%" % float(roe))
        maximo = 6
    else:
        maximo = 3
        puntos.append("sin fundamentales disponibles (clave Finnhub o plan)")

    if maximo == 6:
        veredicto = "viva" if score >= 5 else ("en riesgo" if score >= 3 else "rota")
    else:
        veredicto = "viva" if score >= 3 else ("en riesgo" if score >= 2 else "rota")

    recuperar = None
    if e["sma200"] and e["close"] < e["sma200"]:
        recuperar = {"nivel": round(e["sma200"], 2),
                     "pct": round((e["sma200"] / e["close"] - 1.0) * 100.0, 1)}
    return {"veredicto": veredicto, "score": score, "maximo": maximo,
            "motivos": puntos, "recuperar": recuperar}


def evaluar(symbol, con_noticias=False):
    """Evalua los dos horizontes. No lanza: devuelve error si falta historia."""
    try:
        e = estructura(symbol)
    except Exception as exc:
        return {"symbol": str(symbol).upper(), "error": str(exc)[:160],
                "veredicto": "sin datos"}
    if e["sma200"] is None:
        return {"symbol": e["symbol"], "error": "sin SMA200", "veredicto": "sin datos"}
    f = fundamentos(symbol)
    corto = _corto(e)
    largo = _largo(e, f)
    return {
        "symbol": e["symbol"],
        "corto": corto,
        "largo": largo,
        "noticias": noticias(symbol) if con_noticias else [],
        "pares": pares(symbol) if con_noticias else [],
        "sma200": round(e["sma200"], 2),
        "sma50": round(e["sma50"], 2) if e["sma50"] else None,
        "drawdown_pct": round(e["drawdown_pct"], 2),
        "rsi14": round(e["rsi14"], 1) if e["rsi14"] is not None else None,
        "high52": round(e["high52"], 2),
        "low52": round(e["low52"], 2),
        "atr_pct": round(e["atr_pct"], 2) if e["atr_pct"] is not None else None,
        "fundamentos": f,
        "aguantar": en_aguante(e["symbol"]),
        # compatibilidad con el vigilante y el resto del codigo
        "veredicto": ("intacta" if corto["veredicto"] == "a favor"
                      else "rota" if corto["veredicto"] == "en contra" else "observacion"),
        "zona_venta": corto["zona_venta"],
        "stop_tesis": corto["stop"],
    }


def _load():
    doc = cfg.read_json(ESTADO, {}) or {}
    if not isinstance(doc.get("marcas"), dict):
        doc["marcas"] = {}
    return doc


def marcar(symbol, aguantar=True):
    sym = str(symbol).upper().strip()
    doc = _load()
    doc["marcas"][sym] = {"aguantar": bool(aguantar),
                          "ts_madrid": zt.madrid().isoformat(timespec="seconds")}
    cfg.write_json(ESTADO, doc)
    return doc["marcas"][sym]


def en_aguante(symbol):
    return bool((_load()["marcas"].get(str(symbol).upper()) or {}).get("aguantar"))


def texto(symbol):
    r = evaluar(symbol, con_noticias=True)
    if r.get("error"):
        return "Sin datos para %s: %s" % (symbol, r["error"])
    c, l = r["corto"], r["largo"]
    out = ["<b>Tesis %s</b> · corto %s · largo %s%s" % (
        r["symbol"], c["veredicto"].upper(), l["veredicto"].upper(),
        " · aguante" if r["aguantar"] else ""),
        "",
        "<b>Corto plazo</b> (dias-semanas)"]
    for m in c["motivos"]:
        out.append("  - " + m)
    out.append("  Stop de estructura: %.2f (3 %% bajo la SMA200)" % r["stop_tesis"])

    out.append("")
    out.append("<b>Largo plazo</b> (meses-anos) · %d/%d" % (l["score"], l["maximo"]))
    for m in l["motivos"]:
        out.append("  - " + m)
    if l.get("recuperar"):
        out.append("  Para recomponer: cerrar sobre %.2f (+%.1f %%)" % (
            l["recuperar"]["nivel"], l["recuperar"]["pct"]))

    if r.get("noticias"):
        out.append("")
        out.append("<b>Noticias</b> (7 dias)")
        for n in r["noticias"][:5]:
            etiqueta = (" [" + ",".join(n["tags"]) + "]") if n.get("tags") else ""
            out.append("  - %s%s" % (n["headline"][:110], etiqueta))
    if r.get("pares"):
        out.append("")
        out.append("Pares: " + ", ".join(r["pares"]))
    out.append("")
    out.append("No es una prediccion ni una orden: es estructura, fundamentos y niveles.")
    return "\n".join(out)
