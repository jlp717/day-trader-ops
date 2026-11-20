"""Tesis de aguante: decidir con reglas si una posicion se mantiene o se rompe.

NO predice. Comprueba si la estructura que sostenia la compra sigue viva y, si lo
esta, evita que un retroceso normal te saque por panico. Es una lista de
comprobacion con niveles, no una bola de cristal.

Reglas pre-registradas (documentadas en `REFERENCIA.md` §14):

- estructura: cierre > SMA200 y SMA50 > SMA200 y caida desde maximo de 52
  semanas <= 15 % -> `intacta`.
- `observacion`: cierre > SMA200 pero SMA50 < SMA200, o caida 15–25 %.
- `rota`: cierre < SMA200 o caida > 25 %.
- `zona_venta`: a menos del 2 % del maximo de 52 semanas y RSI(14) >= 70.
- fundamentos (Finnhub, opcional): crecimiento de ingresos negativo o margen
  neto negativo rebajan `intacta` a `observacion`.

El modo aguante lo marca el usuario (`marcar`). Mientras la tesis no este `rota`,
el vigilante avisa de un nivel con contexto en vez de alarmar.
"""
from . import cfg
from . import datos
from . import zonatiempo as zt

ESTADO = cfg.STATE / "tesis.json"
CACHE = cfg.STATE / "tesis_cache.json"
FINNHUB_METRIC = "https://finnhub.io/api/v1/stock/metric?symbol=%s&metric=all&token=%s"
CACHE_TTL = 6 * 3600


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


def evaluar(symbol):
    """Veredicto con motivos. No lanza: devuelve error si falta historia."""
    try:
        e = estructura(symbol)
    except Exception as exc:
        return {"symbol": str(symbol).upper(), "error": str(exc)[:160], "veredicto": "sin datos"}
    motivos = []
    s200 = e["sma200"]
    s50 = e["sma50"]
    c = e["close"]
    veredicto = "intacta"
    if s200 is None:
        return {"symbol": e["symbol"], "error": "sin SMA200", "veredicto": "sin datos"}
    if c < s200:
        veredicto = "rota"
        motivos.append("cierre %.2f por debajo de la SMA200 %.2f" % (c, s200))
    elif e["drawdown_pct"] <= -25:
        veredicto = "rota"
        motivos.append("caida de %.1f %% desde el maximo de 52 semanas" % e["drawdown_pct"])
    elif s50 is not None and s50 < s200:
        veredicto = "observacion"
        motivos.append("SMA50 %.2f por debajo de la SMA200 %.2f" % (s50, s200))
    elif e["drawdown_pct"] <= -15:
        veredicto = "observacion"
        motivos.append("caida de %.1f %% desde el maximo" % e["drawdown_pct"])
    if not motivos:
        motivos.append("precio sobre SMA200 y SMA50 sobre SMA200")

    f = fundamentos(symbol)
    if f:
        rev = f.get("revenueGrowthTTMYoy")
        margen = f.get("netProfitMarginTTM")
        if rev is not None and float(rev) < 0:
            motivos.append("ingresos decreciendo %.1f %%" % float(rev))
            if veredicto == "intacta":
                veredicto = "observacion"
        if margen is not None and float(margen) < 0:
            motivos.append("margen neto negativo %.1f %%" % float(margen))
            if veredicto == "intacta":
                veredicto = "observacion"

    zona_venta = False
    if e["high52"] and c >= e["high52"] * 0.98 and (e["rsi14"] or 0) >= 70:
        zona_venta = True
        motivos.append("a %.1f %% del maximo de 52 semanas con RSI14 %.0f" % (
            (c / e["high52"] - 1.0) * 100.0, e["rsi14"] or 0))

    stop_tesis = round(s200 * 0.97, 2)
    return {
        "symbol": e["symbol"],
        "veredicto": veredicto,
        "motivos": motivos,
        "zona_venta": zona_venta,
        "stop_tesis": stop_tesis,
        "sma200": round(s200, 2),
        "sma50": round(s50, 2) if s50 else None,
        "drawdown_pct": round(e["drawdown_pct"], 2),
        "rsi14": round(e["rsi14"], 1) if e["rsi14"] is not None else None,
        "high52": round(e["high52"], 2),
        "low52": round(e["low52"], 2),
        "atr_pct": round(e["atr_pct"], 2) if e["atr_pct"] is not None else None,
        "fundamentos": f,
        "aguantar": en_aguante(e["symbol"]),
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
    r = evaluar(symbol)
    if r.get("error"):
        return "Sin datos para %s: %s" % (symbol, r["error"])
    etiqueta = {"intacta": "INTACTA", "observacion": "EN OBSERVACION",
                "rota": "ROTA"}.get(r["veredicto"], r["veredicto"])
    out = ["<b>Tesis %s</b> · %s%s" % (r["symbol"], etiqueta,
                                       " · modo aguante" if r["aguantar"] else ""),
           "SMA200 %.2f · SMA50 %s · caida %.1f %% · RSI14 %s" % (
               r["sma200"], ("%.2f" % r["sma50"]) if r["sma50"] else "n/d",
               r["drawdown_pct"], r["rsi14"] if r["rsi14"] is not None else "n/d")]
    for m in r["motivos"]:
        out.append("  - " + m)
    out.append("Stop de tesis: %.2f (3 %% bajo la SMA200)" % r["stop_tesis"])
    if r["zona_venta"]:
        out.append("Zona de venta: extendida; el sistema sugiere recoger parte.")
    if r["aguantar"]:
        out.append("Modo aguante: los niveles avisan con contexto, no alarman.")
    return "\n".join(out)
