"""Mesa de research: fundamentales, noticias, analistas, insiders y tecnico.

    python trader-ops/run/research.py NVDA
    python trader-ops/run/research.py NVDA --json research_nvda.json

Solo lectura. No envia ordenes. No predice: ordena la evidencia.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import research  # noqa: E402


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Research de un valor")
    ap.add_argument("symbol")
    ap.add_argument("--json", help="guardar el informe")
    a = ap.parse_args(argv)
    sym = a.symbol.strip().upper()
    txt = research.texto(sym).replace("<b>", "").replace("</b>", "")
    print(txt)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(research.analizar(sym), f, ensure_ascii=False, indent=2)
        print("\nJSON: %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
