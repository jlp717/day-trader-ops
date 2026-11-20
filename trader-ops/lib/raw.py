"""RAW NASDAQ LITE (nico66fx) en Python, para EE. UU. y para Xetra.

Regla del indicador original (Pine v6, `tradingview/RAW_NASDAQ_LITE.pine`):

1. Toma la primera vela de 5 minutos de la sesion (09:30 ET en EE. UU.).
2. Calcula una media exponencial de los cierres de 5 min con alfa 4/26.
3. Si el cierre de esa vela esta POR ENCIMA de la media -> COMPRA.
   Si esta POR DEBAJO -> VENTA. Si es igual -> sin operacion.
4. Una sola senal al dia, sin repintar, cuando la vela ya ha cerrado.

Adaptacion europea (`mercado="eu"`): misma regla con la primera vela de Xetra
(09:00-09:05 hora de Berlin, que es la misma que Madrid en invierno).

El indicador esta pensado para futuros del Nasdaq; se puede aplicar a cualquier
grafico, pero que tenga ventaja en acciones hay que medirlo, no suponerlo.

Solo lectura. No envia ordenes.
"""
import datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
BERLIN = ZoneInfo("Europe/Berlin")
ALPHA = 4.0 / 26.0

MERCADOS = {
    "us": {"tz": NY, "apertura": dt.time(9, 30), "etiqueta": "09:30 NY"},
    "eu": {"tz": BERLIN, "apertura": dt.time(9, 0), "etiqueta": "09:00 CET"},
}


def _cfg(mercado):
    return MERCADOS.get(str(mercado or "us").lower(), MERCADOS["us"])


def _local(ts, tz):
    return dt.datetime.fromtimestamp(int(ts), tz=tz)


def ema(closes, alpha=ALPHA):
    """Media exponencial recursiva, igual que `_k` del Pine."""
    out = []
    prev = None
    for c in closes:
        prev = float(c) if prev is None else prev + (float(c) - prev) * alpha
        out.append(prev)
    return out


def _por_dia(bars, tz):
    dias = {}
    for b in bars:
        if b.get("t") is None or b.get("c") is None:
            continue
        dias.setdefault(_local(b["t"], tz).date(), []).append(b)
    for d in dias:
        dias[d].sort(key=lambda x: x["t"])
    return dias


def senales(bars, mercado="us"):
    """[{date, dir, close, ema, high, low, entry, exit, pct}] por sesion."""
    cfg = _cfg(mercado)
    tz = cfg["tz"]
    apertura = cfg["apertura"]
    grupos = _por_dia(bars, tz)
    ordenadas = [b for d in sorted(grupos) for b in grupos[d]]
    if not ordenadas:
        return []
    cierres = [float(b["c"]) for b in ordenadas]
    medias = ema(cierres)
    idx = {id(b): i for i, b in enumerate(ordenadas)}
    out = []
    for dia in sorted(grupos):
        filas = grupos[dia]
        primera = next((b for b in filas if _local(b["t"], tz).time() == apertura), None)
        if primera is None:
            continue
        i = idx[id(primera)]
        c = float(primera["c"])
        e = medias[i]
        direccion = 1 if c > e else (-1 if c < e else 0)
        despues = [b for b in filas if _local(b["t"], tz).time() > apertura]
        entry = None
        if despues and despues[0].get("o") is not None:
            entry = float(despues[0]["o"])
        elif despues and despues[0].get("c") is not None:
            entry = float(despues[0]["c"])
        salida = float(filas[-1]["c"])
        pct = ((salida / entry - 1.0) * 100.0) if entry else None
        out.append({
            "date": dia.isoformat(),
            "dir": direccion,
            "close": c,
            "ema": e,
            "high": float(primera["h"]) if primera.get("h") is not None else None,
            "low": float(primera["l"]) if primera.get("l") is not None else None,
            "entry": entry,
            "exit": salida,
            "pct": pct,
            "mercado": str(mercado or "us").lower(),
        })
    return out


def ultima(bars, mercado="us"):
    filas = senales(bars, mercado)
    return filas[-1] if filas else None


def barras(symbol, rango="60d"):
    from . import datos
    doc = datos.chart(symbol, rango, "5m", ttl=3600)
    return [b for b in (doc.get("bars") or []) if b.get("c") is not None]


def plan(fila, max_loss=50.0, target_r=2.0, buffer_pct=0.0):
    """Stop, objetivo y tamaño para una señal larga. Solo si dir == 1."""
    if not fila or fila.get("dir") != 1:
        return None
    entry = float(fila["entry"] or fila["close"])
    stop = float(fila["low"] or entry) * (1.0 - abs(float(buffer_pct)) / 100.0)
    riesgo = entry - stop
    if riesgo <= 0:
        return None
    qty = int(float(max_loss) // riesgo)
    return {"entry": round(entry, 2), "stop": round(stop, 2),
            "target": round(entry + float(target_r) * riesgo, 2),
            "riesgo": round(riesgo, 3), "qty": qty,
            "riesgo_usd": round(qty * riesgo, 2)}


def texto_senal(fila, symbol, mercado="us", plan_=None):
    """Texto listo para Telegram/web con la senal del dia."""
    if not fila:
        return "Sin primera vela para %s (mercado cerrado o sin datos)." % symbol
    cfg = _cfg(mercado)
    etiqueta = {1: "COMPRA", -1: "VENTA", 0: "SIN OPERACION"}.get(fila["dir"], "?")
    out = ["<b>RAW %s</b> · %s · %s · %s" % (
        symbol, fila["date"], etiqueta, cfg["etiqueta"]),
        "cierre %.2f · EMA %.2f · max %.2f · min %.2f" % (
            fila["close"], fila["ema"], fila["high"] or 0, fila["low"] or 0)]
    if fila["dir"] == 1:
        out.append("Sesgo largo. Sobre %.2f sigue; bajo %.2f se invalida." % (
            fila["high"] or fila["close"], fila["low"] or fila["close"]))
        if plan_:
            out.append("Plan: entrada %.2f · stop %.2f · objetivo %.2f · %d acc (riesgo %.0f USD)" % (
                plan_["entry"], plan_["stop"], plan_["target"], plan_["qty"],
                plan_["riesgo_usd"]))
    elif fila["dir"] == -1:
        out.append("Sesgo corto: el sistema es solo largo, no se opera en corto.")
    else:
        out.append("Sin direccion clara: no se opera.")
    out.append("Misma regla que RAW NASDAQ LITE, adaptada a la primera vela de la sesion.")
    return "\n".join(out)


def backtest(bars, cost_pct=0.0, mercado="us"):
    """Mide el sesgo direccional contra la base (todos los dias)."""
    filas = [f for f in senales(bars, mercado) if f["pct"] is not None]
    if not filas:
        return {"n": 0}
    largos = [f["pct"] for f in filas if f["dir"] == 1]
    cortos = [f["pct"] for f in filas if f["dir"] == -1]
    base = [f["pct"] for f in filas]

    def res(v):
        if not v:
            return {"n": 0, "media": None, "acierto": None}
        return {"n": len(v), "media": sum(v) / len(v),
                "acierto": sum(1 for x in v if x > 0) / float(len(v))}

    r = {"n": len(filas), "compra": res(largos), "venta": res(cortos), "base": res(base)}
    if largos:
        r["neto_compra"] = sum(x - float(cost_pct) for x in largos) / len(largos)
    return r
