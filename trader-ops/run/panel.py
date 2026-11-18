"""Panel de terminal. Se refresca solo, solo lectura, sin red.

    python trader-ops/run/panel.py              # bucle, refresco cada 5 s
    python trader-ops/run/panel.py --once       # una pasada (para capturas)
    python trader-ops/run/panel.py --cada 3
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import estado_vivo  # noqa: E402

VERDE, ROJO, AMBAR, AZUL, GRIS, NEGRITA, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[90m", "\033[1m", "\033[0m")


def _vt():
    """Activa secuencias ANSI y UTF-8 en la consola de Windows."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)
    except Exception:
        pass


def _limpiar():
    sys.stdout.write("\033[2J\033[H")


def _pct(x):
    return "n/d" if x is None else "%+.2f%%" % x


def _sec(x):
    if x is None:
        return "n/d"
    if x < 120:
        return "%ds" % x
    if x < 7200:
        return "%dm" % (x // 60)
    return "%dh %02dm" % (x // 3600, (x % 3600) // 60)


def render(f):
    L = []
    ancho = 78
    L.append(NEGRITA + "DAY TRADER · PAPEL" + RESET + "  " + f["now_madrid"][11:16] + " Madrid / " +
             f["now_ny"] + " NY  (desfase " + str(f["offset_h"]) + "h)")
    ses = f["session"]
    estado_mercado = VERDE + "ABIERTO" + RESET if ses["open"] else ROJO + "cerrado" + RESET
    L.append("Mercado: %s (%s-%s, %s)" % (estado_mercado, ses["start"] or "-", ses["end"] or "-", ses["why"]))
    L.append("Fase: " + NEGRITA + f["phase"]["title"] + RESET + "   Proximo: %s a las %s (en %s)" % (
        f["next"]["title"] or "n/d", f["next"]["at"] or "-", f["next"]["countdown"]))
    L.append(GRIS + "-" * ancho + RESET)

    h = f["health"]
    salud = (VERDE + "VIVO" + RESET) if h["alive"] else (ROJO + "PARADO" + RESET)
    L.append("Salud: %s · latido %s (%s) · errores 1h %d · 429: %d · comandos/min %d · datos %s%s" % (
        salud, _sec(h["heartbeat_age_s"]), h["heartbeat_phase"] or "n/d", h["errors_1h"],
        h["http429_1h"], h["cmds_1m"], _sec(f["data"]["age_s"]),
        (AMBAR + " · PAUSADO" + RESET) if f["paused"] else ""))

    L.append("")
    L.append(NEGRITA + "VIGILADOS" + RESET)
    if f["watch"]:
        L.append("  %-7s %10s %10s %9s" % ("valor", "precio", "nivel", "dist."))
        for v in f["watch"]:
            L.append("  %-7s %10s %10s %9s" % (
                v["symbol"], ("%.2f" % v["price"]) if v["price"] else "n/d",
                ("%.2f" % v["level"]) if v["level"] else "-", _pct(v["dist_pct"])))
    else:
        L.append("  (nada vigilado)")

    s = f["signals"]
    L.append("")
    L.append(NEGRITA + "SEÑALES HOY" + RESET + "  A %d · vigilar %d · descartadas %d · sin señal %d" % (
        s["counts"].get("SEÑAL A", 0), s["counts"].get("VIGILAR", 0),
        s["counts"].get("DESCARTADA", 0), s["counts"].get("SIN SEÑAL", 0) + s["counts"].get("SIN DATOS", 0)))
    for a in s["A"][-3:]:
        L.append("  " + VERDE + "A " + str(a["symbol"]) + RESET + " " + "; ".join((a["motivos"] or [])[:1]))
    for v in s["watchlist"][:4]:
        L.append("  " + AMBAR + "V " + str(v["symbol"]) + RESET + " " + "; ".join(v["motivos"]))
    for d in s["descartadas"][:4]:
        L.append("  " + GRIS + "D " + str(d["symbol"]) + " " + ("; ".join(d["motivos"]))[:70] + RESET)

    L.append("")
    L.append(NEGRITA + "POSICIONES" + RESET + ("   cierre en %d min" % f["minutes_to_close"]
                                               if f["minutes_to_close"] is not None and f["minutes_to_close"] >= 0 else ""))
    if f["positions"]:
        L.append("  %-7s %5s %9s %9s %9s %9s %9s %9s" % ("valor", "acc", "entrada", "stop", "objetivo",
                                                          "precio", "a stop", "a objetivo"))
        for p in f["positions"]:
            L.append("  %-7s %5s %9.2f %9s %9s %9s %9s %9s" % (
                p["symbol"], p["qty"], float(p["entry"]),
                ("%.2f" % p["stop"]) if p["stop"] else "-",
                ("%.2f" % p["target"]) if p["target"] else "-",
                ("%.2f" % p["price"]) if p["price"] else "n/d",
                _pct(p["dist_stop_pct"]), _pct(p["dist_target_pct"])))
    else:
        L.append("  (ninguna abierta)")

    L.append("")
    armadas = f["alerts"]
    L.append(NEGRITA + "ALERTAS ARMADAS" + RESET + "  %d" % len(armadas))
    for a in armadas[:5]:
        L.append("  %s %s %s %s" % (a["id"], a["symbol"] or "", a["type"] or "", a["price"] or ""))

    p = f["pnl"]
    r = f["registro"]
    lim = f["limits"]
    L.append("")
    L.append(NEGRITA + "RESULTADO" + RESET + "  P&L a mano %+.2f USD · señales %d cerradas (R medio %+.2f)" % (
        p["pnl_usd"], r["cerradas"], r["r_medio"]))
    L.append("  riesgo hoy %.2f / %s USD (papel %.2f + manual %.2f) · operaciones %d / %s · freno: %s" % (
        lim["risk_today_usd"], lim["risk_cap_usd"], lim.get("risk_signals_usd", 0),
        lim.get("risk_manual_usd", 0), lim["trades_today"], lim["trades_cap"],
        (ROJO + "ACTIVO" + RESET) if f["freno"]["activo"] else "no"))
    if f["freno"]["activo"]:
        L.append("  " + ROJO + f["freno"]["motivo"] + RESET)

    L.append("")
    L.append(AZUL + NEGRITA + "QUE HACER AHORA" + RESET)
    L.append("  Sistema: " + f["phase"]["system"])
    L.append("  Tu:      " + NEGRITA + f["phase"]["you"] + RESET)
    L.append("  Ignora:   " + f["phase"]["ignore"])
    L.append(GRIS + "Ctrl+C para salir · refresco automatico · solo lectura" + RESET)
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Panel de terminal del banco de pruebas")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--cada", type=float, default=5.0)
    a = ap.parse_args(argv)
    _vt()
    if a.once:
        print(render(estado_vivo.foto()))
        return 0
    try:
        while True:
            _limpiar()
            print(render(estado_vivo.foto()))
            time.sleep(max(1.0, a.cada))
    except KeyboardInterrupt:
        print("\nPanel cerrado.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
