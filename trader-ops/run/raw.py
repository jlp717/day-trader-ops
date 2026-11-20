"""RAW NASDAQ LITE (nico66fx) en el bot: senal del dia y backtest honesto.

    python trader-ops/run/raw.py --symbol NVDA
    python trader-ops/run/raw.py --backtest NVDA,AMD,MSFT --days 60
    python trader-ops/run/raw.py --backtest --days 60 --cost 0.52

La senal se calcula igual que el Pine: primera vela de 5 min de NY contra una
EMA de alfa 4/26. El backtest mide si las COMPRA baten a la base (todos los dias):
si no la baten, el indicador no aporta ventaja en acciones, solo orden.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import raw  # noqa: E402

UNIVERSO = ("AAPL,MSFT,NVDA,AMD,AMZN,GOOGL,META,TSLA,AVGO,NFLX,CRM,ORCL,ADBE,INTC,MU,"
            "QCOM,JPM,BAC,GS,XOM,CVX,JNJ,PFE,UNH,LLY,WMT,COST,HD,DIS,BA,CAT,GE,F,GM,"
            "T,VZ,KO,PEP,MCD,NKE")


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="RAW NASDAQ LITE en Python")
    ap.add_argument("--symbol", help="un simbolo: senal del dia")
    ap.add_argument("--backtest", nargs="?", const=UNIVERSO, help="lista de simbolos")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--cost", type=float, default=0.0, help="coste ida y vuelta en %%")
    ap.add_argument("--split", type=float, default=0.7)
    ap.add_argument("--json", help="guardar el resultado")
    ap.add_argument("--send", action="store_true")
    a = ap.parse_args(argv)

    if a.symbol:
        sym = a.symbol.strip().upper()
        fila = raw.ultima(raw.barras(sym))
        txt = raw.texto_senal(fila, sym)
        print(txt.replace("<b>", "").replace("</b>", ""))
        if a.json and fila:
            with open(a.json, "w", encoding="utf-8") as f:
                json.dump(fila, f, ensure_ascii=False, indent=2)
        if a.send:
            from lib import telegram as tg
            try:
                tg.Telegram().send(txt)
            except Exception as exc:
                print("ERROR Telegram: %s" % exc)
        return 0

    syms = [x.strip().upper() for x in (a.backtest or UNIVERSO).split(",") if x.strip()]
    filas = []
    fallos = {}
    for s in syms:
        try:
            for f in raw.senales(raw.barras(s))[-int(a.days):]:
                if f["pct"] is not None:
                    f["symbol"] = s
                    filas.append(f)
        except Exception as exc:
            fallos[s] = str(exc)[:80]
    if not filas:
        print("Sin datos para el backtest.")
        return 2
    r = None
    # Agregado multi-simbolo
    largos = [f["pct"] - float(a.cost) for f in filas if f["dir"] == 1]
    cortos = [f["pct"] for f in filas if f["dir"] == -1]
    base = [f["pct"] for f in filas]

    def media(v):
        return (sum(v) / len(v)) if v else None

    def acierto(v):
        return (sum(1 for x in v if x > 0) / float(len(v))) if v else None

    print("RAW NASDAQ LITE · %d valores · %d sesiones · coste %.2f%%" % (
        len(syms), a.days, a.cost))
    for s, e in fallos.items():
        print("  %-6s ERROR %s" % (s, e))
    print("\nCOMPRA: n=%d · media %s%% · acierto %s" % (
        len(largos),
        ("%+.3f" % media(largos)) if media(largos) is not None else "n/d",
        ("%.1f%%" % (100 * acierto(largos))) if acierto(largos) is not None else "n/d"))
    print("VENTA : n=%d · media %s%% (inverso, solo informativo)" % (
        len(cortos), ("%+.3f" % media(cortos)) if media(cortos) is not None else "n/d"))
    print("BASE  : n=%d · media %+.3f%% (todos los dias, lo que hay que batir)" % (
        len(base), media(base)))
    if largos and media(largos) is not None and media(base) is not None:
        ventaja = media(largos) - media(base)
        print("\nVentaja de la senal sobre la base: %+.3f puntos por sesion." % ventaja)
        print("Lectura: si no es positiva y consistente, el indicador ordena pero no aporta.")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"n": len(filas), "compra": media(largos), "venta": media(cortos),
                       "base": media(base), "coste": a.cost,
                       "filas": filas}, f, ensure_ascii=False, indent=2)
        print("\nJSON: %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
