"""RAW NASDAQ LITE (nico66fx) en el bot: senal del dia y backtest honesto.

    python trader-ops/run/raw.py --symbol NVDA
    python trader-ops/run/raw.py --symbol SAP.DE --mercado eu
    python trader-ops/run/raw.py --backtest --days 60
    python trader-ops/run/raw.py --backtest --mercado eu --days 60 --cost 0.30

La senal se calcula igual que el Pine: primera vela de 5 min de la sesion contra
una EMA de alfa 4/26. En EE. UU. la vela es 09:30 ET; en Xetra, 09:00 CET.
El backtest mide si las COMPRA baten a la base (todos los dias): si no la baten,
el indicador ordena pero no aporta.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import raw  # noqa: E402

UNIVERSO_US = ("AAPL,MSFT,NVDA,AMD,AMZN,GOOGL,META,TSLA,AVGO,NFLX,CRM,ORCL,ADBE,INTC,MU,"
               "QCOM,JPM,BAC,GS,XOM,CVX,JNJ,PFE,UNH,LLY,WMT,COST,HD,DIS,BA,CAT,GE,F,GM,"
               "T,VZ,KO,PEP,MCD,NKE")

UNIVERSO_EU = ("SAP.DE,SIE.DE,ALV.DE,DTE.DE,BAS.DE,BAYN.DE,BMW.DE,MBG.DE,VOW3.DE,"
               "AIR.DE,ADS.DE,IFX.DE,HEN3.DE,FME.DE,DBK.DE,CBK.DE,RWE.DE,EOAN.DE,"
               "MUV2.DE,SHL.DE")


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="RAW NASDAQ LITE en Python (US y Xetra)")
    ap.add_argument("--symbol", help="un simbolo: senal del dia")
    ap.add_argument("--backtest", nargs="?", const="AUTO",
                    help="lista de simbolos, o vacio para el universo del mercado")
    ap.add_argument("--mercado", choices=("us", "eu"), default="us")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--cost", type=float, default=None,
                    help="coste ida y vuelta en %% (defecto: 0.52 US, 0.30 EU)")
    ap.add_argument("--json", help="guardar el resultado")
    ap.add_argument("--send", action="store_true")
    a = ap.parse_args(argv)
    coste = a.cost if a.cost is not None else (0.30 if a.mercado == "eu" else 0.52)

    if a.symbol:
        sym = a.symbol.strip().upper()
        fila = raw.ultima(raw.barras(sym), a.mercado)
        txt = raw.texto_senal(fila, sym, a.mercado)
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

    bruto = a.backtest
    syms = (UNIVERSO_EU if a.mercado == "eu" else UNIVERSO_US).split(",") if bruto in (None, "AUTO") \
        else [x.strip().upper() for x in str(bruto).split(",") if x.strip()]
    filas = []
    fallos = {}
    for s in syms:
        try:
            for f in raw.senales(raw.barras(s), a.mercado)[-int(a.days):]:
                if f["pct"] is not None:
                    f["symbol"] = s
                    filas.append(f)
        except Exception as exc:
            fallos[s] = str(exc)[:80]
    if not filas:
        print("Sin datos para el backtest.")
        return 2
    largos = [f["pct"] - coste for f in filas if f["dir"] == 1]
    cortos = [f["pct"] for f in filas if f["dir"] == -1]
    base = [f["pct"] for f in filas]

    def media(v):
        return (sum(v) / len(v)) if v else None

    def acierto(v):
        return (sum(1 for x in v if x > 0) / float(len(v))) if v else None

    print("RAW · mercado %s · %d valores · %d sesiones · coste %.2f%%" % (
        a.mercado.upper(), len(syms), a.days, coste))
    for s, e in fallos.items():
        print("  %-8s ERROR %s" % (s, e))
    print("\nCOMPRA: n=%d · media %s%% · acierto %s" % (
        len(largos),
        ("%+.3f" % media(largos)) if media(largos) is not None else "n/d",
        ("%.1f%%" % (100 * acierto(largos))) if acierto(largos) is not None else "n/d"))
    print("VENTA : n=%d · media %s%% (inverso, solo informativo)" % (
        len(cortos), ("%+.3f" % media(cortos)) if media(cortos) is not None else "n/d"))
    print("BASE  : n=%d · media %+.3f%% (todos los dias, lo que hay que batir)" % (
        len(base), media(base)))
    if largos and media(largos) is not None and media(base) is not None:
        print("\nVentaja de la senal sobre la base: %+.3f puntos por sesion." % (
            media(largos) - media(base)))
        print("Lectura: si no es positiva y consistente, el indicador ordena pero no aporta.")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"mercado": a.mercado, "n": len(filas), "compra": media(largos),
                       "venta": media(cortos), "base": media(base), "coste": coste,
                       "filas": filas}, f, ensure_ascii=False, indent=2)
        print("\nJSON: %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
