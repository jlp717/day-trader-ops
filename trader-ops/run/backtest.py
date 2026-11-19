"""Backtest del ORB sobre Yahoo (5 min, ultimos ~60 dias).

    python trader-ops/run/backtest.py --symbols NVDA,AMD --days 30
    python trader-ops/run/backtest.py --days 30 --json estado/backtest.json
    python trader-ops/run/backtest.py --list-strategies

No envia nada, no toca el estado del bot y no usa el pipeline vivo.
"""
import argparse
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

    trades, meta = backtest.correr(
        symbols, days=days, max_loss=max_loss, min_dv=float(a.min_dv),
        min_price=float(a.min_price), strategy=a.strategy, con_costes=not a.no_costs,
        max_cost_r=a.max_cost_r)
    res = backtest.resumen(trades)
    backtest.imprimir(trades, meta, res)

    if a.json:
        backtest.guardar_json(a.json, trades, meta, res)
        print("\nJSON: %s" % a.json)
    if a.csv:
        backtest.guardar_csv(a.csv, trades)
        print("CSV:  %s" % a.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
