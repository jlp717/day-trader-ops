"""Tesis de aguante: estructura, niveles y zona de venta de un valor.

    python trader-ops/run/tesis.py NVDA
    python trader-ops/run/tesis.py NVDA --aguantar
    python trader-ops/run/tesis.py NVDA --liberar
    python trader-ops/run/tesis.py NVDA --json

No predice y no envia ordenes: comprueba si la estructura que sostenia la compra
sigue viva y evita que un retroceso normal te saque por panico.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import tesis  # noqa: E402


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Tesis de aguante")
    ap.add_argument("symbol")
    ap.add_argument("--aguantar", action="store_true", help="marcar modo aguante")
    ap.add_argument("--liberar", action="store_true", help="quitar modo aguante")
    ap.add_argument("--json", help="guardar el resultado")
    a = ap.parse_args(argv)
    sym = a.symbol.strip().upper()

    if a.aguantar:
        tesis.marcar(sym, True)
    elif a.liberar:
        tesis.marcar(sym, False)

    r = tesis.evaluar(sym)
    print(tesis.texto(sym).replace("<b>", "").replace("</b>", ""))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print("\nJSON: %s" % a.json)
    return 0 if not r.get("error") else 2


if __name__ == "__main__":
    sys.exit(main())
