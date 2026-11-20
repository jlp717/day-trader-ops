"""Hipotesis de swing sobre barras diarias: reversion tras caida (RSI-2).

No es intradia: la senal se calcula con el cierre y se ejecuta en la apertura siguiente.
Encaja con MyInvestor (orden limitada a la apertura) y con el objetivo de saber, al abrir,
que candidatos hay y con que stop.

Reglas (pre-registradas, sin ajustar a la muestra):

- filtro de tendencia: cierre > media de 200 sesiones;
- entrada: RSI(2) < 10 al cierre -> compra en la apertura siguiente;
- salida: cierre > media de 5 sesiones, o RSI(2) > 65, o 5 sesiones, o stop -7 %;
- coste: 0,55 % ida y vuelta (0,12 % + 0,30 % FX de MyInvestor, redondeado arriba).

Solo mide. No envia nada.
"""
import datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def fecha(bar):
    t = bar.get("t")
    if t is None:
        return str(bar.get("date") or "")
    return dt.datetime.fromtimestamp(int(t), tz=NY).date().isoformat()


def sma(valores, n):
    out = [None] * len(valores)
    acc = 0.0
    for i, v in enumerate(valores):
        acc += float(v)
        if i >= n:
            acc -= float(valores[i - n])
        if i >= n - 1:
            out[i] = acc / n
    return out


def rsi(closes, n=2):
    """RSI de Wilder. None hasta tener n+1 cierres."""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = []
    losses = []
    for i in range(1, len(closes)):
        ch = float(closes[i]) - float(closes[i - 1])
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    out[n] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    for i in range(n + 1, len(closes)):
        ag = (ag * (n - 1) + gains[i - 1]) / n
        al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def senales(bars, *, rsi_buy=10.0, sma_trend=200):
    """Fechas (indices) en las que se cumple la compra al cierre."""
    closes = [float(b["c"]) for b in bars]
    r = rsi(closes, 2)
    trend = sma(closes, sma_trend)
    out = []
    for i in range(len(bars)):
        if r[i] is None or trend[i] is None:
            continue
        if closes[i] > trend[i] and r[i] < float(rsi_buy):
            out.append(i)
    return out


def simular(symbol, bars, *, cost_pct=0.55, rsi_buy=10.0, rsi_exit=65.0,
            sma_exit=5, sma_trend=200, max_days=5, stop_pct=7.0):
    """Lista de operaciones cerradas. Entrada y salida en la apertura siguiente."""
    if len(bars) < max(sma_trend + 5, 60):
        return []
    closes = [float(b["c"]) for b in bars]
    r = rsi(closes, 2)
    trend = sma(closes, sma_trend)
    salida = sma(closes, sma_exit)
    trades = []
    i = 0
    while i < len(bars) - 2:
        if r[i] is None or trend[i] is None or salida[i] is None:
            i += 1
            continue
        if not (closes[i] > trend[i] and r[i] < float(rsi_buy)):
            i += 1
            continue
        j = i + 1                      # entrada en la apertura siguiente
        entry = float(bars[j]["o"] if bars[j].get("o") is not None else closes[j])
        if entry <= 0:
            i += 1
            continue
        stop = entry * (1.0 - float(stop_pct) / 100.0)
        exit_px = None
        exit_day = None
        motivo = None
        for k in range(j, min(len(bars), j + int(max_days) + 1)):
            b = bars[k]
            if b.get("l") is not None and float(b["l"]) <= stop:
                exit_px, exit_day, motivo = stop, k, "stop"
                break
            if k > j and salida[k] is not None and closes[k] > salida[k]:
                exit_px, exit_day, motivo = closes[k], k, "sma"
                break
            if k > j and r[k] is not None and r[k] > float(rsi_exit):
                exit_px, exit_day, motivo = closes[k], k, "rsi"
                break
            if k == j + int(max_days) - 1:
                exit_px, exit_day, motivo = closes[k], k, "tiempo"
                break
        if exit_px is None:
            exit_px, exit_day, motivo = closes[min(len(closes) - 1, j + int(max_days))], \
                min(len(bars) - 1, j + int(max_days)), "fin"
        bruto = (exit_px / entry - 1.0) * 100.0
        trades.append({
            "symbol": str(symbol).upper(),
            "entry_date": fecha(bars[j]),
            "exit_date": fecha(bars[exit_day]),
            "entry": round(entry, 2),
            "exit": round(exit_px, 2),
            "days": exit_day - j,
            "gross_pct": round(bruto, 3),
            "net_pct": round(bruto - float(cost_pct), 3),
            "reason": motivo,
            "rsi_in": round(r[i], 1),
        })
        i = exit_day + 1
    return trades


def resumen(trades):
    n = len(trades)
    if not n:
        return {"n": 0, "win_rate": 0.0, "avg_net": 0.0, "total_net": 0.0,
                "expectancy": 0.0, "max_dd": 0.0, "avg_days": 0.0}
    nets = [t["net_pct"] for t in trades]
    wins = [x for x in nets if x > 0]
    total = sum(nets)
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for x in nets:
        eq += x
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {
        "n": n,
        "win_rate": len(wins) / float(n),
        "avg_net": total / n,
        "total_net": total,
        "expectancy": total / n,
        "max_dd": dd,
        "avg_days": sum(t["days"] for t in trades) / float(n),
        "avg_gross": sum(t["gross_pct"] for t in trades) / float(n),
    }


def partir(trades, frac=0.7):
    fechas = sorted({t["entry_date"] for t in trades})
    if len(fechas) < 2:
        return trades, []
    cut = max(1, min(len(fechas) - 1, int(round(len(fechas) * float(frac)))))
    is_days = set(fechas[:cut])
    return ([t for t in trades if t["entry_date"] in is_days],
            [t for t in trades if t["entry_date"] not in is_days])
