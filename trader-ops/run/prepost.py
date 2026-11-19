"""Analisis pre/post market con Yahoo. Solo lectura, sin ordenes.

    python trader-ops/run/prepost.py --symbols NVDA,AMD --modo pre
    python trader-ops/run/prepost.py --symbols NVDA,AMD --modo post --json salida.json

MyInvestor no permite ejecutar fuera del horario regular: esto prepara el plan.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import prepost  # noqa: E402


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Analisis pre/post market")
    ap.add_argument("--symbols", required=True, help="lista separada por comas")
    ap.add_argument("--modo", choices=("pre", "post"), default="pre")
    ap.add_argument("--json", help="guardar el resultado")
    a = ap.parse_args(argv)
    syms = [x.strip().upper() for x in a.symbols.split(",") if x.strip()]
    filas = []
    for sym in syms:
        try:
            filas.append(prepost.resumen(sym, a.modo))
        except Exception as exc:
            print("%-6s ERROR %s" % (sym, str(exc)[:120]))
    if filas:
        prepost.imprimir(filas)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(filas, f, ensure_ascii=False, indent=2)
        print("\nJSON: %s" % a.json)
    print("\nSolo analisis: MyInvestor no ejecuta fuera del horario regular.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
