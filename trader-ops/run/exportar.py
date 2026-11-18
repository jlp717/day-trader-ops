"""Exporta el diario y las señales a CSV. Solo lectura.

    python trader-ops/run/exportar.py            # trader-ops/historico/diario.csv y senales.csv
"""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import cfg, diario, posiciones, registro  # noqa: E402

OUT = cfg.OPS / "historico"


def exportar():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = diario.read_all()
    p1 = OUT / "diario.csv"
    with open(p1, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ts_utc", "ts_madrid", "evento", "nombre", "symbol", "veredicto",
                    "code", "segundos", "hash_salida", "detalle"])
        for r in rows:
            w.writerow([r.get("ts_utc"), r.get("ts_madrid"), r.get("event"), r.get("name") or r.get("cmd"),
                        r.get("symbol"), r.get("veredicto"), r.get("code"), r.get("seconds"),
                        r.get("output_hash"), str(r.get("error") or r.get("error") or "")[:200]])
    p2 = OUT / "senales.csv"
    with open(p2, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "ts_madrid", "symbol", "estado", "entry", "stop", "target",
                    "risk_per_share", "target_r", "shares", "R", "precio_cierre", "coste_usd"])
        for s in registro.all_signals():
            plan = s.get("plan") or {}
            w.writerow([s.get("id"), s.get("ts_madrid"), s.get("symbol"), s.get("estado"),
                        plan.get("entry"), plan.get("stop"), plan.get("target"),
                        plan.get("risk_per_share"), plan.get("target_r"), s.get("shares"),
                        s.get("R"), s.get("precio_cierre"), s.get("coste_usd")])
    p3 = OUT / "posiciones.csv"
    with open(p3, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "symbol", "qty", "entrada", "entrada_plan", "stop", "target",
                    "estado", "salida", "motivo", "pnl_usd", "R", "deslizamiento_entrada"])
        for p in posiciones.todas():
            w.writerow([p.get("id"), p.get("symbol"), p.get("qty"), p.get("entrada"),
                        p.get("entrada_plan"), p.get("stop"), p.get("target"), p.get("estado"),
                        p.get("salida"), p.get("motivo"), p.get("pnl_usd"), p.get("R"),
                        p.get("deslizamiento_entrada")])
    return [str(p1), str(p2), str(p3)]


if __name__ == "__main__":
    for p in exportar():
        print("escrito", p)
