"""RAW NASDAQ LITE (nico66fx) en Python, para cualquier simbolo.

Regla del indicador original (Pine v6, `tradingview/RAW_NASDAQ_LITE.pine`):

1. Toma la primera vela de 5 minutos de Nueva York (09:30-09:35 ET).
2. Calcula una media exponencial de los cierres de 5 min con alfa 4/26.
3. Si el cierre de esa vela esta POR ENCIMA de la media -> COMPRA.
   Si esta POR DEBAJO -> VENTA. Si es igual -> sin operacion.
4. Una sola senal al dia, sin repintar, cuando la vela ya ha cerrado.

El indicador original esta pensado para futuros del Nasdaq (MNQ/NQ), pero usa
`syminfo.tickerid`, asi que se puede aplicar a cualquier grafico, incluida una
accion suelta como NVDA. Otra cosa es que tenga ventaja en acciones: eso se mide
con `run/raw.py --backtest`, no se supone.

Solo lectura. No envia ordenes.
"""
import datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
ALPHA = 4.0 / 26.0
APERTURA = dt.time(9, 30)


def _ny(ts):
    return dt.datetime.fromtimestamp(int(ts), tz=NY)


def ema(closes, alpha=ALPHA):
    """Media exponencial recursiva, igual que `_k` del Pine."""
    out = []
    prev = None
    for c in closes:
        prev = float(c) if prev is None else prev + (float(c) - prev) * alpha
        out.append(prev)
    return out


def _por_dia(bars):
    dias = {}
    for b in bars:
        if b.get("t") is None or b.get("c") is None:
            continue
        dias.setdefault(_ny(b["t"]).date(), []).append(b)
    for d in dias:
        dias[d].sort(key=lambda x: x["t"])
    return dias


def senales(bars):
    """[{date, dir, close, ema, high, low, entry, exit, pct}] por sesion.

    `entry` es la apertura de la barra siguiente al cierre de 09:35 (la entrada
    realista: el indicador avisa cuando la vela ya cerro) y `exit` el ultimo
    cierre de la sesion.
    """
    grupos = _por_dia(bars)
    ordenadas = [b for d in sorted(grupos) for b in grupos[d]]
    if not ordenadas:
        return []
    cierres = [float(b["c"]) for b in ordenadas]
    medias = ema(cierres)
    idx = {id(b): i for i, b in enumerate(ordenadas)}
    out = []
    for dia in sorted(grupos):
        filas = grupos[dia]
        primera = next((b for b in filas if _ny(b["t"]).time() == APERTURA), None)
        if primera is None:
            continue
        i = idx[id(primera)]
        c = float(primera["c"])
        e = medias[i]
        direccion = 1 if c > e else (-1 if c < e else 0)
        despues = [b for b in filas if _ny(b["t"]).time() > dt.time(9, 30)]
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
        })
    return out


def ultima(bars):
    filas = senales(bars)
    return filas[-1] if filas else None


def texto_senal(fila, symbol):
    """Texto listo para Telegram/web con la senal del dia."""
    if not fila:
        return "Sin vela de 09:30 para %s (mercado cerrado o sin datos)." % symbol
    etiqueta = {1: "COMPRA", -1: "VENTA", 0: "SIN OPERACION"}.get(fila["dir"], "?")
    out = ["<b>RAW %s</b> · %s · %s" % (symbol, fila["date"], etiqueta),
           "cierre 09:35 %.2f · EMA %.2f · max %.2f · min %.2f" % (
               fila["close"], fila["ema"],
               fila["high"] or 0, fila["low"] or 0)]
    if fila["dir"] == 1:
        out.append("Sesgo largo. Sobre %.2f sigue; bajo %.2f se invalida." % (
            fila["high"] or fila["close"], fila["low"] or fila["close"]))
    elif fila["dir"] == -1:
        out.append("Sesgo corto: el sistema es solo largo, no se opera en corto.")
    else:
        out.append("Sin direccion clara: no se opera.")
    out.append("Indicador de futuros del Nasdaq; en acciones hay que medirlo, no suponerlo.")
    return "\n".join(out)


def barras(symbol, rango="60d"):
    from . import datos
    doc = datos.chart(symbol, rango, "5m", ttl=3600)
    return [b for b in (doc.get("bars") or []) if b.get("c") is not None]


def backtest(bars, cost_pct=0.0, solo_largos=True):
    """Mide el sesgo direccional: COMPRA vs resto de dias.

    Devuelve un dict con la media de las COMPRA, la de las VENTA y la base
    (todos los dias), que es lo que hay que batir para tener ventaja.
    """
    filas = [f for f in senales(bars) if f["pct"] is not None]
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
    if solo_largos and largos:
        r["neto_compra"] = sum(x - float(cost_pct) for x in largos) / len(largos)
    return r
