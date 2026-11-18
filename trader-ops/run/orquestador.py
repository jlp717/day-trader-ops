"""Orquestador determinista del banco de pruebas. Solo libreria estandar.

Cada dia construye su agenda en hora de Madrid a partir del calendario NYSE,
la ejecuta sin intervencion y deja latido y diario. Fuera de horario duerme.

Uso:
    python trader-ops/run/orquestador.py            # bucle normal
    python trader-ops/run/orquestador.py --once     # una pasada (pruebas)
    python trader-ops/run/orquestador.py --dry      # no envia a Telegram
"""
import argparse
import datetime as dt
import os
import signal
import subprocess
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import apertura, alertas, briefing, calendario, cfg, criterios, datos, diario, ganadores, proceso  # noqa: E402
from lib import posiciones, registro, skills, telegram as tg, texto  # noqa: E402
from lib import zonatiempo as zt  # noqa: E402

STATE = cfg.STATE
HEARTBEAT = STATE / "heartbeat.json"
DONE = STATE / "agenda_done.json"
TICK = 10


# ---------------------------------------------------------------- utilidades de estado

def _load(path, default):
    doc = cfg.read_json(path, None)
    return doc if doc is not None else default


def latido(phase, extra=None):
    doc = {"ts_utc": zt.iso_utc(), "ts_madrid": zt.iso_madrid(), "pid": os.getpid(),
           "phase": phase, "tz_offset": zt.offset_hours()}
    if extra:
        doc.update(extra)
    cfg.write_json(HEARTBEAT, doc)


def pausado():
    """Lee trader-ops/state/pausa.json (lo escribe /pausa en Telegram)."""
    doc = cfg.read_json(cfg.STATE / "pausa.json", {}) or {}
    return bool(doc.get("pausado"))


def keep_awake(on=True):
    """Evita la suspension mientras corre. No toca ajustes globales del sistema."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
        return True
    except Exception:
        return False


def repo_hash():
    path = os.path.join(cfg.SKILL)
    try:
        out = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30)
        return (out.stdout or "").strip() or None
    except Exception:
        return None


# ---------------------------------------------------------------- tareas

def _simbolos_orb(filas, hits, limite=150):
    """Lista del ORB: ganadores primero, luego setups, sin duplicados y con techo.

    `hits` ya viene ordenado por dolares negociados (scan.py); el orden importa
    porque la cadena completa solo corre para los 8 primeros de cada pasada.
    """
    syms = []
    for f in filas or []:
        s = f.get("symbol")
        if s and s not in syms:
            syms.append(s)
    for h in hits or []:
        s = h.get("symbol")
        if s and s not in syms:
            syms.append(s)
    return syms[:limite]


class Runner:
    def __init__(self, bot, dry=False):
        self.bot = bot
        self.dry = dry
        self.day = None
        self.done = {}
        self.last = {}
        self.errores = {}
        self.abiertas = []

    # ------------------------------------------------------------ avisos
    def aviso(self, key, text, silent=False, cooldown=3600):
        now = time.time()
        prev = self.errores.get(key, 0)
        if now - prev < cooldown:
            return
        self.errores[key] = now
        try:
            self.bot.send(text, silent=silent)
        except tg.TelegramError as exc:
            diario.append("telegram_error", where=key, error=str(exc), output=str(exc))

    def error(self, key, exc):
        diario.append("error", where=key, error=str(exc), trace=traceback.format_exc()[-1500:],
                      output=str(exc))
        self.aviso("err:" + key, "⚠️ Fallo en %s: %s" % (key, str(exc)[:300]))

    # ------------------------------------------------------------ agenda
    def tareas(self, day):
        """[(key, at_madrid, fn, repeat_seconds|None, hasta_madrid|None)]"""
        start, end, why = calendario.session_madrid(day)
        if not start:
            return [], why, None
        o = start
        flat = calendario.flat_by_madrid(day, cfg.config().get("flat_by", "15:55"))
        cutoff_et = cfg.config().get("no_entries_after", "15:30")
        o_et, c_et, _ = calendario.nyse_session(day)
        if c_et == calendario.NYSE_EARLY:
            h, m = [int(x) for x in str(cutoff_et).split(":")[:2]]
            moved = dt.datetime.combine(day, dt.time(h, m)) - (
                dt.datetime.combine(day, calendario.NYSE_CLOSE) - dt.datetime.combine(day, c_et))
            cutoff_et = moved.strftime("%H:%M")
        cutoff = zt.et_to_madrid(cutoff_et, day)
        tareas = [
            ("premarket", o - dt.timedelta(minutes=150), self.t_premarket, None, None),
            ("briefing", o - dt.timedelta(minutes=30), self.t_briefing, None, None),
            ("apertura", o, self.t_apertura, None, None),
            ("orb", o + dt.timedelta(minutes=20), self.t_orb, 300, cutoff),
            ("alertas", o, self.t_alertas, 60, end),
            ("flat", flat, self.t_flat, None, None),
            ("cierre", end, self.t_cierre, None, None),
        ]
        return tareas, why, end

    def run_day(self, now):
        day = now.date()
        if self.day != day:
            self.day = day
            self.done = {}
            self.last = {}
            doc = _load(DONE, {})
            if doc.get("date") == day.isoformat():
                self.done = dict(doc.get("done") or {})
            latido("nuevo_dia", {"day": day.isoformat()})
        tareas, why, end = self.tareas(day)
        if not tareas:
            return "cerrado: %s" % why
        start = min(t[1] for t in tareas)
        if now < start:
            return "pre-apertura"
        if now > end:
            return "cerrado"
        for key, at, fn, every, until in tareas:
            if now < at:
                continue
            if until and now > until:
                continue
            if every:
                last = self.last.get(key)
                if last and (now - last).total_seconds() < every:
                    continue
            elif self.done.get(key):
                continue
            try:
                fn(now)
                self.done[key] = zt.iso_madrid(now)
                self.last[key] = now
                cfg.write_json(DONE, {"date": day.isoformat(), "done": self.done})
            except Exception as exc:  # noqa: BLE001 - el orquestador no debe morir
                self.error(key, exc)
                self.done[key] = "error"
                cfg.write_json(DONE, {"date": day.isoformat(), "done": self.done})
        return "sesion"

    # ------------------------------------------------------------ tareas concretas
    def t_premarket(self, now):
        cfgd = cfg.config()
        watch = list(cfgd.get("watch") or ["NVDA"])
        latido("premarket")
        if not (cfg.TRADER / "universe.txt").exists():
            u = skills.run("scanner", ["universe", "--json"], timeout=180, json_out=True,
                           label="scan universe")
            diario.save_artifact("scan_universe.json", u.data or {"error": u.stderr[:500]})
        res = skills.scanner_daily(no_write=False)
        scan = res.data or {}
        if not scan:
            diario.append("scan_error", error=res.stderr[:500], output=res.stderr[:500])
        diario.save_artifact("scan_daily.json", scan)

        # ganadores de ayer entre los liquidos, y candidatos combinados para el ORB
        try:
            g = ganadores.premarket(top=20)
            diario.save_artifact("ganadores.json", g)
            self._ganadores = g
        except Exception as exc:
            diario.append("ganadores_error", error=str(exc), output=str(exc))
            g = {"filas": []}
        simbolos = _simbolos_orb(g.get("filas"), scan.get("hits"))
        # techo de carga: 150 valores por escaneo ORB cada 5 min (20 ganadores + 130 setups)
        cfg.write_json(cfg.STATE / "orb_candidates.json",
                       {"hits": [{"symbol": s} for s in simbolos]})
        self._scan = scan
        # noticias + resultados de los vigilados
        nw = skills.news(watch, hours=24)
        adverse, earnings = proceso.clasificar_noticias(nw.data, watch[0] if watch else "")
        msg = ["<b>Premarket</b> · %s" % zt.short_stamp(now),
               "Scanner: %s valores, %s escaneados, %d candidatos." % (
                   scan.get("universe"), scan.get("scanned"), len(scan.get("hits") or [])),
               "Lista ORB de hoy: %d valores (ganadores primero, luego setups)." % len(simbolos)]
        for h in (scan.get("hits") or [])[:5]:
            msg.append("  %s %s (%s)" % (h.get("symbol"), h.get("price"), ", ".join(h.get("setups") or [])))
        if adverse:
            syms = proceso.simbolos_afectados(nw.data, "adverse")
            msg.append("⚠️ Noticias adversas %s: %s" % (", ".join(syms) or "watchlist", adverse[0]))
        if earnings:
            syms = proceso.simbolos_afectados(nw.data, "earnings")
            msg.append("⚠️ Resultados cerca %s: %s" % (", ".join(syms) or "watchlist", earnings[0]))
        if not scan.get("hits"):
            msg.append("Sin setups en el scanner: es un resultado valido.")
        g = getattr(self, "_ganadores", None) or {"filas": []}
        if g.get("filas"):
            msg.append("Ganadores de ayer (liquidos, no recomendacion): " + ", ".join(
                "%s %+.0f%%" % (f["symbol"], f["pct"]) for f in g["filas"][:8]))
        from lib import avisos
        avisos.send_once(self.bot, "premarket:%s" % now.date().isoformat(), "\n".join(msg))
        # Pelosi una vez al dia (contexto, nunca senal)
        try:
            pl = skills.pelosi_new(read=False)
            items = (pl.data or {}).get("new") or (pl.data or {}).get("filings") or []
            if items:
                self.bot.send("Pelosi/contexto: hay PTR nuevos en el indice (%d). "
                              "Se leen bajo demanda con /pelosi." % len(items), silent=True)
        except Exception as exc:
            diario.append("pelosi_error", error=str(exc), output=str(exc))

    def t_briefing(self, now):
        latido("briefing")
        from lib import avisos
        scan = getattr(self, "_scan", None) or _load(STATE / "scan_daily.json", {})
        payload = briefing.construir(scan_json=scan)
        diario.save_artifact("briefing.json", payload)
        avisos.send_once(self.bot, "briefing:%s" % now.date().isoformat(), payload["texto"])

    def t_apertura(self, now):
        latido("apertura")
        from lib import avisos
        cfgd = cfg.config()
        cand = cfg.read_json(cfg.STATE / "orb_candidates.json", {}) or {}
        n_cand = len(cand.get("hits") or [])
        avisos.send_once(self.bot, "apertura:%s" % now.date().isoformat(),
                         "<b>Apertura NYSE</b> · %s\nVigilando el rango 9:30-9:45 ET de: %s%s\n"
                         "Escaner ORB cada 5 min a partir de las %s Madrid. Silencio si no hay nada." % (
                             zt.short_stamp(now), ", ".join(cfgd.get("watch") or ["NVDA"]),
                             (" + %d candidatos de la lista ORB" % n_cand) if n_cand else "",
                             (now + dt.timedelta(minutes=20)).strftime("%H:%M")), silent=True)

    def t_orb(self, now):
        latido("orb")
        cfgd = cfg.config()
        watch = list(cfgd.get("watch") or ["NVDA"])
        cand = cfg.STATE / "orb_candidates.json"
        doc_cand = cfg.read_json(cand, {}) or {}
        ruta = str(cand) if doc_cand.get("hits") else "trader/watchlist.json"
        if ruta == "trader/watchlist.json" and not (cfg.TRADER / "watchlist.json").exists():
            diario.append("orb_sin_candidatos", output="ni orb_candidates.json ni trader/watchlist.json")
            return
        res = skills.scanner_orb(watchlist=ruta, out=str(cfg.STATE / "orb.json"))
        doc = res.data or {}
        diario.save_artifact("scan_orb.json", doc)
        hits = doc.get("hits") or []
        if not hits:
            diario.append("orb_sin_hits", scanned=doc.get("scanned"), output=str(doc.get("scanned")))
            return
        # union: primero los ganadores que hayan roto, luego el resto, y los vigilados fijos
        gdoc = cfg.read_json(cfg.STATE / "ganadores.json", {}) or {}
        ganadores_hoy = {f.get("symbol") for f in (gdoc.get("filas") or []) if f.get("symbol")}
        seg = cfg.read_json(cfg.STATE / "seguir.json", {}) or {}
        if seg.get("date") == zt.madrid().date().isoformat():
            ganadores_hoy.update(seg.get("symbols") or [])
        ordenados = sorted(hits, key=lambda h: (0 if h.get("symbol") in ganadores_hoy else 1))
        syms = []
        for h in ordenados:
            if h.get("symbol") and h["symbol"] not in syms:
                syms.append(h["symbol"])
        for s in watch:
            if s not in syms:
                syms.append(s)
        for sym in syms[:8]:
            out = proceso.evaluar_symbol(sym, cfgd=cfgd, enviar=(not self.dry) and (not pausado()),
                                         bot=self.bot)
            diario.append("pipeline", symbol=sym, verdict=out.get("verdict"),
                          reasons="; ".join(out.get("reasons") or [])[:600],
                          output="; ".join(out.get("reasons") or [])[:600])

    def t_alertas(self, now):
        """Comprueba reglas de precio cada minuto y avisa de proximidad a stop/objetivo."""
        from lib import avisos
        if not alertas.reglas():
            return
        abiertas = {p["id"]: p for p in posiciones.abiertas()}

        def _extra(rid):
            if not rid.startswith("pos-"):
                return ""
            pid = rid[4:].rsplit("-", 1)[0]
            p = abiertas.get(pid)
            if not p:
                return ""
            if rid.endswith("-stop"):
                return ("\nSTOP del plan (%s). Si sigues dentro, cierra a mano.\n"
                        "Que haces: vende %s a mercado o limitada, cancela el stop-loss y /sali %s <fill>."
                        % (p.get("stop"), ("%g" % float(p.get("qty") or 0)), p.get("symbol")))
            if rid.endswith("-target"):
                return ("\nOBJETIVO (%s). Si sigues dentro, recoge a mano.\n"
                        "Que haces: vende %s con limitada %s, cancela el stop y /sali %s <fill>."
                        % (p.get("target"), ("%g" % float(p.get("qty") or 0)),
                           p.get("target"), p.get("symbol")))
            return ""

        rings = []
        if alertas.reglas_skill():
            r = skills.alerts_check()
            rings.extend((r.data or {}).get("rings") or [])
        for regla, _px in alertas.comprobar_xetra():
            rings.append({"id": regla.get("id"), "symbol": regla.get("symbol"),
                          "message": regla.get("message") or "alerta Xetra"})
        for a in rings:
            txt = a.get("message") or "alerta"
            self.bot.send("🔔 %s%s" % (txt, _extra(a.get("id") or "")))

        # proximidad: 0,5 % antes del stop y del objetivo, una vez por nivel y dia
        for p in posiciones.abiertas():
            try:
                px = datos.quote(p["symbol"])["price"]
            except Exception:
                continue
            for tipo, nivel in (("stop", p.get("stop")), ("objetivo", p.get("target"))):
                if not nivel:
                    continue
                dist = abs(float(px) - float(nivel)) / float(px) * 100.0
                if dist > 0.5:
                    continue
                key = "cerca-%s-%s-%s" % (tipo, p["id"], zt.madrid().date().isoformat())
                avisos.send_once(
                    self.bot, key,
                    "⚠️ %s a %.2f · a %.2f%% de tu %s (%.2f). Si lo toca, te aviso; decides tu."
                    % (p["symbol"], px, dist, tipo, float(nivel)))
        precios = {}
        for a in rings:
            sym = a.get("symbol")
            if sym and sym not in precios:
                try:
                    precios[sym] = datos.quote(sym)["price"]
                except Exception:
                    pass
        if precios:
            registro.marcar_resultados(precios)

    def t_flat(self, now):
        cfgd = cfg.config()
        latido("flat_by")
        from lib import avisos
        abiertas = registro.open_signals()
        extra = ""
        if abiertas:
            extra = "\nSeñales abiertas: " + ", ".join(
                "%s (stop %s / objetivo %s)" % (s["symbol"], s["plan"].get("stop"), s["plan"].get("target"))
                for s in abiertas)
        manual = posiciones.abiertas()
        if manual:
            extra += "\nPosiciones a mano: " + ", ".join(
                "%s %s acc (stop %s / objetivo %s)" % (
                    p["symbol"], p.get("qty"), p.get("stop"), p.get("target")) for p in manual)
        avisos.send_once(self.bot, "flat:%s" % now.date().isoformat(),
                         "⏰ <b>Flat by close</b> · %s\nSi sigues dentro, cierra a mano: no se mantiene nada "
                         "durante la noche.%s\nDetalle y orden exacta: /guia" % (zt.short_stamp(now), extra))

    def t_cierre(self, now):
        from lib import avisos, informe
        latido("cierre")
        doc = informe.generar(now)
        avisos.send_once(self.bot, "cierre:%s" % now.date().isoformat(),
                         doc["texto"][:4000], silent=True)
        diario.save_artifact("informe_dia.json", doc)


# ---------------------------------------------------------------- semanal

def tarea_semanal(now, bot):
    """Lunes: hash del repo + resumen semanal."""
    guardado = _load(STATE / "repo_hash.json", {})
    actual = repo_hash()
    if guardado.get("hash") and actual and actual != guardado["hash"]:
        bot.send("⚠️ El repo del skill cambio: %s -> %s. No se actualiza solo; revisalo."
                 % (guardado["hash"][:10], actual[:10]))
    if actual:
        cfg.write_json(STATE / "repo_hash.json", {"hash": actual, "visto": zt.iso_utc()})
    try:
        from lib import informe
        txt = informe.semanal(now)
        bot.send(txt[:4000], silent=True)
    except Exception as exc:
        diario.append("semanal_error", error=str(exc), output=str(exc))


# ---------------------------------------------------------------- bucle

def main(argv=None):
    ap = argparse.ArgumentParser(description="Orquestador del banco de pruebas en papel")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--simular", help="muestra la agenda de un dia (YYYY-MM-DD) y sale")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)

    if a.simular:
        day = dt.date.fromisoformat(a.simular)
        r = Runner(tg.Telegram(dry=True), dry=True)
        tareas, why, end = r.tareas(day)
        print("Agenda %s (%s)" % (day.isoformat(), why))
        for key, at, fn, every, until in tareas:
            print("  %-9s %s Madrid%s%s" % (key, at.strftime("%H:%M"),
                                            (" cada %ds" % every) if every else "",
                                            (" hasta %s" % until.strftime("%H:%M")) if until else ""))
        return 0

    bot = tg.Telegram(dry=True if a.dry else None)
    runner = Runner(bot, dry=a.dry)
    keep_awake(True)
    diario.append("arranque", pid=os.getpid(), dry=a.dry, tz_offset=zt.offset_hours(),
                  output="arranque")
    latido("arranque")

    def _stop(*_):
        keep_awake(False)
        diario.append("parada", pid=os.getpid(), output="parada")
        latido("parada")
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
    except Exception:
        pass

    semanal_hecho = _load(STATE / "agenda_done.json", {}).get("semanal")

    while True:
        now = zt.madrid()
        try:
            # si arrancamos sin secretos, activar el envio en cuanto existan
            if runner.bot.dry:
                sec = cfg.telegram_secret()
                if sec.get("bot_token") and sec.get("chat_id"):
                    runner.bot = tg.Telegram()
                    runner.dry = False
                    diario.append("bot_activado", chat=sec.get("chat_id"), output="activado")
                    try:
                        runner.bot.send("✅ Orquestador conectado. A partir de ahora los avisos "
                                        "llegan aqui. PRUEBA EN PAPEL.", silent=True)
                    except tg.TelegramError:
                        pass
            estado = runner.run_day(now)
            if a.verbose:
                print(now.strftime("%H:%M:%S"), estado)
            # semanal (lunes 9:00 Madrid)
            if now.weekday() == 0 and now.hour >= 9 and semanal_hecho != now.date().isoformat():
                tarea_semanal(now, bot)
                semanal_hecho = now.date().isoformat()
                cfg.write_json(DONE, {"date": now.date().isoformat(),
                                      "done": runner.done, "semanal": semanal_hecho})
            latido(estado)
        except Exception as exc:  # noqa: BLE001
            runner.error("bucle", exc)
        if a.once:
            return 0
        time.sleep(TICK)


if __name__ == "__main__":
    sys.exit(main())
