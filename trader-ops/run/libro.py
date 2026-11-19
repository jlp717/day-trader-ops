"""Libro de ordenes: top-of-book IEX gratis o proveedor de pago.

    python trader-ops/run/libro.py --symbol NVDA --proveedor alpaca_iex

Sin claves de Alpaca falla de forma explicita. No inventa profundidad.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import proveedores  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Libro de ordenes")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--proveedor", default="alpaca_iex",
                    choices=sorted(proveedores.PROVEEDORES))
    a = ap.parse_args(argv)
    try:
        libro = proveedores.get(a.proveedor).libro(a.symbol)
    except Exception as exc:
        print("ERROR: %s" % exc)
        return 2
    print(json.dumps(libro, ensure_ascii=False, indent=2))
    if libro.get("depth") == 1:
        print("\nTop-of-book: bid/ask y tamanos. No es profundidad completa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
