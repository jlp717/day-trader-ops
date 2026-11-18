"""Comprueba que el repo del skill vendorizado tiene todos los archivos esperados.

    python trader-ops/run/verificar_skill.py
    python trader-ops/run/verificar_skill.py --tests   # ademas corre los 315 tests

No modifica nada. Sale con codigo 0 si esta completo.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "vendor" / "day-trader-skill"

REQUERIDOS = [
    "trader-scanner/SKILL.md", "trader-scanner/scan.py",
    "trader-news/SKILL.md", "trader-news/news.py",
    "trader-entry/SKILL.md", "trader-entry/entry.py",
    "trader-exit/SKILL.md", "trader-exit/exit.py",
    "trader-timemachine/SKILL.md", "trader-timemachine/timemachine.py",
    "trader-risk/SKILL.md", "trader-risk/check.py",
    "trader-budget/SKILL.md", "trader-budget/size.py",
    "trader-budget/config.example.json", "trader-budget/targets.example.json",
    "trader-broker/SKILL.md", "trader-broker/ticket.py",
    "trader-broker/claude_desktop_config.example.json",
    "trader-alerts/SKILL.md", "trader-alerts/alerts.py", "trader-alerts/alerts.example.json",
    "trader-analyst/SKILL.md", "trader-analyst/facts.py", "trader-analyst/metrics.example.json",
    "trader-pelosi/SKILL.md", "trader-pelosi/ptr.py",
    "tests/_load.py",
    "tests/fixtures/trader-entry/TSLA-2026-10-19-5m.json",
    "tests/fixtures/trader-scanner/daily-spark-2026-10-19.json",
    "tests/fixtures/trader-timemachine/TSLA-60d5m.json.gz",
]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Verifica el repo vendorizado del skill")
    ap.add_argument("--tests", action="store_true", help="ejecuta los tests del skill")
    a = ap.parse_args(argv)
    if not SKILL.exists():
        print("FALTA la carpeta %s" % SKILL)
        return 2
    faltan = []
    for rel in REQUERIDOS:
        if not (SKILL / rel).exists():
            faltan.append(rel)
            print("FALTA  %s" % rel)
        else:
            print("OK     %s" % rel)
    for d in ("tests", "tests/fixtures"):
        if not (SKILL / d).is_dir():
            faltan.append(d + "/")
            print("FALTA  %s/" % d)
    # Snapshot plano: el hash vive en vendor/VENDOR_COMMIT (ver vendor/README.md).
    # No usar `git rev-parse` a secas: sin .git propio resolveria el repo padre.
    marca = SKILL.parent / "VENDOR_COMMIT"
    commit = "n/d"
    if marca.exists():
        valor = marca.read_text(encoding="utf-8").strip()
        if valor:
            commit = valor + "  (snapshot, sin .git)"
    else:
        try:
            top = subprocess.run(["git", "-C", str(SKILL), "rev-parse", "--show-toplevel"],
                                 capture_output=True, text=True, timeout=30)
            if top.stdout.strip() and Path(top.stdout.strip()).resolve() == SKILL.resolve():
                out = subprocess.run(["git", "-C", str(SKILL), "rev-parse", "HEAD"],
                                     capture_output=True, text=True, timeout=30)
                commit = (out.stdout or "").strip() or "n/d"
        except Exception:
            commit = "n/d"
    print("\nCommit: %s" % commit)
    print("Archivos requeridos: %d · faltan: %d" % (len(REQUERIDOS), len(faltan)))
    if a.tests and not faltan:
        print("\nEjecutando tests del skill...")
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                           cwd=str(SKILL), text=True, capture_output=True, timeout=900)
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-6:]
        print("\n".join(tail))
        if r.returncode != 0:
            return 3
    return 0 if not faltan else 1


if __name__ == "__main__":
    sys.exit(main())
