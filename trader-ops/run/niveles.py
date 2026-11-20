"""Niveles manuales de stop y objetivo, sin depender del skill.

    python trader-ops/run/niveles.py --ver
    python trader-ops/run/niveles.py --poner TLK --stop 11.20 --target 12.38
    python trader-ops/run/niveles.py --poner CRCL --stop 54.20
    python trader-ops/run/niveles.py --quitar TLK

El vigilante rapido (`run/vigia.py`) los comprueba cada 30 s y avisa por Telegram.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import niveles  # noqa: E402


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Niveles manuales de stop y objetivo")
    ap.add_argument("--ver", action="store_true")
    ap.add_argument("--poner", help="simbolo")
    ap.add_argument("--stop", type=float)
    ap.add_argument("--target", type=float)
    ap.add_argument("--nota")
    ap.add_argument("--quitar", help="simbolo")
    ap.add_argument("--json", help="guardar el listado")
    a = ap.parse_args(argv)

    if a.quitar:
        print("Quitado %s" % a.quitar if niveles.quitar(a.quitar) else "No estaba %s" % a.quitar)
        return 0
    if a.poner:
        try:
            fila = niveles.poner(a.poner, stop=a.stop, target=a.target, nota=a.nota)
        except ValueError as exc:
            print("ERROR: %s" % exc)
            return 2
        print(json.dumps(fila, ensure_ascii=False, indent=2))
        return 0

    texto = niveles.texto().replace("<b>", "").replace("</b>", "")
    print(texto)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(niveles.todos(), f, ensure_ascii=False, indent=2)
        print("\nJSON: %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
