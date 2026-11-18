"""Vigilante: avisa si el orquestador cae o si hay hueco de datos.

No reinicia nada por su cuenta (el reinicio lo hace el Programador de tareas).
Uso:
    python trader-ops/run/watchdog.py            # una comprobacion
    python trader-ops/run/watchdog.py --bucle    # cada 5 minutos
"""
import argparse
import datetime as dt
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import calendario, cfg, diario, telegram as tg  # noqa: E402
from lib import zonatiempo as zt  # noqa: E402

HB = cfg.STATE / "heartbeat.json"
COOLDOWN = cfg.STATE / "watchdog_last.json"


def _age_seconds(iso):
    try:
        t = dt.datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except Exception:
        return None
    return (zt.now_utc() - t).total_seconds()


def _puede_avisar(key, minutos=30):
    doc = cfg.read_json(COOLDOWN, {}) or {}
    last = doc.get(key, 0)
    now = time.time()
    if now - last < minutos * 60:
        return False
    doc[key] = now
    cfg.write_json(COOLDOWN, doc)
    return True


def _ventana_orb(now, start, end, cutoff):
    """True solo entre la primera pasada del ORB y el corte de entradas.

    Entre la apertura (15:30) y las 15:50 no hay escaneo ORB por diseno: el
    premarket de las 13:00 es la ultima pasada. Avisar a las 15:34 de un hueco
    de 152 min es un falso positivo, no una averia.
    """
    if not start or not end:
        return False
    ini = start + dt.timedelta(minutes=20)
    fin = min(cutoff, end) if cutoff else end
    return ini <= now <= fin


def comprobar(bot=None):
    bot = bot or tg.Telegram()
    problemas = []
    hb = cfg.read_json(HB, {}) or {}
    age = _age_seconds(hb.get("ts_utc"))
    now = zt.madrid()
    start, end, why = calendario.session_madrid(now.date())
    en_sesion = bool(start and start <= now <= end)
    limite = 600 if en_sesion else 3600
    if age is None:
        problemas.append(("sin_latido", "No hay latido del orquestador."))
    elif age > limite:
        problemas.append(("latido_viejo", "El orquestador no late desde hace %d min (fase %s)." % (
            age / 60, hb.get("phase"))))
    # hueco de datos: ultimo comando del scanner, solo dentro de la ventana ORB
    last_scan = diario.last_command("scanner")
    cutoff = zt.et_to_madrid(cfg.config().get("no_entries_after", "15:30"), now.date())
    if _ventana_orb(now, start, end, cutoff):
        if not last_scan:
            problemas.append(("hueco_datos", "El escaner ORB no ha hecho ninguna pasada."))
        else:
            sage = _age_seconds(last_scan.get("ts_utc"))
            if sage and sage > 1800:
                problemas.append(("hueco_datos", "Sin pasada del scanner desde hace %d min." % (sage / 60)))
    # errores recientes
    errs = [e for e in diario.read_all() if e.get("event") in ("error", "telegram_error")
            and (_age_seconds(e.get("ts_utc")) or 1e9) < 3600]
    if len(errs) >= 3:
        problemas.append(("errores", "%d errores en la ultima hora (ultimo: %s)." % (
            len(errs), str(errs[-1].get("where") or errs[-1].get("error"))[:120])))

    enviados = []
    for key, text in problemas:
        if _puede_avisar(key):
            try:
                bot.send("🩺 Vigilante: " + text, silent=False)
                enviados.append(key)
            except tg.TelegramError as exc:
                diario.append("watchdog_error", error=str(exc), output=str(exc))
    diario.append("watchdog", problemas=[p[0] for p in problemas], enviados=enviados,
                  output="; ".join(p[1] for p in problemas))
    return problemas, enviados


def main(argv=None):
    ap = argparse.ArgumentParser(description="Vigilante del orquestador")
    ap.add_argument("--bucle", action="store_true")
    ap.add_argument("--cada", type=int, default=300)
    a = ap.parse_args(argv)
    while True:
        problemas, enviados = comprobar()
        print(zt.short_stamp(), "problemas:", [p[0] for p in problemas] or "ninguno")
        if not a.bucle:
            return 0
        time.sleep(a.cada)


if __name__ == "__main__":
    sys.exit(main())
