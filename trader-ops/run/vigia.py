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

from lib import alertas, avisos, calendario, datos, niveles, posiciones, telegram, zonatiempo as zt  # noqa: E402


def simbolos():
    """Solo lo que tiene un nivel armado: reglas US, niveles manuales y posiciones."""
    out = []
    for r in alertas.reglas_skill():
        s = str(r.get("symbol") or "").upper()
        if s and s not in out:
            out.append(s)
    for f in niveles.todos():
        s = str(f.get("symbol") or "").upper()
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
    """Lista de avisos en texto: reglas del skill y niveles manuales."""
    syms = syms if syms is not None else simbolos()
    if not syms:
        return []
    px = precios(syms)
    eventos = []
    for r, p in alertas.comprobar(px):
        eventos.append("%s  %s" % (r.get("symbol"),
                                   r.get("message") or ("%.2f" % p)))
    for fila, tipo, p, nivel in niveles.comprobar(px):
        etiqueta = "stop" if tipo == "stop" else "objetivo"
        eventos.append("%s a %.2f (nivel %s de %.2f)" % (
            fila.get("symbol"), p, etiqueta, nivel))
    return eventos


def texto(eventos):
    lineas = ["<b>Nivel tocado</b>"]
    for e in eventos:
        lineas.append("  " + e)
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
        try:
            eventos = revisar()
        except Exception as exc:          # un fallo de red no mata al vigilante
            print("ERROR revision: %s" % exc)
            eventos = []
        if eventos:
            msg = texto(eventos)
            print(msg.replace("<b>", "").replace("</b>", ""))
            if tg:
                try:
                    avisos.send_once(tg, ("vigia:" + "|".join(eventos))[:180], msg)
                except Exception as exc:
                    print("ERROR Telegram: %s" % exc)
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
