"""Vigilante rapido de niveles: comprueba stops y objetivos cada 30 s.

    python trader-ops/run/vigia.py --once
    python trader-ops/run/vigia.py --cada 30 --send

Motivo: el orquestador revisa las alertas cada 5 minutos y un movimiento de 2-3 minutos
se le escapa. Esto consulta solo los simbolos con nivel armado (posiciones y /alerta),
no el universo entero, y termina solo al cierre del mercado.

No envia ordenes. No crea señales. Solo avisa de que un nivel se ha tocado.
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import alertas, avisos, calendario, datos, posiciones, telegram, zonatiempo as zt  # noqa: E402


def simbolos():
    """Solo lo que tiene un nivel armado: reglas US y posiciones abiertas."""
    out = []
    for r in alertas.reglas_skill():
        s = str(r.get("symbol") or "").upper()
        if s and s not in out:
            out.append(s)
    for p in posiciones.abiertas():
        s = str(p.get("symbol") or "").upper()
        if s and s not in out:
            out.append(s)
    return out


def precios(syms, pausa=0.4):
    out = {}
    for s in syms:
        try:
            out[s] = float(datos.quote(s)["price"])
        except Exception:
            continue
        time.sleep(pausa)
    return out


def revisar(syms=None):
    syms = syms if syms is not None else simbolos()
    if not syms:
        return []
    px = precios(syms)
    return alertas.comprobar(px)


def texto(rings):
    lineas = ["<b>Nivel tocado</b>"]
    for r, px in rings:
        lineas.append("  %s  %s" % (r.get("symbol"), r.get("message") or ("%.2f" % px)))
    lineas.append("Revisa /guia y decide. El sistema no envia ordenes.")
    return "\n".join(lineas)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Vigilante rapido de niveles")
    ap.add_argument("--cada", type=int, default=30, help="segundos entre pasadas (min 15)")
    ap.add_argument("--once", action="store_true", help="una sola pasada")
    ap.add_argument("--send", action="store_true", help="enviar aviso a Telegram")
    ap.add_argument("--max-minutos", type=int, default=0, help="corta tras N minutos (0 = hasta el cierre)")
    a = ap.parse_args(argv)
    cada = max(15, int(a.cada))

    start, end, why = calendario.session_madrid(zt.madrid().date())
    if not start and not a.once:
        print("Sin mercado hoy: %s" % why)
        return 0

    limite = None
    if a.max_minutos:
        limite = time.time() + a.max_minutos * 60

    tg = telegram.Telegram() if a.send else None
    while True:
        rings = revisar()
        if rings:
            msg = texto(rings)
            print(msg.replace("<b>", "").replace("</b>", ""))
            if tg:
                clave = "vigia:%s" % ",".join(str(r.get("id")) for r, _px in rings)
                avisos.send_once(tg, clave[:180], msg)
        if a.once:
            return 0
        if limite and time.time() >= limite:
            return 0
        if end and zt.madrid() >= end:
            print("Cierre del mercado: el vigilante termina.")
            return 0
        time.sleep(cada)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
