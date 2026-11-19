"""Backtest del ORB sobre Yahoo (5 min, ultimos ~60 dias).

    python trader-ops/run/backtest.py --symbols NVDA,AMD --days 30
    python trader-ops/run/backtest.py --days 30 --json estado/backtest.json
    python trader-ops/run/backtest.py --list-strategies

No envia nada, no toca el estado del bot y no usa el pipeline vivo.
"""
import argparse
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import backtest, cfg, estrategias  # noqa: E402


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Backtest de la mecanica ORB")
    ap.add_argument("--symbols", help="lista separada por comas; por defecto la watchlist")
    ap.add_argument("--days", type=int, default=30, help="sesiones hacia atras (max 60)")
    ap.add_argument("--max-loss", type=float, default=None,
                    help="riesgo maximo por operacion en USD (por defecto config)")
    ap.add_argument("--min-dv", type=float, default=20_000_000.0,
                    help="liquidez minima media 20d en USD; 0 desactiva")
    ap.add_argument("--min-price", type=float, default=5.0)
    ap.add_argument("--max-cost-r", type=float, default=None,
                    help="descartar trades cuyo coste supere este multiplo de R")
    ap.add_argument("--or-minutes", type=int, default=15, help="minutos del rango (5-60)")
    ap.add_argument("--target-r", type=float, default=2.0, help="objetivo en multiplos de R")
    ap.add_argument("--stop-rule", choices=("mid", "low"), default="mid")
    ap.add_argument("--entry-cutoff", default="15:30", help="ultima entrada ET HH:MM")
    ap.add_argument("--flat", default="15:50", help="barra de cierre ET HH:MM")
    ap.add_argument("--slippage-bps", type=float, default=0.0, help="deslizamiento por lado en bps")
    ap.add_argument("--split", type=float, default=0.0,
                    help="0 = sin split; 0.7 = 70%% in-sample / 30%% out-of-sample")
    ap.add_argument("--features", help="CSV de features/labels para un futuro modelo")
    ap.add_argument("--strategy", default="orb", choices=estrategias.nombres())
    ap.add_argument("--json", help="guardar trades + resumen en JSON")
    ap.add_argument("--csv", help="guardar trades en CSV")
    ap.add_argument("--no-costs", action="store_true", help="no descontar comisiones")
    ap.add_argument("--list-strategies", action="store_true")
    a = ap.parse_args(argv)

    if a.list_strategies:
        print("Estrategias: " + ", ".join(estrategias.nombres()))
        return 0

    conf = cfg.config()
    if a.symbols:
        symbols = [x.strip().upper() for x in a.symbols.split(",") if x.strip()]
    else:
        symbols = [str(x).upper() for x in (conf.get("watch") or ["NVDA"])]
    if not symbols:
        symbols = ["NVDA"]
    days = max(1, min(60, int(a.days)))
    if a.days > 60:
        print("AVISO: Yahoo solo guarda ~60 dias de 5 min; se usan 60.")
    max_loss = float(a.max_loss if a.max_loss is not None
                     else conf.get("max_loss_per_trade_usd") or 50.0)
    try:
        corte = dt.time.fromisoformat(a.entry_cutoff)
        flat = dt.time.fromisoformat(a.flat)
    except ValueError:
        print("ERROR: --entry-cutoff y --flat quieren HH:MM")
        return 2
    if not (5 <= a.or_minutes <= 60 and a.or_minutes % 5 == 0):
        print("ERROR: --or-minutes debe ser multiplo de 5 entre 5 y 60")
        return 2
    if a.target_r < 0.5:
        print("ERROR: --target-r debe ser >= 0.5")
        return 2

    trades, meta = backtest.correr(
        symbols, days=days, max_loss=max_loss, min_dv=float(a.min_dv),
        min_price=float(a.min_price), strategy=a.strategy, con_costes=not a.no_costs,
        max_cost_r=a.max_cost_r, or_minutes=a.or_minutes, target_r=a.target_r,
        stop_rule=a.stop_rule, entry_cutoff=corte, flat=flat,
        slippage_bps=a.slippage_bps)
    res = backtest.resumen(trades)
    backtest.imprimir(trades, meta, res)
    extra = {}
    if a.split and a.split > 0:
        is_t, oos_t = backtest.partir(trades, a.split)
        extra = {"in_sample": backtest.resumen(is_t), "out_sample": backtest.resumen(oos_t)}
        for nombre, sub in (("In-sample", is_t), ("Out-of-sample", oos_t)):
            r = backtest.resumen(sub)
            print("\n%s: %d trades · %.1f%% acierto · R neto %+.2f · PnL %+.2f USD" % (
                nombre, r["n"], 100 * r["win_rate"], r["total_net_r"], r["total_pnl"]))

    if a.json:
        backtest.guardar_json(a.json, trades, meta, res, extra=extra)
        print("\nJSON: %s" % a.json)
    if a.csv:
        backtest.guardar_csv(a.csv, trades)
        print("CSV:  %s" % a.csv)
    if a.features:
        backtest.guardar_features(a.features, trades)
        print("FEATURES: %s" % a.features)
    return 0


if __name__ == "__main__":
    sys.exit(main())
