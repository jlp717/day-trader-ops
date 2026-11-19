"""Backtest del ORB sobre barras de 5 minutos de Yahoo.

Mide la mecanica de precio y los costes. No reproduce noticias, Time Machine,
Wilson ni EV historicos: esas capas no se pueden reconstruir con los datos
disponibles. Sirve para saber si el patron bruto tiene alguna ventaja.

    python trader-ops/run/backtest.py --symbols NVDA,AMD --days 30
"""
import csv
import datetime as dt
import json
from zoneinfo import ZoneInfo

from . import cfg
from . import datos
from . import estrategias

NY = ZoneInfo("America/New_York")


def barras_por_dia(symbol, days=30):
    """{date: [barras ordenadas]} de las ultimas `days` sesiones disponibles."""
    doc = datos.chart(symbol, "60d", "5m", ttl=6 * 3600)
    groups = {}
    for b in doc.get("bars") or []:
        if b.get("t") is None:
            continue
        day = dt.datetime.fromtimestamp(int(b["t"]), tz=NY).date()
        groups.setdefault(day, []).append(b)
    for day in groups:
        groups[day].sort(key=lambda x: x["t"])
    usables = sorted(groups)
    if days and len(usables) > days:
        usables = usables[-days:]
    return {d: groups[d] for d in usables}


def liquidez_20d(symbol):
    """Volumen medio en dolares de las ultimas 20 sesiones, o None."""
    doc = datos.chart(symbol, "3mo", "1d", ttl=6 * 3600)
    bars = [b for b in (doc.get("bars") or []) if b.get("c") and b.get("v")][-20:]
    if len(bars) < 10:
        return None
    return sum(float(b["c"]) * float(b["v"]) for b in bars) / len(bars)


def _coste(notional):
    return datos.coste_ida_vuelta_usd(notional)["total_usd"]


def correr(symbols, days=30, max_loss=50.0, min_dv=20_000_000.0,
           min_price=5.0, strategy="orb", con_costes=True, max_cost_r=None,
           or_minutes=15, target_r=2.0, stop_rule="mid",
           entry_cutoff=None, flat=None, slippage_bps=0.0):
    """Devuelve (trades, meta). No lanza por un simbolo roto: lo anota."""
    est = estrategias.get(strategy)
    trades = []
    meta = {"strategy": getattr(est, "nombre", strategy), "days": days,
            "max_loss": max_loss, "min_dv": min_dv, "min_price": min_price,
            "max_cost_r": max_cost_r, "or_minutes": or_minutes,
            "target_r": target_r, "stop_rule": stop_rule,
            "slippage_bps": slippage_bps, "symbols": {}}
    for sym in symbols:
        sym = sym.strip().upper()
        if not sym:
            continue
        info = {"trades": 0, "dias": 0, "dv20": None}
        try:
            if min_dv:
                info["dv20"] = liquidez_20d(sym)
                if info["dv20"] is not None and info["dv20"] < float(min_dv):
                    info["skip"] = "liquidez"
                    meta["symbols"][sym] = info
                    continue
            groups = barras_por_dia(sym, days)
            info["dias"] = len(groups)
            for day, bars in groups.items():
                kw = {}
                if entry_cutoff is not None:
                    kw["entry_cutoff"] = entry_cutoff
                if flat is not None:
                    kw["flat"] = flat
                t = est.simular_dia(
                    sym, day, bars, max_loss=max_loss,
                    comision_fn=_coste if con_costes else None,
                    min_price=min_price, or_minutes=or_minutes,
                    target_r=target_r, stop_rule=stop_rule,
                    slippage_bps=slippage_bps, **kw)
                if not t:
                    continue
                if max_cost_r is not None and t["qty"] and t["risk"]:
                    cr = t["cost_usd"] / (t["qty"] * t["risk"])
                    if cr > float(max_cost_r):
                        continue
                trades.append(t)
                info["trades"] += 1
        except Exception as exc:
            info["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
        meta["symbols"][sym] = info
    trades.sort(key=lambda x: (x["date"], x["entry_time"], x["symbol"]))
    return trades, meta


def resumen(trades):
    n = len(trades)
    if not n:
        return {"n": 0, "wins": 0, "win_rate": 0.0, "avg_net_r": 0.0,
                "total_net_r": 0.0, "total_pnl": 0.0, "profit_factor": None,
                "max_dd_r": 0.0, "avg_hold_min": 0.0, "avg_cost_r": 0.0,
                "pct_cost_gt1": 0.0, "by_symbol": {}}
    wins = [t for t in trades if t["net_r"] > 0]
    losses = [t for t in trades if t["net_r"] <= 0]
    total_r = sum(t["net_r"] for t in trades)
    total_pnl = sum(t["pnl_usd"] for t in trades)
    pos = sum(t["pnl_usd"] for t in trades if t["pnl_usd"] > 0)
    neg = abs(sum(t["pnl_usd"] for t in trades if t["pnl_usd"] < 0))
    cum = 0.0
    peak = 0.0
    dd = 0.0
    for t in sorted(trades, key=lambda x: (x["date"], x["entry_time"])):
        cum += t["net_r"]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    holds = []
    cost_rs = []
    for t in trades:
        try:
            a = dt.datetime.strptime(t["entry_time"], "%H:%M")
            b = dt.datetime.strptime(t["exit_time"], "%H:%M")
            if b < a:
                b += dt.timedelta(days=1)
            holds.append((b - a).total_seconds() / 60.0)
        except Exception:
            pass
        if t.get("qty") and t.get("risk"):
            cost_rs.append(t["cost_usd"] / (t["qty"] * t["risk"]))
    by = {}
    for t in trades:
        d = by.setdefault(t["symbol"], {"n": 0, "net_r": 0.0, "pnl": 0.0})
        d["n"] += 1
        d["net_r"] += t["net_r"]
        d["pnl"] += t["pnl_usd"]
    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / float(n),
        "avg_net_r": total_r / n,
        "total_net_r": total_r,
        "total_pnl": total_pnl,
        "profit_factor": (pos / neg) if neg else None,
        "max_dd_r": dd,
        "avg_hold_min": (sum(holds) / len(holds)) if holds else 0.0,
        "avg_cost_r": (sum(cost_rs) / len(cost_rs)) if cost_rs else 0.0,
        "pct_cost_gt1": (sum(1 for x in cost_rs if x > 1) / float(len(cost_rs))) if cost_rs else 0.0,
        "by_symbol": by,
    }


def partir(trades, frac=0.7):
    """Divide por fechas: primeras `frac` in-sample, resto out-of-sample."""
    fechas = sorted({t["date"] for t in trades})
    if len(fechas) < 2:
        return trades, []
    cut = max(1, min(len(fechas) - 1, int(round(len(fechas) * float(frac)))))
    is_days = set(fechas[:cut])
    return ([t for t in trades if t["date"] in is_days],
            [t for t in trades if t["date"] not in is_days])


def guardar_json(path, trades, meta, res, extra=None):
    doc = {"meta": meta, "resumen": res}
    if extra:
        doc.update(extra)
    doc["trades"] = trades
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def guardar_csv(path, trades):
    campos = ["date", "entry_time", "exit_time", "symbol", "or_high", "or_low",
              "or_mid", "entry", "entry_fill", "stop", "target", "qty", "exit",
              "exit_fill", "exit_reason", "gross_r", "net_r", "cost_usd", "pnl_usd"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for t in trades:
            w.writerow(t)


def guardar_features(path, trades):
    """CSV de features/labels para un futuro modelo. No entrena nada."""
    campos = ["date", "entry_time", "symbol", "or_high", "or_low", "or_mid",
              "entry", "stop", "target", "qty", "risk", "entry_fill",
              "exit_fill", "exit_reason", "gross_r", "net_r", "cost_usd", "pnl_usd"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for t in trades:
            w.writerow(t)


def imprimir(trades, meta, res, limite=15):
    print("Backtest %s · hasta %d sesiones · %d simbolos" % (
        meta.get("strategy"), meta.get("days"), len(meta.get("symbols") or {})))
    for sym, info in (meta.get("symbols") or {}).items():
        if info.get("error"):
            print("  %-6s ERROR %s" % (sym, info["error"]))
        elif info.get("skip"):
            print("  %-6s saltado (%s)" % (sym, info["skip"]))
        else:
            dv = info.get("dv20")
            print("  %-6s %2d trades · %2d dias%s" % (
                sym, info.get("trades", 0), info.get("dias", 0),
                (" · %.1f M USD/dia" % (dv / 1e6)) if dv else ""))
    if not res["n"]:
        print("\nSin operaciones: revisa simbolos, dias, liquidez o precio minimo.")
        return
    print("\nTotal: %d trades · %d ganadoras (%.1f%%) · R neto %+.2f · PnL %+.2f USD" % (
        res["n"], res["wins"], 100 * res["win_rate"], res["total_net_r"], res["total_pnl"]))
    print("R medio %+.3f · factor beneficio %s · max drawdown %.2fR · duracion media %.0f min" % (
        res["avg_net_r"],
        ("%.2f" % res["profit_factor"]) if res["profit_factor"] else "n/d",
        res["max_dd_r"], res["avg_hold_min"]))
    print("Coste medio %.2fR · trades con coste >1R: %.1f%%" % (
        res["avg_cost_r"], 100 * res["pct_cost_gt1"]))
    print("\nUltimos %d trades:" % min(limite, res["n"]))
    print("fecha      entrada  sym    entry   stop   target  exit   R     motivo")
    for t in trades[-limite:]:
        print("%s %s  %-6s %7.2f %6.2f %7.2f %6.2f %+5.2f  %s" % (
            t["date"], t["entry_time"], t["symbol"], t["entry"], t["stop"],
            t["target"], t["exit"], t["net_r"], t["exit_reason"]))
