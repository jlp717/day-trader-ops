"""Medir antes de relajar un filtro. Solo recalcula sobre lo ya evaluado hoy.

    python trader-ops/run/simular_filtro.py --relajar historial
    python trader-ops/run/simular_filtro.py --relajar historial,ev --min-hist 6
    python trader-ops/run/simular_filtro.py --min-ev -0.2

No re-ejecuta el pipeline ni cambia nada: lee los eventos `evaluacion` del diario de hoy,
aplica los umbrales nuevos sobre los numeros guardados y dice cuantas SEÑAL A mas saldrian,
con su EV y su muestra. Si un dato no se guardo, lo dice en vez de inventarlo.

Aviso de sesgo: solo mide los valores que llegaron a evaluarse (los que dispararon el setup),
no todo el mercado. Relajar un filtro siempre mejora el recuento y empeora la calidad media:
por eso se mide el EV, no solo el numero.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import criterios, diario, zonatiempo as zt  # noqa: E402


def cargar(day=None):
    day = day or zt.madrid().date().isoformat()
    return [e for e in diario.read_all()
            if e.get("event") == "evaluacion" and (e.get("ts_madrid") or "").startswith(day)]


def recalcular(evs, relajar, min_hist, min_ev, z=criterios.UMBRALES["wilson_z"]):
    filas = []
    for e in evs:
        n = e.get("numbers") or {}
        checks = e.get("checks") or {}
        relajados = set(x.strip().lower() for x in relajar)
        fallos = []
        # historial: n y wilson contra break-even
        hist_ok = (n.get("hist_n") or 0) >= min_hist
        if n.get("wilson_low") is not None and n.get("break_even") is not None:
            hist_ok = hist_ok and n["wilson_low"] > n["break_even"]
        if "historial" in relajados:
            hist_ok = True
        if not hist_ok:
            fallos.append("historial")
        ev = n.get("ev")
        ev_ok = ev is not None and ev > min_ev
        if "ev" in relajados:
            ev_ok = True
        if not ev_ok:
            fallos.append("ev")
        if "calidad" in relajados and not checks.get("calidad", True):
            pass
        else:
            if not checks.get("calidad", True):
                fallos.append("calidad")
        if "frescura" in relajados:
            pass
        elif not checks.get("frescura", True):
            fallos.append("frescura")
        criticos = [f for f in fallos if f in ("calidad", "frescura")]
        nuevo = "SEÑAL A" if not criticos and not fallos else ("VIGILAR" if not criticos else "DESCARTADA")
        filas.append({"symbol": e.get("symbol"), "antes": e.get("veredicto"), "despues": nuevo,
                      "ev": ev, "hist_n": n.get("hist_n"), "motivos": fallos})
    return filas


def main(argv=None):
    ap = argparse.ArgumentParser(description="Simula relajar filtros sobre lo evaluado hoy")
    ap.add_argument("--relajar", default="", help="checks a ignorar: historial,ev,calidad,frescura")
    ap.add_argument("--min-hist", type=int, default=criterios.UMBRALES["min_history_triggered"])
    ap.add_argument("--min-ev", type=float, default=0.0)
    ap.add_argument("--dia", help="YYYY-MM-DD (por defecto hoy Madrid)")
    a = ap.parse_args(argv)

    evs = cargar(a.dia)
    if not evs:
        print("No hay evaluaciones hoy. El simulador solo puede medir lo que ya se evaluo.")
        return 1
    filas = recalcular(evs, a.relajar.split(",") if a.relajar else [], a.min_hist, a.min_ev)
    antes = len([f for f in filas if f["antes"] == "SEÑAL A"])
    despues = len([f for f in filas if f["despues"] == "SEÑAL A"])
    evs_nuevas = [f for f in filas if f["despues"] == "SEÑAL A" and f["antes"] != "SEÑAL A"]
    print("Evaluados hoy: %d · SEÑAL A antes: %d · con el cambio: %d" % (len(filas), antes, despues))
    print("Relajado: %s · min_hist %d · min_ev %s" % (a.relajar or "nada", a.min_hist, a.min_ev))
    if evs_nuevas:
        print("\nNuevas que pasarian:")
        for f in evs_nuevas:
            print("  %-6s EV %s R · hist n=%s · antes %s" % (
                f["symbol"], "n/d" if f["ev"] is None else "%+.3f" % f["ev"],
                f["hist_n"], f["antes"]))
        evs_validos = [f["ev"] for f in evs_nuevas if f["ev"] is not None]
        if evs_validos:
            print("  EV medio de las nuevas: %+.3f R (n=%d)" % (sum(evs_validos) / len(evs_validos), len(evs_validos)))
            if sum(evs_validos) / len(evs_validos) <= 0:
                print("  AVISO: el EV medio de las nuevas es <= 0. Relajar el filtro añade avisos que pierden.")
    else:
        print("\nNinguna nueva pasaria. El filtro no es el cuello de botella hoy.")
    print("\nRecuerda: esto no re-ejecuta el pipeline y solo cubre los valores que llegaron a evaluarse.")
    print("Cualquier cambio de umbral debe registrarse en CRITERIOS.md con fecha y motivo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
