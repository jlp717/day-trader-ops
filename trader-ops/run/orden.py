"""Orden de papel: local o Alpaca paper. Nunca usa un broker real.

    python trader-ops/run/orden.py --broker alpaca_paper --side buy --symbol NVDA --qty 1 --limit 100
    python trader-ops/run/orden.py --broker alpaca_paper --side buy --symbol NVDA --qty 1 --confirm

Sin --confirm solo imprime lo que haria.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import brokers  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Orden de papel")
    ap.add_argument("--broker", default="paper", choices=brokers.nombres())
    ap.add_argument("--side", required=True, choices=("buy", "sell"))
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--qty", type=float, required=True)
    ap.add_argument("--limit", type=float, default=None)
    ap.add_argument("--key", default=None, help="idempotencia: misma clave, misma orden")
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args(argv)
    if not a.confirm:
        print("DRY RUN: %s %s %s qty=%g limit=%s broker=%s" % (
            a.side, a.symbol.upper(), "PAPEL", a.qty, a.limit, a.broker))
        print("Anade --confirm para enviarlo al broker de papel.")
        return 0
    try:
        b = brokers.get(a.broker)
        fn = b.comprar if a.side == "buy" else b.vender
        res = fn(a.symbol, a.qty, limit=a.limit, key=a.key)
    except Exception as exc:
        print("ERROR: %s" % exc)
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
