"""Baseline ML walk-forward sobre el CSV de features del backtest.

    python trader-ops/run/ml.py --features state/features.csv --split 0.7

No entrena en produccion ni toca el bot. Es un banco de pruebas.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import ml  # noqa: E402


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Baseline ML walk-forward")
    ap.add_argument("--features", required=True, help="CSV de --features del backtest")
    ap.add_argument("--split", type=float, default=0.7)
    ap.add_argument("--json", help="guardar metricas y modelo")
    ap.add_argument("--epochs", type=int, default=2500)
    a = ap.parse_args(argv)
    try:
        trades = ml.cargar_csv(a.features)
        res = ml.walk_forward(trades, frac=a.split, epochs=a.epochs)
    except Exception as exc:
        print("ERROR: %s" % exc)
        return 2
    print("Walk-forward: %d train (%d dias) · %d test (%d dias)" % (
        res["n_train"], res["train_days"], res["n_test"], res["test_days"]))
    print("Accuracy: %s · base rate: %s · AUC: %s" % (
        ("%.3f" % res["accuracy"]) if res["accuracy"] is not None else "n/d",
        ("%.3f" % res["base_rate"]) if res["base_rate"] is not None else "n/d",
        ("%.3f" % res["auc"]) if res["auc"] is not None else "n/d"))
    if res["accuracy"] is not None and res["base_rate"] is not None:
        auc = res.get("auc")
        if auc is not None and auc < 0.55:
            print("Lectura: AUC %.3f < 0.55. NO hay senal; la accuracy engana por desbalance." % auc)
        elif res["accuracy"] <= res["base_rate"] + 0.02:
            print("Lectura: el modelo NO supera la base. No hay senal util.")
        else:
            print("Lectura: supera la base, pero con esta muestra es una pista, no una ventaja.")
    if a.json:
        ml.guardar_modelo(a.json, res)
        print("JSON: %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
