"""Backtest y radar de la hipotesis de swing RSI-2 (solo lectura, sin ordenes).

    python trader-ops/run/swing.py --years 2 --split 0.7
    python trader-ops/run/swing.py --hoy
    python trader-ops/run/swing.py --hoy --send

`--hoy` responde a la pregunta operativa: al abrir, que candidatos cumplen el patron.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import cfg, datos, swing  # noqa: E402

UNIVERSO = ("AAPL,MSFT,NVDA,AMD,AMZN,GOOGL,META,TSLA,AVGO,NFLX,CRM,ORCL,ADBE,INTC,MU,"
            "QCOM,JPM,BAC,GS,XOM,CVX,JNJ,PFE,UNH,LLY,WMT,COST,HD,DIS,BA,CAT,GE,F,GM,"
            "T,VZ,KO,PEP,MCD,NKE")


def universo():
    doc = cfg.read_json(cfg.STATE / "scan_universe.json", {}) or {}
    syms = doc.get("symbols") or doc.get("universe") or []
    if isinstance(syms, list) and len(syms) >= 20:
        return [str(s).upper() for s in syms if str(s).strip()][:120]
    return UNIVERSO.split(",")


def barras(sym, years=2):
    doc = datos.chart(sym, "%dy" % int(years), "1d", ttl=6 * 3600)
    return [b for b in (doc.get("bars") or []) if b.get("c") is not None]


def correr(syms, years=2):
    trades = []
    fallos = {}
    for s in syms:
        try:
            tr = swing.simular(s, barras(s, years))
        except Exception as exc:
            fallos[s] = "%s: %s" % (type(exc).__name__, str(exc)[:80])
            continue
        trades.extend(tr)
    trades.sort(key=lambda t: (t["entry_date"], t["symbol"]))
    return trades, fallos


def hoy(syms=None, rsi_buy=10.0):
    syms = syms or universo()
    filas = []
    for s in syms:
        try:
            bars = barras(s, 1)
            if len(bars) < 210:
                continue
            closes = [float(b["c"]) for b in bars]
            r = swing.rsi(closes, 2)
            trend = swing.sma(closes, 200)
            i = len(bars) - 1
            if r[i] is None or trend[i] is None:
                continue
            if closes[i] > trend[i] and r[i] < float(rsi_buy):
                filas.append({"symbol": s, "close": round(closes[i], 2),
                              "rsi2": round(r[i], 1),
                              "sma200": round(trend[i], 2),
                              "stop": round(closes[i] * 0.93, 2),
                              "fecha": swing.fecha(bars[i])})
        except Exception:
            continue
    filas.sort(key=lambda x: x["rsi2"])
    return filas


def texto_hoy(filas, max_loss=None):
    if not filas:
        return "Sin candidatos RSI-2 hoy. El silencio es una decision."
    out = ["<b>Candidatos RSI-2</b> (comprar en la apertura, solo si abre sin hueco loco)"]
    for f in filas[:12]:
        linea = "  %s cierre %.2f · RSI2 %.1f · SMA200 %.2f · stop %.2f" % (
            f["symbol"], f["close"], f["rsi2"], f["sma200"], f["stop"])
        if max_loss:
            riesgo = f["close"] - f["stop"]
            if riesgo > 0:
                linea += " · %d acc" % int(float(max_loss) // riesgo)
        out.append(linea)
    out.append("Salida: cierre > SMA5, RSI2 > 65 o 5 sesiones. No es intradia.")
    return "\n".join(out)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Swing RSI-2: backtest y radar")
    ap.add_argument("--symbols", help="lista separada por comas")
    ap.add_argument("--years", type=int, default=2)
    ap.add_argument("--split", type=float, default=0.7)
    ap.add_argument("--json", help="guardar trades y resumen")
    ap.add_argument("--hoy", action="store_true", help="candidatos de hoy")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--max-loss", type=float, default=None)
    a = ap.parse_args(argv)
    max_loss = a.max_loss if a.max_loss is not None else float(
        (cfg.config().get("risk") or {}).get("max_loss_usd") or 50.0)

    if a.hoy:
        filas = hoy([x.strip().upper() for x in a.symbols.split(",")] if a.symbols else None)
        txt = texto_hoy(filas, max_loss)
        print(txt.replace("<b>", "").replace("</b>", ""))
        if a.json:
            with open(a.json, "w", encoding="utf-8") as f:
                json.dump(filas, f, ensure_ascii=False, indent=2)
            print("\nJSON: %s" % a.json)
        if a.send and filas:
            from lib import telegram as tg
            try:
                tg.Telegram().send(txt)
            except Exception as exc:
                print("ERROR Telegram: %s" % exc)
        return 0

    syms = [x.strip().upper() for x in (a.symbols or UNIVERSO).split(",") if x.strip()]
    trades, fallos = correr(syms, a.years)
    res = swing.resumen(trades)
    is_t, oos = swing.partir(trades, a.split)
    print("Swing RSI-2 · %d valores · %d anyos · coste 0,55%% ida y vuelta" % (
        len(syms), a.years))
    for s, e in fallos.items():
        print("  %-6s ERROR %s" % (s, e))
    if not res["n"]:
        print("\nSin operaciones: revisa el universo o los anyos.")
        return 0
    print("\nTotal: %d trades · %.1f%% acierto · %% neto medio %+.3f · total %+.1f%%" % (
        res["n"], 100 * res["win_rate"], res["avg_net"], res["total_net"]))
    print("Bruto medio %+.3f%% · duracion media %.1f sesiones · max DD %.1f puntos" % (
        res["avg_gross"], res["avg_days"], res["max_dd"]))
    for nombre, sub in (("In-sample", is_t), ("Out-of-sample", oos)):
        r = swing.resumen(sub)
        if r["n"]:
            print("%s: %d trades · %.1f%% · medio %+.3f%% · total %+.1f%%" % (
                nombre, r["n"], 100 * r["win_rate"], r["avg_net"], r["total_net"]))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"resumen": res, "is": swing.resumen(is_t),
                       "oos": swing.resumen(oos), "trades": trades},
                      f, ensure_ascii=False, indent=2)
        print("JSON: %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
