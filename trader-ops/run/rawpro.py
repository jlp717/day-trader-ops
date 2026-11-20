"""Version completa de RAW: mide stop, objetivo y filtros en EE. UU. y Xetra.

    python trader-ops/run/rawpro.py --mercado us --days 60
    python trader-ops/run/rawpro.py --mercado eu --days 60 --cost 0.30
    python trader-ops/run/rawpro.py --mercado us --variante stop2R+tendencia --json out.json

Cada variante se mide con IS/OOS. Si no bate a la base y no es positiva neta, no
se usa: el indicador puede ordenar la operativa sin dar ventaja.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import datos, raw, rawpro  # noqa: E402

UNIVERSO_US = ("AAPL,MSFT,NVDA,AMD,AMZN,GOOGL,META,TSLA,AVGO,NFLX,CRM,ORCL,ADBE,INTC,MU,"
               "QCOM,JPM,BAC,GS,XOM,CVX,JNJ,PFE,UNH,LLY,WMT,COST,HD,DIS,BA,CAT,GE,F,GM,"
               "T,VZ,KO,PEP,MCD,NKE")
UNIVERSO_EU = ("SAP.DE,SIE.DE,ALV.DE,DTE.DE,BAS.DE,BAYN.DE,BMW.DE,MBG.DE,VOW3.DE,"
               "AIR.DE,ADS.DE,IFX.DE,HEN3.DE,FME.DE,DBK.DE,CBK.DE,RWE.DE,EOAN.DE,"
               "MUV2.DE,SHL.DE")

VARIANTES = [
    ("stop1R", {"target_r": 1.0}),
    ("stop2R", {"target_r": 2.0}),
    ("stop3R", {"target_r": 3.0}),
    ("2R+tendencia", {"target_r": 2.0, "tendencia": True}),
    ("2R+rango", {"target_r": 2.0, "rango_min": 0.15, "rango_max": 1.2}),
    ("2R+volumen", {"target_r": 2.0, "vol_min": 1.2}),
    ("2R+tend+vol", {"target_r": 2.0, "tendencia": True, "vol_min": 1.2}),
    ("trailing", {"target_r": 2.0, "exit_mode": "be_trail"}),
]


def tendencia_diaria(symbol):
    """{fecha ISO: True/False} con el cierre y la SMA200 del dia ANTERIOR (sin mirar el futuro)."""
    try:
        doc = datos.chart(symbol, "1y", "1d", ttl=6 * 3600)
    except Exception:
        return {}
    bars = [b for b in (doc.get("bars") or []) if b.get("c") is not None and b.get("t")]
    if len(bars) < 210:
        return {}
    cierres = [float(b["c"]) for b in bars]
    s200 = rawpro_sma(cierres, 200)
    out = {}
    prev = None
    for b, sma in zip(bars, s200):
        if prev is not None:
            out[raw_fecha(b)] = prev
        prev = (float(b["c"]) > sma) if sma is not None else None
    return {k: v for k, v in out.items() if v is not None}


def rawpro_sma(valores, n):
    out = [None] * len(valores)
    acc = 0.0
    for i, v in enumerate(valores):
        acc += float(v)
        if i >= n:
            acc -= float(valores[i - n])
        if i >= n - 1:
            out[i] = acc / n
    return out


def raw_fecha(bar):
    import datetime as dt
    from zoneinfo import ZoneInfo
    return dt.datetime.fromtimestamp(int(bar["t"]), tz=ZoneInfo("UTC")).date().isoformat()


def correr(syms, mercado, days, cost, params, con_tendencia):
    trades = []
    fallos = {}
    for s in syms:
        try:
            bars = raw.barras(s)
            trozos = raw._por_dia(bars, raw._cfg(mercado)["tz"])
            fechas = sorted(trozos)[-int(days):]
            recorte = [b for d in fechas for b in trozos[d]]
            kw = dict(params)
            kw.setdefault("cost_pct", cost)
            if con_tendencia or params.get("tendencia"):
                kw["tendencia"] = tendencia_diaria(s)
            trades.extend(rawpro.operar(recorte, mercado, **kw))
        except Exception as exc:
            fallos[s] = str(exc)[:80]
    trades.sort(key=lambda t: (t["date"], t["entry"]))
    return trades, fallos


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="RAW completo: stop, objetivo y filtros")
    ap.add_argument("--mercado", choices=("us", "eu"), default="us")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--cost", type=float, default=None)
    ap.add_argument("--split", type=float, default=0.7)
    ap.add_argument("--max-loss", type=float, default=50.0)
    ap.add_argument("--variante", help="medir solo una variante por su nombre")
    ap.add_argument("--json", help="guardar los trades de la variante elegida")
    a = ap.parse_args(argv)
    coste = a.cost if a.cost is not None else (0.30 if a.mercado == "eu" else 0.52)
    syms = (UNIVERSO_EU if a.mercado == "eu" else UNIVERSO_US).split(",")

    elegidas = [v for v in VARIANTES if not a.variante or v[0] == a.variante]
    if not elegidas:
        print("Variante desconocida. Opciones: " + ", ".join(v[0] for v in VARIANTES))
        return 2

    print("RAW completo · %s · %d valores · %d sesiones · coste %.2f%%" % (
        a.mercado.upper(), len(syms), a.days, coste))
    print("\nvariante          n     acierto   media%    total%    R medio   IS%      OOS%")
    for nombre, params in elegidas:
        trades, fallos = correr(syms, a.mercado, a.days, coste, params,
                                bool(params.get("tendencia")))
        r = rawpro.resumen(trades)
        is_t, oos = rawpro.partir(trades, a.split)
        ri = rawpro.resumen(is_t)
        ro = rawpro.resumen(oos)
        print("%-16s %4d   %6.1f%%  %+7.3f  %+8.1f  %+7.2f   %+7.1f  %+7.1f" % (
            nombre, r["n"], 100 * r["win_rate"], r["avg_net"], r["total_net"],
            r["avg_r"], ri["total_net"], ro["total_net"]))
        if fallos:
            print("   fallos: " + ", ".join("%s (%s)" % (k, v[:30]) for k, v in list(fallos.items())[:4]))
        if a.variante and a.json:
            with open(a.json, "w", encoding="utf-8") as f:
                json.dump({"variante": nombre, "params": params, "resumen": r,
                           "is": ri, "oos": ro, "trades": trades},
                          f, ensure_ascii=False, indent=2)
            print("   JSON: %s" % a.json)
    print("\nLectura: 'media%' es por operacion, ya con coste. Si no es positiva, no se opera.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
