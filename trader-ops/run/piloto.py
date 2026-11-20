"""Convierte la ultima SEÑAL A de hoy en una orden bracket PAPEL.

    python trader-ops/run/piloto.py              # dry-run
    python trader-ops/run/piloto.py --confirm    # envia a Alpaca paper

No toca MyInvestor ni dinero real.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import brokers, piloto  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Piloto de papel de una SEÑAL A")
    ap.add_argument("--broker", default="alpaca_paper", choices=brokers.nombres())
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args(argv)
    senal = piloto.ultima_senal()
    if not senal:
        print("No hay SEÑAL A abierta hoy. Nada que hacer.")
        return 0
    try:
        prop = piloto.propuesta(senal)
    except Exception as exc:
        print("ERROR: %s" % exc)
        return 2
    print("SEÑAL A: %s %s acc · entrada %.2f · stop %.2f · objetivo %.2f" % (
        prop["symbol"], prop["qty"], prop["entry"], prop["stop"], prop["target"]))
    if not a.confirm:
        print("DRY RUN. Anade --confirm para enviar el bracket PAPEL a %s." % a.broker)
        return 0
    try:
        res = piloto.ejecutar(senal, broker=brokers.get(a.broker), confirm=True)
    except Exception as exc:
        print("ERROR: %s" % exc)
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
