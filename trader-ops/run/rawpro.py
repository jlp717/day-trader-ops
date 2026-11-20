"""Version completa de RAW: mide stop, objetivo y filtros, con años de datos.

    python trader-ops/run/rawpro.py --mercado us --days 60
    python trader-ops/run/rawpro.py --mercado us --fuente alpaca --desde 2016-01-01 --days 0
    python trader-ops/run/rawpro.py --mercado eu --days 60 --cost 0.30

Yahoo solo da 60 sesiones de 5 minutos. Para EE. UU., Alpaca (SIP) da años.
Cada variante se mide con IS/OOS y, si se pide, con intervalo de confianza
bootstrap: una media negativa con intervalo que cruza cero es ruido, no ventaja.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import raw, rawpro  # noqa: E402

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
    ("2R+gap", {"target_r": 2.0, "gap_min": 0.0}),
    ("2R+cierre alto", {"target_r": 2.0, "pos_min": 0.6}),
    ("2R+gap+cierre", {"target_r": 2.0, "gap_min": 0.0, "pos_min": 0.6}),
    ("2R+mercado", {"target_r": 2.0, "mercado": True}),
    ("2R+mercado+tend", {"target_r": 2.0, "tendencia": True, "mercado": True}),
    ("trailing", {"target_r": 2.0, "exit_mode": "be_trail"}),
]


def cargar(syms, fuente, desde, hasta):
    barras, fallos = {}, {}
    for s in syms:
        try:
            if fuente == "alpaca":
                barras[s] = raw.barras_alpaca(s, desde, hasta)
            else:
                barras[s] = raw.barras(s)
            if len(barras[s]) < 100:
                fallos[s] = "pocas barras (%d)" % len(barras[s])
                barras.pop(s, None)
        except Exception as exc:
            fallos[s] = str(exc)[:100]
    return barras, fallos


def correr(barras, mercado, days, cost, params, con_tendencia, tendencias=None, mercado_ok=None):
    trades = []
    for s, bars in barras.items():
        trozos = raw._por_dia(bars, raw._cfg(mercado)["tz"])
        fechas = sorted(trozos)
        if days:
            fechas = fechas[-int(days):]
        recorte = [b for d in fechas for b in trozos[d]]
        kw = dict(params)
        usa_mercado = bool(kw.pop("mercado", False))
        kw.setdefault("cost_pct", cost)
        if con_tendencia or params.get("tendencia"):
            kw["tendencia"] = (tendencias or {}).get(s, {})
        if usa_mercado:
            kw["mercado_ok"] = mercado_ok or {}
        trades.extend(rawpro.operar(recorte, mercado, **kw))
    trades.sort(key=lambda t: (t["date"], t["entry"]))
    return trades


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="RAW completo: años de datos, stop y filtros")
    ap.add_argument("--mercado", choices=("us", "eu"), default="us")
    ap.add_argument("--symbols", help="lista separada por comas")
    ap.add_argument("--fuente", choices=("yahoo", "alpaca"), default="yahoo")
    ap.add_argument("--desde", default="2016-01-01")
    ap.add_argument("--hasta", default=None)
    ap.add_argument("--days", type=int, default=60, help="0 = todas las sesiones disponibles")
    ap.add_argument("--cost", type=float, default=None)
    ap.add_argument("--split", type=float, default=0.7)
    ap.add_argument("--max-loss", type=float, default=50.0)
    ap.add_argument("--cuenta", type=float, default=10000.0)
    ap.add_argument("--variante", help="medir solo una variante por su nombre")
    ap.add_argument("--bootstrap", action="store_true", help="intervalo de confianza de la media")
    ap.add_argument("--json", help="guardar los trades de la variante elegida")
    a = ap.parse_args(argv)
    coste = a.cost if a.cost is not None else (0.30 if a.mercado == "eu" else 0.52)
    syms = ([x.strip().upper() for x in a.symbols.split(",") if x.strip()]
            if a.symbols else (UNIVERSO_EU if a.mercado == "eu" else UNIVERSO_US).split(","))

    elegidas = [v for v in VARIANTES if not a.variante or v[0] == a.variante]
    if not elegidas:
        print("Variante desconocida. Opciones: " + ", ".join(v[0] for v in VARIANTES))
        return 2

    barras, fallos = cargar(syms, a.fuente, a.desde, a.hasta)
    print("RAW completo · %s · %s · %d valores · %s · coste %.2f%%" % (
        a.mercado.upper(), a.fuente, len(barras),
        ("todas las sesiones" if not a.days else "%d sesiones" % a.days), coste))
    for s, e in list(fallos.items())[:6]:
        print("  %-8s %s" % (s, e))
    tendencias = {}
    if any(p.get("tendencia") for _, p in elegidas):
        tendencias = {s: rawpro.tendencia_diaria(s, a.desde, a.hasta, a.fuente)
                      for s in barras}
    mercado_ok = {}
    if any(p.get("mercado") for _, p in elegidas):
        indice = "SPY" if a.mercado == "us" else "^GDAXI"
        fuente_ind = a.fuente if a.mercado == "us" else "yahoo"
        mercado_ok = rawpro.tendencia_diaria(indice, a.desde, a.hasta, fuente_ind)
    print("\nvariante          n     acierto   media%    total%    IS%      OOS%")
    for nombre, params in elegidas:
        trades = correr(barras, a.mercado, a.days, coste, params,
                        bool(params.get("tendencia")), tendencias, mercado_ok)
        r = rawpro.resumen(trades)
        is_t, oos = rawpro.partir(trades, a.split)
        ri = rawpro.resumen(is_t)
        ro = rawpro.resumen(oos)
        print("%-16s %5d   %6.1f%%  %+7.3f  %+8.1f  %+7.1f  %+7.1f" % (
            nombre, r["n"], 100 * r["win_rate"], r["avg_net"], r["total_net"],
            ri["total_net"], ro["total_net"]))
        if a.bootstrap and trades:
            b = rawpro.bootstrap(trades)
            if b:
                print("   bootstrap 95%%: media %+.3f%% · intervalo [%+.3f, %+.3f]" % (
                    b["media"], b["lo"], b["hi"]))
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
