"""Saludo de inicio de sesion: 5 lineas con el estado real. Sin relleno.

    python trader-ops/run/saludo.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import estado_vivo  # noqa: E402


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for linea in estado_vivo.resumen_5_lineas():
        print(linea)
    return 0


if __name__ == "__main__":
    sys.exit(main())
