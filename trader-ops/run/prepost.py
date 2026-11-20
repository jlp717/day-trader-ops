"""Analisis pre/post market con Yahoo. Solo lectura, sin ordenes.

    python trader-ops/run/prepost.py --symbols NVDA,AMD --modo pre
    python trader-ops/run/prepost.py --symbols NVDA,AMD --modo post --json salida.json

MyInvestor no permite ejecutar fuera del horario regular: esto prepara el plan.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import cfg, calendario, prepost, zonatiempo as zt  # noqa: E402


def _send(text):
    from lib import telegram as tg
    try:
        tg.Telegram().send(text)
        return True
    except Exception as exc:
        print("ERROR Telegram: %s" % exc)
        return False


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Analisis pre/post market")
    ap.add_argument("--symbols", help="lista separada por comas")
    ap.add_argument("--radar", action="store_true", help="escanear una lista y ordenar por movimiento")
    ap.add_argument("--top", type=int, default=30, help="candidatos del scan diario para el radar")
    ap.add_argument("--limit", type=int, default=30, help="maximo de simbolos a consultar")
    ap.add_argument("--modo", choices=("pre", "post"), default="pre")
    ap.add_argument("--json", help="guardar el resultado")
    ap.add_argument("--out", help="ruta del radar (por defecto state/pre|post/radar.json)")
    ap.add_argument("--send", action="store_true", help="enviar el resultado a Telegram")
    a = ap.parse_args(argv)
    start, end, why = calendario.session_madrid(zt.madrid().date())
    if not start:
        print("Sin mercado hoy: %s" % why)
        return 0
    if a.radar:
        syms = ([x.strip().upper() for x in a.symbols.split(",") if x.strip()]
                if a.symbols else prepost.symbols_from_scan(a.top))
        filas = prepost.radar(syms, a.modo, a.limit)
        out = a.out or str(cfg.STATE / a.modo / "radar.json")
        prepost.guardar(out, filas)
        texto = prepost.texto(filas, a.modo)
        print(texto)
        print("\nGuardado: %s" % out)
        if a.send and filas:
            _send(texto)
        return 0
    if not a.symbols:
        print("ERROR: pasa --symbols o --radar")
        return 2
    syms = [x.strip().upper() for x in a.symbols.split(",") if x.strip()]
    filas = []
    for sym in syms:
        try:
            filas.append(prepost.resumen(sym, a.modo))
        except Exception as exc:
            print("%-6s ERROR %s" % (sym, str(exc)[:120]))
    if filas:
        prepost.imprimir(filas)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(filas, f, ensure_ascii=False, indent=2)
        print("\nJSON: %s" % a.json)
    print("\nSolo analisis: MyInvestor no ejecuta fuera del horario regular.")
    if a.send and filas:
        _send(prepost.texto(filas, a.modo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
