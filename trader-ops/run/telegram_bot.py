"""Bot de Telegram: comandos deterministas, sin LLM y sin shell.

Solo atiende al chat_id configurado. Los argumentos se validan con expresiones
regulares; nunca se pasa texto libre a un proceso. Cada comando tiene timeout y
la salida se recorta a 4096 caracteres.

Uso:
    python trader-ops/run/telegram_bot.py                 # long polling
    python trader-ops/run/telegram_bot.py --simulate /reloj
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import apertura, briefing, calendario, cfg, criterios, datos, diario, ganadores, mercado  # noqa: E402
from lib import ahora, alertas, estado_vivo, niveles, raw, referencias, prepost, tesis  # noqa: E402
from lib import posiciones, proceso, registro, research, skills, telegram as tg, texto  # noqa: E402
from lib import zonatiempo as zt  # noqa: E402

PAUSA = cfg.STATE / "pausa.json"
OFFSET = cfg.STATE / "tg_offset.json"
COOLDOWN = {"scan": 30, "ticker": 20, "tm": 15, "briefing": 30}
_last = {}


def pausado():
    doc = cfg.read_json(PAUSA, {}) or {}
    return bool(doc.get("pausado"))


def set_pausa(valor, motivo=""):
    cfg.write_json(PAUSA, {"pausado": bool(valor), "desde": zt.iso_madrid(), "motivo": motivo})


# ---------------------------------------------------------------- helpers

def _fmt(x, dec=2):
    try:
        return ("%%.%df" % dec) % float(x)
    except (TypeError, ValueError):
        return "n/d"


def _qty(x):
    """Cantidad: 87 si es entera, 87.5 si es fraccionaria."""
    try:
        v = float(x)
        return ("%d" % v) if v.is_integer() else ("%g" % v)
    except (TypeError, ValueError):
        return str(x)


def _sandbox(symbol):
    d = cfg.STATE / "cmd" / symbol.upper()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run(args, timeout=120, json_out=True, name=None):
    """Ejecuta un script con lista de argumentos ya validada."""
    return skills.run(name or "scanner", args, timeout=timeout, json_out=json_out)


NO_TICKERS = {
    "NADA", "TODO", "HOY", "AHORA", "ESTO", "ESO", "QUE", "COMO", "PLAN", "STOP", "TIME",
    "CUANDO", "DONDE", "PORQUE", "MEJOR", "PEOR", "COMPRA", "VENTA", "LIBRO", "RANGO",
    "PRECIO", "NIVEL", "ORDEN", "DATOS", "MIRA", "VER", "ANALIZA", "EVALUA", "SENAL",
    "MAS", "MENOS", "CON", "SIN", "POR", "PARA", "LOS", "LAS", "DEL", "CUAL", "CUALES",
    "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ",
    "ALGO", "POCO", "BIEN", "MAL", "OTRA", "OTRO", "AQUI", "ALLI",
}


def _ticker(arg):
    t = (arg or "").strip().upper()
    if t in NO_TICKERS:
        return None
    return t if texto.is_ticker(t) else None


def _cadena(symbol, target="2R", stop="or-mid"):
    """entry -> exit -> tm -> size -> risk en un directorio aparte, sin tocar el plan vivo."""
    d = _sandbox(symbol)
    entry_p = d / "entry.json"
    plan_p = d / "plan.json"
    tm_p = d / "tm.json"
    orders_p = d / "orders.json"
    prices_p = d / "prices.json"
    out = {"symbol": symbol}
    e = skills.run("entry", ["check", symbol, "--json", "--write", str(entry_p)],
                   timeout=120, json_out=True)
    out["entry"] = e.data or {"error": e.stderr.strip()[:300]}
    if (out["entry"] or {}).get("status") != "triggered":
        return out
    x = skills.run("exit", ["plan", "--from", str(entry_p), "--stop", stop, "--target", target,
                            "--json", "--write", str(plan_p)], timeout=120, json_out=True)
    out["plan"] = x.data or {"error": x.stderr.strip()[:300]}
    if not (out["plan"] or {}).get("entry"):
        return out
    t = skills.run("timemachine", ["run", "--plan", str(plan_p), "--until",
                                   str(out["plan"].get("flat_by") or "15:55"),
                                   "--json", "--write", str(tm_p)], timeout=600, json_out=True)
    out["tm"] = t.data or {"error": t.stderr.strip()[:300]}
    skills.run("alerts", ["quote", symbol, "--json", "--write", str(prices_p)], timeout=90, json_out=True)
    b = skills.run("budget", ["--plan", str(plan_p), "--prices", str(prices_p), "--json",
                              "--write", str(orders_p), "--limit"], timeout=120, json_out=True)
    out["budget"] = b.data or {"error": b.stderr.strip()[:300]}
    r = skills.run("risk", ["--orders", str(orders_p), "--prices", str(prices_p),
                            "--portfolio", "trader/portfolio.json", "--out", str(d / "risk.json"),
                            "--json", "--no-write"], timeout=120, json_out=True)
    out["risk"] = r.data or {"error": r.stderr.strip()[:300]}
    return out


# ---------------------------------------------------------------- comandos

def c_estado(bot, args):
    hb = cfg.read_json(cfg.STATE / "heartbeat.json", {}) or {}
    st = registro.stats()
    pnl = posiciones.pnl()
    freno, motivo = registro.freno_activo()
    lat = cfg.read_json(OFFSET, {}) or {}
    txt = ("<b>Estado</b>\n"
           "Orquestador: %s (latido %s, fase %s)\n"
           "Pausa: %s\n"
           "Registro: %d señales, %d cerradas, R medio %+.2f\n"
           "Posiciones a mano: %d abiertas, PnL %+.2f USD\n"
           "Freno por evidencia: %s (%s)\n"
           "Zona: Madrid %s / NY %s (desfase %dh)") % (
        "vivo" if hb else "sin latido", hb.get("ts_madrid", "n/d"), hb.get("phase", "n/d"),
        "SI" if pausado() else "no", st["total"], st["cerradas"], st["r_medio"],
        len(posiciones.abiertas()), pnl["pnl_usd"], "ACTIVO" if freno else "no", motivo,
        zt.madrid().strftime("%H:%M"), zt.ny().strftime("%H:%M"), zt.offset_hours())
    return txt


def c_reloj(bot, args):
    now = zt.now_utc()
    start, end, why = calendario.session_madrid(now.date())
    nxt = calendario.next_trading_day(now.date(), "US", include_today=True)
    s2, e2, _ = calendario.session_madrid(nxt) if nxt else (None, None, "")
    return ("<b>Reloj</b>\nMadrid %s\nNueva York %s\nDesfase %dh\n"
            "Sesion NYSE hoy: %s\nSiguiente sesion: %s %s-%s Madrid") % (
        zt.human(now, zt.MADRID), zt.human(now, zt.NEW_YORK), zt.offset_hours(),
        ("%s-%s (%s)" % (start.strftime("%H:%M"), end.strftime("%H:%M"), why)) if start else why,
        nxt.isoformat() if nxt else "n/d",
        s2.strftime("%H:%M") if s2 else "n/d", e2.strftime("%H:%M") if e2 else "n/d")


def c_briefing(bot, args):
    scan = diario.load_artifact("scan_daily.json", {}) or {}
    return briefing.construir(scan_json=scan)["texto"]


def c_scan(bot, args):
    symbols = None
    if args:
        symbols = [_ticker(t) for a in args for t in str(a).split(",") if _ticker(t)]
        if not symbols:
            return "Uso: /scan [TICKER ...]"
    if symbols:
        r = skills.scanner_daily(symbols=symbols, no_write=True)
    else:
        r = skills.scanner_daily(no_write=True)
    doc = r.data or {}
    if not doc:
        return "Scanner sin datos: %s" % (r.stderr.strip()[:300] or "sin salida")
    lines = ["<b>Scan daily</b> · %s ET" % doc.get("as_of"),
             "%s valores, %s escaneados, %s fallos, %d candidatos" % (
                 doc.get("universe"), doc.get("scanned"), doc.get("failed"), len(doc.get("hits") or []))]
    for h in (doc.get("hits") or [])[:12]:
        lines.append("  %s %s (%s)" % (h.get("symbol"), h.get("price"), ", ".join(h.get("setups") or [])))
    if not doc.get("hits"):
        lines.append("Ninguno paso el filtro. No se relajan las reglas.")
    return "\n".join(lines)


def c_ticker(bot, args):
    sym = _ticker(args[0]) if args else None
    if not sym:
        return "Uso: /ticker NVDA"
    if alertas.es_xetra(sym):
        return _aviso_xetra(sym)
    out = _cadena(sym)
    lines = ["<b>%s</b>" % sym]
    e = out.get("entry") or {}
    lines.append("Setup: %s (%s)" % (e.get("status"), e.get("reason") or "sin detalle"))
    if e.get("opening_range"):
        o = e["opening_range"]
        lines.append("Rango: %.2f - %.2f" % (o.get("high"), o.get("low")))
    if e.get("status") != "triggered":
        nw = skills.news([sym], hours=24)
        adv, ern = proceso.clasificar_noticias(nw.data, sym)
        lines.append("Noticias: %s" % (adv[0] if adv else "sin adversas"))
        lines.append("Resultados: %s" % (ern[0] if ern else "sin senal de resultados hoy/manana"))
        return "\n".join(lines)
    p = out.get("plan") or {}
    lines.append("Entrada %s · stop %s · objetivo %s (%sR) · flat %s ET" % (
        _fmt(p.get("entry")), _fmt(p.get("stop")), _fmt(p.get("target")), p.get("target_r"), p.get("flat_by")))
    tm = (out.get("tm") or {}).get("mc") or {}
    if tm:
        nums = (out.get("tm") or {}).get("history") or {}
        lines.append("TM: objetivo %s%%, stop %s%%, nada %s%% (%s replays)" % (
            _fmt(100 * (tm.get("p_target") or 0), 1), _fmt(100 * (tm.get("p_stop") or 0), 1),
            _fmt(100 * (tm.get("p_neither") or 0), 1), tm.get("replays")))
        lines.append("Historico: %s disparos, %s objetivo, %s stop" % (
            nums.get("triggered"), nums.get("target"), nums.get("stop")))
    b = out.get("budget") or {}
    if b.get("qty") or b.get("orders"):
        q = (b.get("orders") or [b])[0]
        lines.append("Tamano: %s acc · perdida max %s USD" % (q.get("qty"), _fmt(q.get("plan", {}).get("max_loss"))))
    r = out.get("risk") or {}
    if r.get("results"):
        lines.append("Risk: %s (%s)" % (r["results"][0].get("verdict"),
                                        "; ".join(r["results"][0].get("reasons") or [])[:160]))
    nw = skills.news([sym], hours=24)
    adv, ern = proceso.clasificar_noticias(nw.data, sym)
    lines.append("Noticias: %s" % (adv[0] if adv else "sin adversas"))
    lines.append("Resultados: %s" % (ern[0] if ern else "sin senal de resultados"))
    lines.append("PRUEBA EN PAPEL")
    return "\n".join(lines)


def c_vigila(bot, args):
    sym = _ticker(args[0]) if args else None
    if not sym:
        return "Uso: /vigila NVDA"
    cfgd = cfg.config()
    watch = list(cfgd.get("watch") or [])
    if sym not in watch:
        watch.append(sym)
        cfgd["watch"] = watch
        cfg.write_json(cfg.TRADER / "config.json", cfgd)
    q = None
    try:
        q = datos.quote(sym)
    except Exception:
        pass
    return "Vigilando %s. Lista: %s%s" % (sym, ", ".join(watch),
                                         (" · precio %s" % _fmt(q["price"])) if q else "")


def c_dejar(bot, args):
    sym = _ticker(args[0]) if args else None
    if not sym:
        return "Uso: /dejar NVDA"
    cfgd = cfg.config()
    watch = [s for s in (cfgd.get("watch") or []) if s != sym]
    cfgd["watch"] = watch
    cfg.write_json(cfg.TRADER / "config.json", cfgd)
    return "Ya no vigilo %s. Lista: %s" % (sym, ", ".join(watch) or "(vacia)")


def c_plan(bot, args):
    sym = _ticker(args[0]) if args else None
    if not sym:
        return "Uso: /plan NVDA"
    out = _cadena(sym)
    e = out.get("entry") or {}
    if e.get("status") != "triggered":
        return "%s: %s (%s). Sin plan: no hay disparo." % (sym, e.get("status"), e.get("reason") or "")
    p = out.get("plan") or {}
    return ("<b>Plan %s</b>\nEntrada %s\nStop %s (%s)\nObjetivo %s (%sR)\nRiesgo/accion %s\n"
            "R:R %s\nFlat by %s ET\nNada enviado: es papel." % (
                sym, _fmt(p.get("entry")), _fmt(p.get("stop")), p.get("stop_label"),
                _fmt(p.get("target")), p.get("target_r"), _fmt(p.get("risk_per_share")),
                p.get("reward_risk"), p.get("flat_by")))


def c_tm(bot, args):
    sym = _ticker(args[0]) if args else None
    if not sym:
        return "Uso: /tm NVDA"
    out = _cadena(sym, target="2R")
    tm = out.get("tm") or {}
    if not tm.get("mc"):
        return "Time Machine no disponible: %s" % (tm.get("error") or "sin datos suficientes")
    mc, h = tm["mc"], tm.get("history") or {}
    return ("<b>Time Machine %s</b>\nObjetivo primero %s%% · stop %s%% · nada %s%%\n"
            "Media R %s · %s replays seed %s\nHistorico: %s disparos, %s objetivo, %s stop, R medio %s\n%s" % (
                sym, _fmt(100 * mc.get("p_target"), 1), _fmt(100 * mc.get("p_stop"), 1),
                _fmt(100 * mc.get("p_neither"), 1), _fmt(mc.get("avg_R"), 3), mc.get("replays"),
                mc.get("seed"), h.get("triggered"), h.get("target"), h.get("stop"),
                _fmt(h.get("avg_R"), 3), tm.get("verdict") or ""))


def c_tamano(bot, args):
    sym = _ticker(args[0]) if args else None
    if not sym:
        return "Uso: /tamano NVDA"
    out = _cadena(sym)
    b = out.get("budget") or {}
    q = (b.get("orders") or [b])[0] if (b.get("orders") or b.get("symbol")) else {}
    if not q.get("qty"):
        return "Sin tamano: %s" % (b.get("error") or "budget no propone orden")
    return ("<b>Tamano %s</b>\n%s acciones · %s USD\nPerdida maxima al stop %s USD\n%s" % (
        sym, q.get("qty"), _fmt(float(q.get("qty") or 0) * float((q.get("plan") or {}).get("entry") or 0)),
        _fmt((q.get("plan") or {}).get("max_loss")), q.get("why") or ""))


def c_risk(bot, args):
    r = skills.risk_check()
    doc = r.data or {}
    if not doc:
        return "Risk sin salida: %s" % (r.stderr.strip()[:300] or "sin ordenes")
    lines = ["<b>Risk</b> · %s NY" % doc.get("now_new_york"),
             "%s pasan, %s bloqueadas" % (doc.get("pass"), doc.get("block"))]
    for res in doc.get("results") or []:
        lines.append("  %s %s %s: %s %s" % (res.get("index"), res.get("side"), res.get("symbol"),
                                            res.get("verdict"), "; ".join(res.get("reasons") or [])[:200]))
    return "\n".join(lines)


def c_ticket(bot, args):
    r = skills.ticket_show()
    doc = r.data or {}
    if isinstance(doc, list):
        tickets = doc
    else:
        tickets = doc.get("tickets") or doc.get("orders") or []
    if not tickets:
        return "No hay ticket. Primero /plan y /tamano."
    lines = ["<b>Ticket (papel)</b>"]
    for t in tickets[:3]:
        ti = t.get("tool_input") or t
        lines.append("%s %s %s · stop %s · objetivo %s · %s" % (
            ti.get("side"), ti.get("qty"), ti.get("symbol"), ti.get("stop_loss_stop_price"),
            ti.get("take_profit_limit_price"),
            "READY" if t.get("ready") else str(t.get("status") or "")[:60]))
    lines.append("No se envia nada: no hay broker conectado.")
    return "\n".join(lines)


def c_alertas(bot, args):
    rules = alertas.reglas()
    if not rules:
        return "Sin alertas configuradas para hoy."
    lines = ["<b>Alertas de hoy</b> (%d)" % len(rules)]
    for x in rules[:25]:
        lines.append("  %s · %s · %s %s%s" % (
            x.get("id"), x.get("symbol"), x.get("type"), _fmt(x.get("price")),
            " (Xetra)" if alertas.es_xetra(x.get("symbol")) else ""))
    return "\n".join(lines)


def c_ref(bot, args):
    """Guarda una referencia de precio que has visto en una fuente externa."""
    if not 2 <= len(args) <= 4:
        return "Uso: /ref NVD.DE 139.40 borse [EUR]"
    sym = _ticker(args[0])
    price = texto.safe_float(args[1], 0.0001, 1e7)
    if not sym or price is None:
        return "Uso: /ref NVD.DE 139.40 borse [EUR]"
    source = str(args[2]).lower() if len(args) > 2 else "manual"
    currency = str(args[3]).upper() if len(args) > 3 else None
    try:
        r = referencias.add(sym, price, source=source, currency=currency, note="telegram")
    except ValueError as exc:
        return "No se guardo la referencia: %s" % exc
    return ("Referencia guardada: %s %s %s · %s · %s Madrid.\n"
            "Consulta /precios %s para compararla con Yahoo y el plan." % (
                r["symbol"], _fmt(r["price"]), r["currency"], r["source"],
                r["ts_madrid"][11:19], r["symbol"]))


def c_precios(bot, args):
    """Yahoo automatico + referencias manuales + plan vigente, en una tabla."""
    sym = _ticker(args[0]) if args else None
    if not sym:
        return "Uso: /precios NVD.DE"
    lines = ["<b>Precios %s</b>" % sym]
    q = None
    try:
        q = datos.quote(sym)
        lines.append("Yahoo: %s %s · %s · hace %ss · %s" % (
            _fmt(q.get("price")), q.get("currency") or "?", q.get("data_time") or "n/d",
            q.get("age_seconds"), q.get("exchange") or "?"))
    except datos.DataError as exc:
        lines.append("Yahoo: no disponible (%s)" % str(exc)[:120])
    alt = None
    try:
        alt = datos.quote_cnbc(sym)
        lines.append("CNBC: %s USD · %s · hace %ss" % (
            _fmt(alt.get("price")), alt.get("data_time") or "n/d", alt.get("age_seconds")))
    except datos.DataError as exc:
        lines.append("CNBC: no disponible (%s)" % str(exc)[:80])
    fh = None
    try:
        fh = datos.quote_finnhub(sym)
        lines.append("Finnhub: %s USD · %s · hace %ss" % (
            _fmt(fh.get("price")), fh.get("data_time") or "n/d", fh.get("age_seconds")))
    except datos.DataError as exc:
        if "sin clave" not in str(exc):
            lines.append("Finnhub: no disponible (%s)" % str(exc)[:80])
    if q and (q.get("age_seconds") or 0) > 300:
        lines.append("AVISO: Yahoo va con retraso (>300 s). No operes con esta tabla; usa /ref con lo que veas en Börse Frankfurt/TradingView/MyInvestor.")
    refs = referencias.get(sym)
    for r in refs:
        lines.append("%s: %s %s · %s Madrid · hace %ss" % (
            r["source"], _fmt(r["price"]), r["currency"], r["ts_madrid"][11:19], r["age_s"]))
    if not refs:
        lines.append("Sin referencias manuales. Añade /ref %s PRECIO borse|tv|investing|mx" % sym)
    prices = []
    if q:
        prices.append(float(q["price"]))
    if alt:
        prices.append(float(alt["price"]))
    if fh:
        prices.append(float(fh["price"]))
    prices += [float(r["price"]) for r in refs]
    if len(prices) >= 2 and min(prices) > 0:
        diff = (max(prices) - min(prices)) / min(prices) * 100.0
        lines.append("Diferencia entre fuentes: %.2f%% (%s)" % (
            diff, "OK" if diff <= 0.5 else "AVISO: >0,5%, no operes a mercado"))
    plan = cfg.read_json(cfg.TRADER / "plan.json", {}) or {}
    if plan.get("symbol") == sym:
        lines.append("Plan vigente: entrada %s · stop %s · objetivo %s (%sR) · flat %s ET" % (
            _fmt(plan.get("entry")), _fmt(plan.get("stop")), _fmt(plan.get("target")),
            plan.get("target_r"), plan.get("flat_by")))
    else:
        lines.append("Plan vigente: no hay plan para %s. El plan sale de la SEÑAL A." % sym)
    lines.append("Para /entre: usa el fill de MyInvestor, no esta tabla. Stop/objetivo salen del plan.")
    return "\n".join(lines)


def c_alerta(bot, args):
    if len(args) != 2:
        return "Uso: /alerta NVDA 155.20"
    sym = _ticker(args[0])
    price = texto.safe_float(args[1], 0.0001, 1e7)
    if not sym or price is None:
        return "Uso: /alerta NVDA 155.20 (precio valido)"
    rid = "tg-alerta-%s-%s-%s" % (sym.lower(), str(price).replace(".", "-"), alertas.hoy_ny())
    ok, motivo = alertas.armar(sym, "above", price, rid, label="alerta")
    if not ok:
        return "No se pudo poner la alerta de %s: %s." % (sym, motivo)
    return "Alerta puesta para hoy: %s por encima de %s." % (sym, _fmt(price))


def c_noticias(bot, args):
    sym = _ticker(args[0]) if args else None
    if not sym:
        return "Uso: /noticias NVDA"
    r = skills.news([sym], hours=24)
    doc = r.data or {}
    items = doc.get("items") or []
    if not items:
        return "Sin noticias nuevas en 24 h para %s." % sym
    lines = ["<b>Noticias %s</b>" % sym]
    for it in items[:8]:
        lines.append("  %s %s [%s]" % (str(it.get("time"))[11:16], (it.get("title") or "")[:110],
                                       ",".join(it.get("tags") or [])))
    return "\n".join(lines)


def c_resultados(bot, args):
    sym = _ticker(args[0]) if args else None
    if not sym:
        return "Uso: /resultados NVDA"
    r = skills.analyst([sym])
    if not r.data:
        return "Analyst no disponible: %s" % (r.stderr.strip()[:300] or "sin datos")
    doc = r.data
    if isinstance(doc, list):
        doc = doc[0] if doc else {}
    res = (doc or {}).get("result") or {}
    rows = res.get("rows") or []
    if not rows:
        return "Sin datos XBRL para %s." % sym
    c = rows[0]
    return ("<b>Resultados %s</b> · %s\nPeriodo %s (%s), presentado %s\n"
            "Ingresos %s (%s%% interanual)\nEPS diluido %s · margen bruto %s%%\n"
            "Es el ultimo trimestre, no una previsión.") % (
        sym, res.get("entity") or sym, c.get("fiscal") or c.get("end") or "n/d",
        c.get("form") or "n/d", c.get("filed") or "n/d",
        _fmt(c.get("revenue"), 0), _fmt(c.get("revenue_yoy"), 1),
        _fmt(c.get("eps_diluted"), 2), _fmt(c.get("gross_margin"), 1))


def c_pelosi(bot, args):
    r = skills.pelosi_new(read=True)
    doc = r.data or {}
    items = doc.get("new") or doc.get("filings") or []
    if not items:
        return "Sin PTR nuevos de Pelosi. (Contexto, nunca senal: son publicos y llegan hasta 45 dias tarde.)"
    lines = ["<b>Pelosi · PTR nuevos</b>"]
    for it in items[:6]:
        lines.append("  %s %s" % (it.get("filed") or it.get("date"), (it.get("title") or "")[:100]))
    lines.append("Contexto, nunca senal.")
    return "\n".join(lines)


def c_apertura(bot, args):
    sym = _ticker(args[0]) if args else None
    if not sym:
        return "Uso: /apertura NVDA"
    res = apertura.analizar(sym)
    return apertura.bloque_texto(res)


def c_mercados(bot, args):
    sym = _ticker(args[0]) if args else None
    us = sym or "NVDA"
    eu = {"NVDA": "NVD.DE", "TSLA": "TL0.DE", "AAPL": "APC.DE", "MSFT": "MSF.DE", "AMZN": "AMZ.DE",
          "GOOGL": "ABEA.DE", "META": "FB2A.DE", "AMD": "AMD.DE"}.get(us)
    if not eu:
        return "Sin equivalencia europea conocida para %s. Uso EE. UU." % us
    try:
        r = mercado.comparar(us, eu)
    except Exception as exc:  # noqa: BLE001
        return ("No se pudo comparar %s con %s: %s.\n"
                "Yahoo no siempre da barras intradia de la plaza europea. Usa /elegir %s y "
                "/apertura %s para el analisis de EE. UU.; la comparacion de mercado no esta disponible."
                % (us, eu, str(exc)[:160], us, us))
    return "\n".join(mercado.recomendacion(r))


def c_vigilar(bot, args):
    cfgd = cfg.config()
    watch = cfgd.get("watch") or []
    lines = ["<b>Vigilados</b>"]
    for s in watch:
        try:
            q = datos.quote(s)
            lines.append("  %s %s USD · dato de %s (%ss)" % (s, _fmt(q["price"]), q["data_time"], q["age_seconds"]))
        except Exception as exc:
            lines.append("  %s sin datos (%s)" % (s, exc))
    return "\n".join(lines)


def c_descartadas(bot, args):
    hoy = zt.madrid().date().isoformat()
    evs = [e for e in diario.read_all() if e.get("event") == "evaluacion"
           and e.get("ts_madrid", "").startswith(hoy) and e.get("veredicto") != "SEÑAL A"]
    if not evs:
        return "Sin evaluaciones descartadas hoy."
    lines = ["<b>Descartadas / vigilar hoy</b>"]
    for e in evs[-10:]:
        lines.append("  %s %s: %s" % (e.get("symbol"), e.get("veredicto"),
                                      "; ".join(e.get("motivos") or [])[:160]))
    return "\n".join(lines)


def c_posiciones(bot, args):
    ab = posiciones.abiertas()
    if not ab:
        return "Sin posiciones abiertas registradas. Usa /entre NVDA 155.20 8 para registrar una."
    lines = ["<b>Posiciones abiertas</b>"]
    hoy = zt.madrid().date().isoformat()
    for p in ab:
        desde = (p.get("abierta_madrid") or "")[:10]
        overnight = " · ⚠️ overnight (fuera del plan intradía)" if desde and desde < hoy else ""
        lines.append("  %s %s acc desde %s · stop %s · objetivo %s%s" % (
            p["symbol"], _qty(p["qty"]), _fmt(p["entrada"]), _fmt(p.get("stop")),
            _fmt(p.get("target")), overnight))
    return "\n".join(lines)


def c_entre(bot, args):
    if not 3 <= len(args) <= 5:
        return "Uso: /entre NVDA 155.20 8 [stop] [objetivo]"
    sym = _ticker(args[0])
    price = texto.safe_float(args[1], 0.0001, 1e7)
    qty = texto.safe_float(args[2], 0.0001, 1e6)
    stop = texto.safe_float(args[3], 0.0001, 1e7) if len(args) > 3 else None
    target = texto.safe_float(args[4], 0.0001, 1e7) if len(args) > 4 else None
    if not sym or price is None or qty is None:
        return "Uso: /entre NVDA 155.20 8 [stop] [objetivo]"
    if posiciones.abierta_de(sym):
        return ("Ya hay una posicion abierta en %s. Cierrala o reduce con /sali antes de abrir otra. "
                "No se promedian posiciones a ciegas." % sym)
    if stop is not None and stop >= price:
        return "El stop (%s) tiene que estar por debajo de la entrada (%s)." % (stop, price)
    if target is not None and target <= price:
        return "El objetivo (%s) tiene que estar por encima de la entrada (%s)." % (target, price)

    cfgd = cfg.config()
    plan = cfg.read_json(cfg.TRADER / "plan.json", {}) or {}
    hoy_ny = zt.ny().date().isoformat()
    if plan.get("symbol") != sym or (plan.get("date") and str(plan.get("date"))[:10] != hoy_ny):
        plan = {}
    if stop is None:
        stop = plan.get("stop")
    if target is None:
        target = plan.get("target")

    pos = posiciones.abrir(sym, price, qty, stop, target, nota="telegram", plan=plan)
    lineas = ["Registrada: %s %s acc a %s. Stop %s, objetivo %s." % (
        sym, _qty(pos["qty"]), _fmt(pos["entrada"]), _fmt(pos.get("stop")), _fmt(pos.get("target")))]
    if plan:
        lineas.append("Plan de referencia: entrada %s · deslizamiento %+.2f USD/acc." % (
            _fmt(plan.get("entry")), pos.get("deslizamiento_entrada") or 0))

    riesgo_real = float(pos.get("riesgo_por_accion") or 0) * float(pos["qty"])
    tope_op = float(cfgd.get("max_loss_per_trade_usd") or 50)
    if riesgo_real > tope_op + 1e-6:
        lineas.append("AVISO: riesgo real al stop %.2f USD supera el tope por operacion de %.2f." % (
            riesgo_real, tope_op))
    elif plan and float(plan.get("risk_per_share") or 0) * float(pos["qty"]):
        plan_risk = float(plan.get("risk_per_share") or 0) * float(pos["qty"])
        if riesgo_real > plan_risk + 1e-6:
            lineas.append("Riesgo real al stop %.2f USD (el plan decia %.2f por el deslizamiento)." % (
                riesgo_real, plan_risk))

    if pos.get("alert_ids"):
        lineas.append("Avisos armados: %s. Solo hoy (fecha de Nueva York)." % ", ".join(
            "stop %s" % _fmt(pos.get("stop")) if x.endswith("-stop") else "objetivo %s" % _fmt(pos.get("target"))
            for x in pos["alert_ids"]))
    else:
        lineas.append("Avisos: NO armados (%s). Revisa el nivel a mano." % (
            pos.get("alert_error") or "sin stop/objetivo"))

    refs = referencias.get(sym)
    if refs:
        lineas.append("Referencias: " + " · ".join(
            "%s %s %s" % (r["source"], _fmt(r["price"]), r["currency"]) for r in refs))
        for r in refs:
            diff = (float(price) - float(r["price"])) / float(r["price"]) * 100.0
            if abs(diff) > 0.5:
                lineas.append("AVISO: tu fill %s está %.2f%% respecto a %s (%s). Revisa venue/divisa." % (
                    _fmt(price), diff, r["source"], _fmt(r["price"])))

    # limites manuales: se avisan, no se bloquean (Javier opera a mano)
    tope = float(cfgd.get("max_daily_loss_usd") or 150)
    comprometido = posiciones.riesgo_comprometido()
    if comprometido > tope:
        lineas.append("AVISO: riesgo comprometido %.2f USD supera el tope diario de %.2f." % (
            comprometido, tope))
    hoy = zt.madrid().date().isoformat()
    entradas = len([p for p in posiciones.hoy() if (p.get("abierta_madrid") or "").startswith(hoy)])
    if entradas >= int(cfgd.get("max_trades_per_day") or 3):
        lineas.append("AVISO: %d entradas hoy (limite %s). Una mas seria fuera de reglas." % (
            entradas, cfgd.get("max_trades_per_day")))

    a, ult = _veredicto_hoy(sym)
    if a:
        lineas.append("Estado: SEÑAL A vigente hoy desde las %s." % (a.get("ts_madrid") or "")[11:16])
    else:
        lineas.append("Estado: FUERA DE SEÑAL A. Registrada como ejecucion manual, no como señal.")
        if ult:
            lineas.append("Ultima evaluacion de hoy: %s." % ult.get("veredicto"))
    return "\n".join(lineas)


def c_sali(bot, args):
    if len(args) < 2:
        return "Uso: /sali NVDA 156.40 [acciones]  (sin acciones = cierra todo)"
    sym = _ticker(args[0])
    price = texto.safe_float(args[1], 0.0001, 1e7)
    qty = texto.safe_float(args[2], 0.0001, 1e6) if len(args) > 2 else None
    if not sym or price is None:
        return "Uso: /sali NVDA 156.40 [acciones]"
    pos = posiciones.cerrar(sym, price, qty=qty, motivo="manual")
    if not pos:
        return "No hay posicion abierta en %s." % sym
    if pos.get("parcial"):
        return ("Cierre parcial de %s: %s acc a %s, PnL bruto %+.2f USD (%s R). Quedan %s acc; "
                "stop %s y objetivo %s siguen armados. No descuenta comisiones ni FX." % (
                    sym, _qty(pos["qty_cerrada"]), _fmt(price), pos["pnl_usd"], pos.get("R"),
                    _qty(pos.get("restante")), _fmt(pos.get("stop")), _fmt(pos.get("target"))))
    return ("Cerrada %s: %s acc a %s, PnL bruto %+.2f USD (%s R). Alertas de stop y objetivo "
            "desarmadas. No descuenta comisiones ni FX." % (
        sym, _qty(pos["qty_cerrada"]), _fmt(price), pos["pnl_usd"], pos.get("R")))


def c_pnl(bot, args):
    p = posiciones.pnl()
    st = registro.stats()
    return ("<b>PnL</b>\nPosiciones a mano: %d cerradas, %+.2f USD bruto, %d ganadoras / %d perdedoras\n"
            "Señales papel: %d cerradas, %d objetivos, %d stops, R medio %+.2f\n"
            "El PnL a mano es bruto: no descuenta comisiones ni FX. El aviso de cada señal trae el coste.") % (
        p["operaciones"], p["pnl_usd"], p["ganadoras"], p["perdedoras"],
        st["cerradas"], st["objetivos"], st["stops"], st["r_medio"])


def c_diario(bot, args):
    hoy = zt.madrid().date().isoformat()
    rows = [e for e in diario.read_all() if e.get("ts_madrid", "").startswith(hoy)]
    if not rows:
        return "Sin eventos hoy."
    lines = ["<b>Diario de hoy</b> (%d eventos)" % len(rows)]
    for e in rows[-15:]:
        detalle = e.get("cmd") or e.get("symbol") or e.get("name") or e.get("where") or ""
        lines.append("  %s %s %s" % (e.get("ts_madrid", "")[11:16], e.get("event"),
                                     str(detalle)[:40]))
    return "\n".join(lines)


def c_registro(bot, args):
    st = registro.stats()
    freno, motivo = registro.freno_activo()
    sigs = registro.all_signals()[-6:]
    lines = ["<b>Registro vivo</b>",
             "%d señales, %d abiertas, %d cerradas (%d objetivos, %d stops), R medio %+.2f" % (
                 st["total"], st["abiertas"], st["cerradas"], st["objetivos"], st["stops"], st["r_medio"]),
             "Freno: %s (%s)" % ("ACTIVO" if freno else "no", motivo)]
    for s in sigs:
        lines.append("  %s %s %s %s" % (s.get("ts_madrid", "")[:16], s["symbol"], s["estado"], s.get("R")))
    lines.append(criterios.registro_libre(st))
    return "\n".join(lines)


def c_pausa(bot, args):
    set_pausa(True, "desde telegram")
    return "Pausado: no se envian SEÑAL A nuevas. El orquestador sigue recogiendo datos."


def c_reanudar(bot, args):
    set_pausa(False, "desde telegram")
    return "Reanudado."


def c_chuleta(bot, args):
    """Chuleta estatica para el movil: comandos, stops, objetivos y escenarios."""
    return (
        "<b>CHULETA · operar con el bot</b>\n\n"
        "<b>1. Mirar</b>\n"
        "/posiciones · que tengo y a que precio\n"
        "/guia · que hago ahora, con numeros\n"
        "/alertas · que niveles vigila hoy\n"
        "/precios T · Yahoo + CNBC + Finnhub + tu referencia\n"
        "/elegir T · analisis completo de un valor\n"
        "/hoy · lista ORB y rupturas\n"
        "/resumen · informe del dia\n\n"
        "<b>2. Registrar</b>\n"
        "/entre T fill cantidad stop objetivo\n"
        "  fill = precio del ticket (no la ficha)\n"
        "  cantidad = acciones llenadas\n"
        "  stop = nivel que invalida la compra\n"
        "  objetivo = nivel de beneficio\n"
        "/sali T fill [cantidad] · cerrar todo o parte\n"
        "/stop T precio · mover stop y rearmar aviso\n"
        "/vender T precio · mover objetivo y rearmar aviso\n\n"
        "<b>3. Como fijar el stop</b>\n"
        "- Break-even neto = entrada + costes / cantidad.\n"
        "  Con 7 acciones y 8,80 USD: entrada + 1,26.\n"
        "- Estructura: debajo del minimo del dia o de 20 dias.\n"
        "- Volatilidad: 1 ATR; si es muy ancho, reduce cantidad.\n"
        "- Trailing: solo hacia arriba. Nunca hacia abajo.\n"
        "- Stop por encima de la entrada = bloquea beneficio.\n\n"
        "<b>4. Como fijar el objetivo</b>\n"
        "- Resistencia: cierre o minimo previo (ej. 57,65; luego 60,56).\n"
        "- 2R = entrada + 2 x (entrada - stop).\n"
        "- No lo muevas sin un nivel nuevo. No persigas.\n\n"
        "<b>5. Costes (MyInvestor)</b>\n"
        "0,12% comision + 0,30% FX por lado, minimo 3 EUR.\n"
        "Con 7 acciones: ~8,80 USD ida+vuelta.\n"
        "Break-even = entrada + 8,80 / 7.\n"
        "Con pocas acciones, las comisiones mandan: mejor una venta que tres parciales.\n\n"
        "<b>6. Si llega SEÑAL A</b>\n"
        "1. Lee VEREDICTO: comprar solo si el precio esta entre stop y max.\n"
        "2. MyInvestor: LIMITADA, cantidad y precio del mensaje, validez DIA.\n"
        "3. Fill: /entre T [fill] cantidad stop objetivo.\n"
        "4. MyInvestor: stop-loss cantidad a stop, validez DIA.\n"
        "5. Opcional: venta limitada al objetivo; si pones las dos, cancela la que sobre.\n"
        "6. Si no puedes actuar: no compres. No persigas.\n\n"
        "<b>7. Si tienes posicion (CRCL)</b>\n"
        "- Sube: puedes subir el stop; nunca bajarlo.\n"
        "- Toca objetivo: vende limitada; /sali T [fill].\n"
        "- Toca stop: vende; /sali T [fill].\n"
        "- 21:55: flat; vende al bid, cancela todo, /sali.\n"
        "- Overnight: rearma /stop y /vender manana.\n\n"
        "<b>8. Avisos</b>\n"
        "- STOP: vende, cancela ordenes, /sali.\n"
        "- OBJETIVO: vende limitada, cancela stop, /sali.\n"
        "- Proximidad: no hagas nada; solo avisa.\n"
        "- Flat 21:55: cierra.\n"
        "- Informe 22:00: automatico.\n\n"
        "<b>9. Fuentes</b>\n"
        "Yahoo + CNBC + Finnhub. /precios muestra las tres.\n"
        "Si difieren mas de 0,5%: no se envia señal y te avisa con los valores.\n"
        "El fill del ticket es la verdad; la ficha de MyInvestor puede ir con retraso.\n\n"
        "<b>10. Reglas</b>\n"
        "Sin SEÑAL A no se compra. No a mercado. No promediar. No mover stop abajo. No mantener de noche.\n"
        "Si dudas: /guia. Si no entiendes: /ensenar concepto."
    )


def c_ayuda(bot, args):
    return ("<b>Comandos</b>\n"
            "<b>Lo del dia:</b> /hoy · /ganadores [N] · /seguir [N] · /incluir T · /evaluar [N] · /elegir N|T · /ahora · /resumen · /briefing\n"
            "<b>Senales:</b> /explica [T] · /porque [T] · /descartadas · /registro\n"
            "<b>Analisis:</b> /ticker T · /plan T · /tm T · /tamano T · /risk · /noticias T · /resultados T\n"
            "<b>Operar a mano:</b> /entre T precio cantidad [stop] [objetivo] · /sali T precio [acciones] · "
            "/vender T precio · /stop T precio · /posiciones · /pnl\n"
            "<b>Guia:</b> /chuleta · comandos, stops y objetivos · /guia · qué hacer ahora, paso a paso, con la posición real\n"
            "<b>Pre/post:</b> /pre T · /post T · radar con run/prepost.py --radar\n"
            "<b>Niveles:</b> /nivel · /nivel T <stop> <objetivo> · /nivel_quitar T\n"
            "<b>Tesis:</b> /tesis T · /tesis T aguantar · /tesis T liberar\n"
            "<b>RAW:</b> /raw T (primera vela de NY, 09:30 ET)\n"
            "<b>Sistema:</b> /estado · /reloj · /scan [T] · /vigila T · /dejar T · /vigilar · "
            "/alertas · /alerta T precio · /precios T · /ref T precio fuente · /apertura T · /mercados T · /pelosi · /ticket · /diario\n"
            "<b>Control:</b> /pausa · /reanudar · /ensenar concepto · /ayuda\n"
            "Tambien entiendo frases: \"que esta pasando\", \"que hago ahora\", \"ya entre en NVDA a 142,5 con 8\", "
            "\"he salido de NVDA a 156\", \"explicame esta senal\", \"por que no hay senales\", "
            "\"preparame la apertura\", \"ensename el ORB\", \"vende NVDA a 160\", \"stop de NVDA en 154\", "
            "\"que ganadores hay\", \"vigila los ganadores\", \"evalua los ganadores\".")


def _doc_orb():
    """Ultimo escaneo ORB de hoy (o None)."""
    hoy = zt.madrid().date().isoformat()
    doc = cfg.read_json(cfg.STATE / "orb.json", None) or {}
    if (doc.get("as_of") or "").startswith(hoy):
        return doc
    art = cfg.read_json(cfg.STATE / "scan_orb.json", None) or {}
    if (art.get("as_of") or "").startswith(hoy):
        return art
    return None


def _tabla_hoy(limite=10):
    """(lineas, filas, texto_manana). Filas = dicts con symbol, hora, rango, ruptura."""
    hoy = zt.madrid().date().isoformat()
    scan = cfg.read_json(cfg.STATE / "scan_daily.json", None) or {}
    orb = _doc_orb()
    filas, lineas = [], []
    if orb:
        hits = orb.get("hits") or []
        lineas.append("<b>HOY · %s</b>" % zt.short_stamp())
        lineas.append("Rango 9:30-9:45 ET · %s graficos usables · %s candidatos · %d rupturas" % (
            orb.get("scanned"), orb.get("unconfirmed") and "parcial" or "todos", len(hits)))
        if not hits:
            lineas.append("Ninguna ruptura todavia. No se hace nada hasta que haya una.")
            return lineas, filas, _lectura_manana(scan, orb, 0)
        lineas.append("")
        lineas.append("<code>#  Hora   Valor  Rango apertura      Ruptura   Ahora    vs rango</code>")
        for i, h in enumerate(hits[:limite], 1):
            sym = h.get("symbol")
            ahora = None
            try:
                ahora = datos.quote(sym)["price"]
            except Exception:
                pass
            filas.append({"n": i, "symbol": sym, "hora": h.get("at"),
                          "or_low": h.get("or_low"), "or_high": h.get("or_high"),
                          "ruptura": h.get("price"), "ahora": ahora})
            lineas.append("<code>%-2d %-6s %-6s %7.2f - %-7.2f %8.2f %8s %+7.2f%%</code>" % (
                i, h.get("at", ""), sym, float(h.get("or_low") or 0), float(h.get("or_high") or 0),
                float(h.get("price") or 0),
                ("%.2f" % ahora) if ahora else "n/d",
                ((ahora / float(h.get("price")) - 1) * 100) if ahora else 0))
    else:
        hits = scan.get("hits") or []
        lineas.append("<b>HOY · %s</b>" % zt.short_stamp())
        lineas.append("Aun no hay rango de apertura (el mercado abre a las 15:30 Madrid).")
        lineas.append("Candidatos del premarket (scan de las %s): %d" % (
            scan.get("as_of") or "n/d", len(hits)))
        if hits:
            lineas.append("")
            lineas.append("<code>#  Valor   Precio   Setups</code>")
            for i, h in enumerate(hits[:limite], 1):
                filas.append({"n": i, "symbol": h.get("symbol"), "hora": "-",
                              "or_low": None, "or_high": None,
                              "ruptura": h.get("price"), "ahora": h.get("price")})
                lineas.append("<code>%-2d %-6s %8.2f  %s</code>" % (
                    i, h.get("symbol"), float(h.get("price") or 0), ", ".join(h.get("setups") or [])))
    lineas.append("")
    lineas.append("Para el analisis completo de uno: <b>/elegir 1</b> (o el numero que sea).")
    return lineas, filas, _lectura_manana(scan, orb, len(filas))


def _lectura_manana(scan, orb, n_filas):
    """Parrafo deterministico: lo que dicen los numeros, sin adjetivos de mas."""
    scan = scan or {}
    partes = []
    if scan:
        partes.append("Premarket: de %s valores, %s pasaron liquidez y %d dieron setup." % (
            scan.get("universe"), scan.get("scanned"), len(scan.get("hits") or [])))
    if orb:
        usables = orb.get("scanned") or 0
        hits = len(orb.get("hits") or [])
        pct = (100.0 * hits / usables) if usables else 0
        partes.append("Rango de apertura: %d de %s graficos usables rompieron (%.1f%%)." % (
            hits, usables, pct))
        if hits and usables:
            if pct >= 50:
                partes.append("Mañana fuerte: mas de la mitad rompio el rango. Ojo, eso tambien "
                              "significa que muchas rupturas ya estan lejos de su entrada.")
            elif pct <= 15:
                partes.append("Mañana debil: pocas rupturas. Es normal que el sistema no encuentre nada.")
            else:
                partes.append("Mañana mixta: ni euforia ni sequia.")
    if not partes:
        partes.append("Sin datos de scanner todavia. Se generan a las 13:00.")
    return " ".join(partes)


def c_hoy(bot, args):
    lineas, filas, manana = _tabla_hoy()
    out = list(lineas)
    out.append("")
    out.append("<b>Lectura de la mañana</b>")
    out.append(manana)
    out.append("")
    out.append("Candidato no es compra: cada uno pasa por noticias, plan, Time Machine y risk.")
    return "\n".join(out)


def c_ahora(bot, args):
    return ahora.texto()


def _prepost_cmd(modo, args):
    if args:
        sym = _ticker(args[0])
        if not sym:
            return "Uso: /%s NVDA" % modo
        try:
            r = prepost.resumen(sym, modo)
        except Exception as exc:
            return "No disponible: %s" % str(exc)[:120]
        return prepost.texto([r], modo)
    filas = prepost.cargar(cfg.STATE / modo / "radar.json")
    return prepost.texto(filas, modo)


def c_pre(bot, args):
    return _prepost_cmd("pre", args)


def c_post(bot, args):
    return _prepost_cmd("post", args)


def c_nivel(bot, args):
    """Niveles manuales: /nivel, /nivel TLK, /nivel TLK 11.20 12.38."""
    if not args:
        return niveles.texto()
    sym = _ticker(args[0])
    if not sym:
        return "Uso: /nivel TLK 11.20 12.38 (stop y objetivo)"
    if len(args) == 1:
        filas = [f for f in niveles.todos() if f.get("symbol") == sym]
        if not filas:
            return "Sin nivel para %s. Uso: /nivel %s <stop> <objetivo>" % (sym, sym)
        return niveles.texto().replace("Niveles manuales", "Nivel %s" % sym)
    try:
        stop = float(str(args[1]).replace(",", "."))
    except ValueError:
        return "El stop debe ser un numero. Uso: /nivel %s <stop> <objetivo>" % sym
    target = None
    if len(args) > 2:
        try:
            target = float(str(args[2]).replace(",", "."))
        except ValueError:
            return "El objetivo debe ser un numero."
    try:
        fila = niveles.poner(sym, stop=stop, target=target)
    except ValueError as exc:
        return "No se pudo guardar: %s" % exc
    return "Nivel guardado: %s stop %.2f%s. El vigilante lo revisa cada 30 s." % (
        sym, fila["stop"],
        (" · objetivo %.2f" % fila["target"]) if fila.get("target") else "")


def c_salir_nivel(bot, args):
    if not args:
        return "Uso: /nivel_quitar TLK"
    sym = _ticker(args[0])
    if not sym:
        return "Uso: /nivel_quitar TLK"
    return ("Nivel de %s borrado." % sym) if niveles.quitar(sym) else ("No habia nivel de %s." % sym)


def c_tesis(bot, args):
    """Tesis de aguante: /tesis NVDA, /tesis NVDA aguantar, /tesis NVDA liberar."""
    if not args:
        return "Uso: /tesis NVDA · /tesis NVDA aguantar · /tesis NVDA liberar"
    sym = _ticker(args[0])
    if not sym:
        return "Uso: /tesis NVDA"
    if len(args) > 1:
        accion = str(args[1]).lower()
        if accion in ("aguantar", "mantener", "hold"):
            tesis.marcar(sym, True)
        elif accion in ("liberar", "quitar", "normal"):
            tesis.marcar(sym, False)
        else:
            return "Accion no valida. Usa aguantar o liberar."
    return tesis.texto(sym)


def c_research(bot, args):
    """Mesa de research: /research NVDA."""
    if not args:
        return "Uso: /research NVDA"
    sym = _ticker(args[0])
    if not sym:
        return "Uso: /research NVDA"
    try:
        return research.texto(sym)
    except Exception as exc:
        return "Sin datos: %s" % str(exc)[:120]


def c_raw(bot, args):
    """Primera vela de la sesion (RAW): /raw NVDA · /raw SAP.DE eu."""
    if not args:
        return "Uso: /raw NVDA · /raw SAP.DE eu"
    sym = str(args[0]).strip().upper()
    if not re.match(r"^[A-Z0-9]{1,6}(\.[A-Z]{1,3})?$", sym):
        return "Uso: /raw NVDA · /raw SAP.DE eu"
    mercado = "us"
    if len(args) > 1 and str(args[1]).lower() in ("eu", "europa", "xetra"):
        mercado = "eu"
    try:
        fila = raw.ultima(raw.barras(sym), mercado)
    except Exception as exc:
        return "Sin datos: %s" % str(exc)[:120]
    return raw.texto_senal(fila, sym, mercado, raw.plan(fila, 50.0, max_notional=10000.0))


def c_guia(bot, args):
    """Que hacer ahora, con los niveles reales y las ordenes exactas."""
    now = zt.madrid()
    clave, titulo, hace, espera, ignora = ahora.fase(now)
    ev, when = ahora.siguiente_evento(now)
    out = ["<b>Guia</b> · %s · %s" % (zt.short_stamp(now), titulo)]
    ab = posiciones.abiertas()
    if not ab:
        out.append("Sin posiciones abiertas.")
        out.append("Que haces: %s" % espera)
        if ev:
            out.append("Proximo: %s a las %s (en %s)" % (
                ev, when.astimezone(zt.MADRID).strftime("%H:%M"), ahora.cuenta_atras(when, now)))
        out.append("Si llega SEÑAL A, te mando el ticket exacto. Si no, no hay nada que hacer.")
        return "\n".join(out)

    for p in ab:
        sym = p["symbol"]
        qty = float(p.get("qty") or 0)
        entry = float(p.get("entrada") or 0)
        stop = p.get("stop")
        target = p.get("target")
        out.append("")
        out.append("<b>%s</b> %s acc desde %s · stop %s · objetivo %s" % (
            sym, _qty(qty), _fmt(entry), _fmt(stop), _fmt(target)))
        px = None
        try:
            q = datos.quote(sym)
            px = float(q["price"])
            out.append("Ahora %s · dato de hace %ss · %s" % (
                _fmt(px), q.get("age_seconds"), q.get("exchange") or ""))
        except Exception:
            out.append("Ahora: sin dato de Yahoo.")
        cost = None
        try:
            cost = float(datos.coste_ida_vuelta_usd(qty * entry)["total_usd"])
            out.append("Coste ida+vuelta %.2f USD · break-even %s" % (cost, _fmt(entry + cost / qty)))
        except Exception:
            pass
        if px is not None:
            pnl = (px - entry) * qty
            r = ((px - entry) / (entry - float(stop))) if stop and entry > float(stop) else None
            out.append("PnL bruto %+.2f USD · %sR" % (pnl, ("%+.2f" % r) if r is not None else "n/d"))
            if stop:
                out.append("Distancia al stop %s: %+.2f USD (%.2f%% desde ahora)" % (
                    _fmt(stop), (float(stop) - px) * qty, abs(px - float(stop)) / px * 100))
            if target:
                out.append("Distancia al objetivo %s: %+.2f USD (%.2f%% desde ahora)" % (
                    _fmt(target), (float(target) - px) * qty, abs(float(target) - px) / px * 100))
            if cost is not None and stop:
                out.append("Neto si salta el stop: %+.2f USD" % ((float(stop) - entry) * qty - cost))
            if cost is not None and target:
                out.append("Neto si toca el objetivo: %+.2f USD" % ((float(target) - entry) * qty - cost))
        if clave in ("ventana", "ultimos30"):
            out.append("Ahora: nada hasta que toque un nivel.")
            if stop:
                out.append("Si toca %s: vende %s (o deja el stop-loss), cancela el stop y /sali %s [fill]." % (
                    _fmt(stop), _qty(qty), sym))
            if target:
                out.append("Si toca %s: vende %s con limitada %s, cancela el stop y /sali %s [fill]." % (
                    _fmt(target), _qty(qty), _fmt(target), sym))
            out.append("A las 21:55: cancela el stop, vende al bid y /sali %s [fill]." % sym)
        elif clave == "cierre":
            out.append("Flat by close: cierra ya. Cancela el stop y /sali %s [fill]." % sym)
        elif clave == "post":
            out.append("Mercado cerrado: posicion overnight. Rearma el stop mañana; el de hoy caduco.")
            if stop:
                out.append("Mañana: /stop %s %s para volver a vigilarlo." % (sym, _fmt(stop)))
            if target:
                out.append("Mañana: /vender %s %s para el objetivo." % (sym, _fmt(target)))
            out.append("Riesgo overnight: un hueco de apertura puede saltarse el stop.")
        else:
            out.append("Fuera de la ventana: %s" % espera)
    if ev:
        out.append("")
        out.append("Proximo: %s a las %s (en %s)" % (
            ev, when.astimezone(zt.MADRID).strftime("%H:%M"), ahora.cuenta_atras(when, now)))
    return "\n".join(out)


def c_explica(bot, args):
    """Explica la ultima senal o evaluacion de un valor en lenguaje llano."""
    hoy = zt.madrid().date().isoformat()
    sym = _ticker(args[0]) if args else None
    evs = [e for e in diario.read_all() if e.get("event") == "evaluacion"
           and e.get("ts_madrid", "").startswith(hoy)]
    if sym:
        evs = [e for e in evs if e.get("symbol") == sym]
    if not evs:
        return ("No hay ninguna evaluacion hoy%s. El sistema evalua a partir de las 15:50."
                % (" para %s" % sym if sym else ""))
    e = evs[-1]
    plan = e.get("plan") or {}
    n = e.get("numbers") or {}
    lines = ["<b>%s · %s</b> (%s)" % (e.get("symbol"), e.get("veredicto"), e.get("ts_madrid", "")[11:16])]
    lines.append("Que paso: %s" % (e.get("setup_detail") or "el setup se disparo y se ejecuto la cadena completa"))
    if plan:
        lines.append("Entrada %s · stop %s · objetivo %s (%sR) · fuera a las %s ET" % (
            _fmt(plan.get("entry")), _fmt(plan.get("stop")), _fmt(plan.get("target")),
            plan.get("target_r"), plan.get("flat_by")))
    if n.get("p_target_mc") is not None:
        lines.append("Time Machine: objetivo %s%%, stop %s%% (%s replays). Historico: %s disparos, "
                     "%s objetivos, %s stops." % (
                         _fmt(100 * n["p_target_mc"], 1), _fmt(100 * n["p_stop_mc"], 1),
                         "10.000", n.get("hist_n"), n.get("hist_target"), n.get("hist_stop")))
    if n.get("ev") is not None:
        lines.append("Valor esperado tras costes: %s R (coste %s R)." % (_fmt(n["ev"], 3), _fmt(n.get("cost_r"), 3)))
    if e.get("motivos"):
        lines.append("Motivos: " + "; ".join(e["motivos"])[:600])
    lines.append("Que la invalida: que el precio pierda el stop, que el dato deje de ser fresco "
                 "o que el EV deje de ser positivo. No se mueve el stop.")
    lines.append("Muestra: %s disparos historicos. Es una frecuencia, no una promesa." % (n.get("hist_n") or "n/d"))
    return "\n".join(lines)


def c_porque(bot, args):
    """Por que no hay senales (o por que se descarto un valor concreto)."""
    hoy = zt.madrid().date().isoformat()
    sym = _ticker(args[0]) if args else None
    evs = [e for e in diario.read_all() if e.get("event") == "evaluacion"
           and e.get("ts_madrid", "").startswith(hoy)]
    if sym:
        evs = [e for e in evs if e.get("symbol") == sym]
        if not evs:
            return "%s no se ha evaluado hoy todavia." % sym
        e = evs[-1]
        return ("<b>%s · %s</b>\n%s" % (e.get("symbol"), e.get("veredicto"),
                                        "\n".join("- " + m for m in (e.get("motivos") or ["sin motivos registrados"]))))
    if not evs:
        return ("Hoy no se ha evaluado nada todavia. El escaneo ORB empieza a las 15:50 Madrid. "
                "Antes de eso no hay senales que descartar.")
    a = [e for e in evs if e.get("veredicto") == "SEÑAL A"]
    if a:
        return ("Hoy hay %d SEÑAL A: %s. Las demas se descartaron; usa /descartadas o "
                "/porque TICKER para el detalle." % (len(a), ", ".join(e["symbol"] for e in a)))
    razones = {}
    for e in evs:
        for m in e.get("motivos") or []:
            clave = m.split(":")[0]
            razones[clave] = razones.get(clave, 0) + 1
    top = sorted(razones.items(), key=lambda kv: -kv[1])[:5]
    return ("No hay SEÑAL A. %d valores evaluados. Motivos mas frecuentes:\n%s\n"
            "No se relajan filtros para generar avisos." % (
                len(evs), "\n".join("- %s (%d veces)" % (k, v) for k, v in top)))


CONCEPTOS = {
    "orb": "ORB = ruptura del rango de apertura. Se mide el maximo y minimo de los primeros 15 minutos "
           "(9:30-9:45 ET) y se entra cuando una vela de 5 minutos CIERRA por encima del maximo.",
    "r": "R = lo que pierdes si salta el stop. Si entras a 100 con stop 98, 1R = 2 USD por accion. "
         "Todo se mide en multiplos de R para comparar operaciones de tamaños distintos.",
    "stop": "Stop = precio al que aceptas que la idea fallo y sales. En este sistema va en el punto "
            "medio del rango de apertura, redondeado hacia abajo.",
    "objetivo": "Objetivo = precio al que recoges. Por politica 2R: el doble de lo que arriesgas.",
    "time machine": "Time Machine = simulacion de 10.000 repeticiones del resto de la sesion con las "
                    "ultimas 59 sesiones del valor, mas la misma regla sobre el historico real. "
                    "Devuelve frecuencias, no probabilidades de ganar.",
    "wilson": "Wilson = intervalo de confianza al 95 % de una tasa. Con 33 disparos y 13 aciertos, "
              "la tasa es 39 % pero el intervalo real va del 25 % al 56 %: por eso no se concluye nada.",
    "ev": "EV = valor esperado en R despues de costes. Si es negativo, la operacion pierde dinero de media "
          "aunque a veces gane.",
    "spread": "Spread = diferencia entre lo que pides y lo que ofrecen. Aqui se usa un proxy: el rango "
              "medio de las velas de 5 minutos, porque Yahoo no da bid-ask gratis.",
    "flat by close": "Flat by close = cerrar todo antes del cierre. Aqui a las 15:55 ET (21:55 Madrid), "
                     "porque no se mantiene nada overnight.",
    "señal a": "SEÑAL A = el unico aviso que se envia. Exige setup, noticias limpias, plan, Time Machine "
               "a favor, historico con muestra, EV positivo tras costes, risk PASS y datos frescos.",
}


def c_ensenar(bot, args):
    clave = " ".join(args).strip().lower().replace("senal a", "señal a")
    if not clave:
        return "Uso: /ensenar orb|R|stop|objetivo|time machine|wilson|ev|spread|flat by close|señal a"
    for k, v in CONCEPTOS.items():
        if clave == k or re.search(r"\b%s\b" % re.escape(k), clave):
            extra = ""
            f = estado_vivo.foto()
            if k == "señal a":
                extra = "\nHoy: %d A, %d vigilar, %d descartadas." % (
                    f["signals"]["counts"].get("SEÑAL A", 0), f["signals"]["counts"].get("VIGILAR", 0),
                    f["signals"]["counts"].get("DESCARTADA", 0))
            if k == "wilson" and f["registro"]["cerradas"]:
                extra = "\nRegistro vivo: %d cerradas, R medio %+.2f." % (
                    f["registro"]["cerradas"], f["registro"]["r_medio"])
            return "<b>%s</b>\n%s%s" % (k.upper(), v, extra)
    return "No tengo esa explicacion. Prueba: /ensenar orb, R, stop, objetivo, time machine, wilson, ev, spread."



    """Analisis completo de un valor, contado para decidir: comprar, donde salir y si mantener."""
    out = _cadena(sym, target="2R")
    e = out.get("entry") or {}
    plan = out.get("plan") or {}
    lines = ["<b>%s</b>" % sym]
    if e.get("status") != "triggered":
        lines.append("Ahora mismo no hay disparo: %s." % (e.get("reason") or e.get("status")))
        nw = skills.news([sym], hours=24)
        adv, ern = proceso.clasificar_noticias(nw.data, sym)
        if adv:
            lines.append("Noticias adversas: %s" % adv[0])
        if ern:
            lines.append("Resultados cerca: %s" % ern[0])
        lines.append("Sin disparo no se compra. Se espera.")
        return "\n".join(lines)

    orr = e.get("opening_range") or {}
    lines.append("Ha roto el rango %s-%s y cerro en %s a las %s." % (
        _fmt(orr.get("low")), _fmt(orr.get("high")), _fmt(plan.get("entry")), e.get("time")))
    lines.append("Comprarias en %s, stop en %s, objetivo %s (%sR)." % (
        _fmt(plan.get("entry")), _fmt(plan.get("stop")), _fmt(plan.get("target")), plan.get("target_r")))
    b = out.get("budget") or {}
    q = (b.get("orders") or [b])[0] if (b.get("orders") or b.get("symbol")) else {}
    if q.get("qty"):
        lines.append("Tamano: %s acciones. Si salta el stop pierdes como maximo %s USD." % (
            q.get("qty"), _fmt((q.get("plan") or {}).get("max_loss"))))
    tm = (out.get("tm") or {}).get("mc") or {}
    hist = (out.get("tm") or {}).get("history") or {}
    if tm:
        lines.append("Time Machine: objetivo primero %s%%, stop %s%% (%s replays). Historico: "
                     "%s disparos, %s objetivo, %s stop." % (
                         _fmt(100 * (tm.get("p_target") or 0), 1), _fmt(100 * (tm.get("p_stop") or 0), 1),
                         tm.get("replays"), hist.get("triggered"), hist.get("target"), hist.get("stop")))
    r = out.get("risk") or {}
    if r.get("results"):
        lines.append("Risk: %s." % r["results"][0].get("verdict"))
    nw = skills.news([sym], hours=24)
    adv, ern = proceso.clasificar_noticias(nw.data, sym)
    lines.append("Noticias: %s" % (adv[0] if adv else "sin adversas"))
    lines.append("Resultados: %s" % (ern[0] if ern else "sin senal de resultados hoy/manana"))
    lines.append("")
    lines.append("<b>Que haria</b>")
    lines.append("Comprar solo si aceptas el plan tal cual: entrada %s, stop %s, objetivo %s." % (
        _fmt(plan.get("entry")), _fmt(plan.get("stop")), _fmt(plan.get("target"))))
    lines.append("Vender en el objetivo, en el stop, o a las %s ET como muy tarde." % plan.get("flat_by"))
    lines.append("Al final del dia NO se mantiene: se cierra todo. Es una regla, no una opinion.")
    lines.append("Nada de esto es una orden ni una promesa: son frecuencias y niveles calculados.")
    return "\n".join(lines)


def c_ganadores(bot, args):
    """Los que mas suben, con filtro de liquidez. No es una recomendacion."""
    n = 15
    if args and str(args[0]).isdigit():
        n = max(3, min(25, int(args[0])))
    abierto = False
    start, end, _ = calendario.session_madrid(zt.madrid().date())
    if start and start <= zt.madrid() <= end:
        abierto = True
    doc = ganadores.intradia(top=n) if abierto else ganadores.premarket(top=n)
    txt = ganadores.texto(doc, top=n)
    hoy = zt.madrid().date().isoformat()
    evs = {e.get("symbol"): e for e in diario.read_all()
           if e.get("event") == "evaluacion" and (e.get("ts_madrid") or "").startswith(hoy)}
    vistos = [(f["symbol"], evs[f["symbol"]]) for f in (doc.get("filas") or []) if f["symbol"] in evs]
    if vistos:
        txt += "\n\nYa evaluados hoy (cadena completa):"
        for sym, e in vistos[:6]:
            txt += "\n  %s · %s" % (sym, e.get("veredicto"))
        txt += "\nDetalle: /elegir TICKER"
    else:
        txt += "\n\nNinguno de estos esta evaluado todavia hoy. /evaluar 3 lo hace ahora."
    return "<pre>" + txt + "</pre>"


def _veredicto_hoy(sym):
    """(ultima SEÑAL A de hoy, ultima evaluacion de hoy) para un valor."""
    hoy = zt.madrid().date().isoformat()
    evs = [e for e in diario.read_all()
           if e.get("event") == "evaluacion" and (e.get("ts_madrid") or "").startswith(hoy)
           and e.get("symbol") == sym]
    a = [e for e in evs if e.get("veredicto") == "SEÑAL A"]
    return (a[-1] if a else None), (evs[-1] if evs else None)


def _aviso_xetra(sym):
    return ("%s es un ticker europeo (Xetra). El motor del skill es de Nueva York y no acepta "
            "sufijos: la señal se calcula sobre el ticker de EE. UU. (NVDA). Para tu posicion en "
            "Xetra usa /entre %s precio acciones y sus alertas; no se mezclan niveles USD y EUR." % (sym, sym))


def _analisis_natural(symbol):
    """Cadena completa en sandbox + criterios. Sin enviar, sin tocar el plan vivo."""
    sym = _ticker(symbol)
    if not sym:
        return "Ticker no valido. Uso: /elegir NVDA"
    if alertas.es_xetra(sym):
        return _aviso_xetra(sym)
    out = _cadena(sym)
    e = out.get("entry") or {}
    lines = ["<b>%s · analisis completo</b> (bajo demanda, no envia aviso)" % sym]

    if e.get("error"):
        return "\n".join(lines + ["entry.py fallo: %s" % str(e["error"])[:300]])
    if e.get("status") != "triggered":
        lines.append("Setup: %s. %s" % (e.get("status") or "sin datos", e.get("reason") or "sin detalle"))
        o = e.get("opening_range") or {}
        if o.get("high") is not None:
            lines.append("Rango de apertura: %.2f - %.2f" % (o.get("high"), o.get("low")))
        try:
            q = datos.quote(sym)
            viejo = " · dato viejo: es el ultimo cierre, no un precio en vivo" if q["age_seconds"] > 300 else ""
            lines.append("Precio ahora: %.2f (dato de hace %ss%s)" % (q["price"], q["age_seconds"], viejo))
        except datos.DataError:
            lines.append("Precio ahora: no disponible")
        try:
            nw = skills.news([sym], hours=24)
            adv, ern = proceso.clasificar_noticias(nw.data, sym)
            lines.append("Noticias: %s" % (adv[0] if adv else "sin adversas"))
            lines.append("Riesgo de resultados (proxy titular/10-Q): %s" % (
                ern[0] if ern else "sin senal hoy/manana"))
        except Exception:  # noqa: BLE001
            lines.append("Noticias: no disponible")
        ana = proceso.analyst_info(sym)
        if ana.get("filed"):
            lines.append("SEC: ultimo trimestre %s (%s), presentado %s." % (
                ana.get("fiscal") or "n/d", ana.get("form") or "n/d", ana["filed"]))
        _, ult = _veredicto_hoy(sym)
        if ult:
            lines.append("Ultima evaluacion de hoy: %s a las %s." % (
                ult.get("veredicto"), (ult.get("ts_madrid") or "")[11:16]))
        lines.append("Veredicto: <b>SIN SEÑAL</b> todavia. Sin ruptura no hay plan, tamaño ni probabilidades.")
        lines.append("Que falta: que una vela de 5 min cierre por encima del maximo del rango "
                     "(9:30-9:45 ET) dentro de la ventana de entrada.")
        return "\n".join(lines)

    plan = out.get("plan") or {}
    tm = out.get("tm") or {}
    b = out.get("budget") or {}
    orders = b.get("orders") or ([b] if b.get("symbol") else [])
    order = orders[0] if orders else {}
    r = out.get("risk") or {}
    res0 = (r.get("results") or [{}])[0]

    lines.append("Setup: TRIGGERED a las %s ET." % (e.get("time") or "n/d"))
    lines.append("Plan: entrada %s · stop %s · objetivo %s (%sR) · fuera a las %s ET." % (
        _fmt(plan.get("entry")), _fmt(plan.get("stop")), _fmt(plan.get("target")),
        plan.get("target_r"), plan.get("flat_by")))
    mc = tm.get("mc") or {}
    hist = tm.get("history") or {}
    if mc:
        lines.append("Time Machine: objetivo %s%% · stop %s%% · %s replays (seed %s)." % (
            _fmt(100 * (mc.get("p_target") or 0), 1), _fmt(100 * (mc.get("p_stop") or 0), 1),
            mc.get("replays"), mc.get("seed")))
    if hist:
        lines.append("Historico: %s disparos · %s objetivo · %s stop." % (
            hist.get("triggered"), hist.get("target"), hist.get("stop")))
    if order.get("qty"):
        lines.append("Tamaño: %s acc · perdida maxima %s USD." % (
            order.get("qty"), _fmt(order.get("max_loss") or
                                   (float(order["qty"]) * float(plan.get("risk_per_share") or 0)))))
    lines.append("Risk: %s%s." % (res0.get("verdict") or "sin datos",
                                  (" · " + "; ".join(res0.get("reasons") or [])[:200])
                                  if res0.get("reasons") else ""))
    try:
        nw = skills.news([sym], hours=24)
        adv, ern = proceso.clasificar_noticias(nw.data, sym)
        lines.append("Noticias: %s · resultados: %s." % (
            adv[0] if adv else "sin adversas", ern[0] if ern else "sin senal"))
    except Exception:  # noqa: BLE001
        lines.append("Noticias: no disponible.")

    try:
        ctx, ev = proceso.contexto_desde_cadena(sym, out)
        n = ev["numbers"]
        lines.append("Criterios: <b>%s</b> · EV %s R · coste %s R · n=%s · Wilson %s-%s%% · break-even %s%%." % (
            ev["verdict"], _fmt(n.get("ev"), 3), _fmt(n.get("cost_r"), 3), n.get("hist_n"),
            _fmt(100 * (n.get("wilson_low") or 0), 1), _fmt(100 * (n.get("wilson_high") or 0), 1),
            _fmt(100 * (n.get("break_even") or 0), 1)))
        fallos = [c for c in ev.get("reasons") or []]
        if fallos:
            lines.append("Lo que falla: " + "; ".join(fallos)[:800])
        if ctx.get("analyst", {}).get("filed"):
            lines.append("SEC: ultimo trimestre %s (%s), presentado %s." % (
                ctx["analyst"].get("fiscal") or "n/d", ctx["analyst"].get("form") or "n/d",
                ctx["analyst"]["filed"]))
    except datos.DataError as exc:
        lines.append("Criterios: no disponibles (%s)." % exc)
        ev = None

    a, ult = _veredicto_hoy(sym)
    if a:
        lines.append("Estado: <b>SEÑAL A vigente hoy</b> desde las %s. Este analisis no ha enviado nada."
                     % (a.get("ts_madrid") or "")[11:16])
    else:
        lines.append("Estado: <b>fuera de SEÑAL A</b>. No se ha enviado aviso ni se ha tocado el plan vivo.")
        if ev and ev["verdict"] == "SEÑAL A":
            lines.append("Los criterios darian SEÑAL A, pero el aviso automatico no se ha disparado "
                         "para este valor (o ya paso su ventana).")
    lines.append("Lo invalida: perder el stop, que el dato deje de ser fresco o que el EV deje de ser positivo.")
    lines.append("Muestra: %s disparos historicos. Frecuencia, no promesa." % (
        (ev or {}).get("numbers", {}).get("hist_n") or "n/d"))
    return "\n".join(lines)


def _evaluar_cadena(sym):
    """Cadena completa en sandbox y veredicto de criterios. Sin efectos secundarios."""
    try:
        out = _cadena(sym)
    except Exception as exc:  # noqa: BLE001
        return {"symbol": sym, "verdict": "ERROR", "ev": None, "detail": str(exc)[:120]}
    e = out.get("entry") or {}
    if e.get("status") != "triggered":
        return {"symbol": sym, "verdict": "SIN SEÑAL", "ev": None, "hist_n": 0,
                "detail": (e.get("reason") or e.get("status") or "sin datos")[:90]}
    try:
        ctx, ev = proceso.contexto_desde_cadena(sym, out)
    except Exception as exc:  # noqa: BLE001
        return {"symbol": sym, "verdict": "ERROR", "ev": None, "detail": str(exc)[:120]}
    n = ev["numbers"]
    return {"symbol": sym, "verdict": ev["verdict"], "ev": n.get("ev"),
            "hist_n": n.get("hist_n"), "p_target": n.get("p_target_mc"),
            "detail": (ev["reasons"][0] if ev["reasons"] else "")[:90]}


def c_evaluar(bot, args):
    """Evaluacion bajo demanda de los ganadores del dia. No envia SEÑAL A."""
    n = 3
    if args and str(args[0]).isdigit():
        n = max(1, min(5, int(args[0])))
    abierto = False
    start, end, _ = calendario.session_madrid(zt.madrid().date())
    if start and start <= zt.madrid() <= end:
        abierto = True
    doc = ganadores.intradia(top=n) if abierto else ganadores.premarket(top=n)
    filas = (doc.get("filas") or [])[:n]
    if not filas:
        return "Sin ganadores con liquidez ahora mismo. No se inventan."
    res = [_evaluar_cadena(f["symbol"]) for f in filas]
    orden = {"SEÑAL A": 0, "VIGILAR": 1, "DESCARTADA": 2, "SIN SEÑAL": 3, "ERROR": 4}
    res.sort(key=lambda x: (orden.get(x["verdict"], 9),
                            -(x["ev"] if x["ev"] is not None else -99)))
    lines = ["<b>Evaluacion bajo demanda</b> · %s · %d ganadores (de %s)" % (
        zt.madrid().strftime("%H:%M"), len(res), "hoy" if abierto else "ayer"),
        "No envia aviso ni toca el plan vivo. Solo mide.",
        "",
        "<code>#  Valor  Veredicto     EV R    n   obj MC</code>"]
    lines.append("<i>obj MC = % de simulaciones con el objetivo antes que el stop, con el plan de hoy.</i>")
    for i, r in enumerate(res, 1):
        ev_txt = "   n/d" if r.get("ev") is None else "%+6.3f" % r["ev"]
        obj = "  n/d" if r.get("p_target") is None else "%4.0f%%" % (100 * r["p_target"])
        lines.append("<code>%-2d %-6s %-12s %s %4s %s</code>" % (
            i, r["symbol"], r["verdict"], ev_txt, r.get("hist_n") or 0, obj))
    motivos = [r for r in res if r.get("detail")]
    if motivos:
        lines.append("")
        lines.append("Motivo principal:")
        for r in motivos[:3]:
            lines.append("  %s: %s" % (r["symbol"], r["detail"]))
    lines.append("")
    lines.append("Esto es el veredicto de los criterios, no una recomendacion. Si un valor "
                 "sale SEÑAL A aqui pero no llego aviso, no se opera: el aviso automatico manda.")
    lines.append("Analisis completo de uno: /elegir NVDA")
    return "\n".join(lines)


def c_incluir(bot, args):
    """Incluye un ticker concreto en la lista que escanea el ORB hoy."""
    sym = _ticker(args[0]) if args else None
    if not sym:
        return "Uso: /incluir MNSO"
    path = cfg.STATE / "orb_candidates.json"
    doc = cfg.read_json(path, {}) or {}
    syms = [h.get("symbol") for h in (doc.get("hits") or []) if h.get("symbol")]
    nuevo = sym not in syms
    if nuevo:
        syms.append(sym)
        cfg.write_json(path, {"hits": [{"symbol": s} for s in syms]})
    hoy = zt.madrid().date().isoformat()
    seg = cfg.read_json(cfg.STATE / "seguir.json", {}) or {}
    if seg.get("date") != hoy:
        seg = {"date": hoy, "symbols": []}
    if sym not in (seg.get("symbols") or []):
        seg["symbols"].append(sym)
    cfg.write_json(cfg.STATE / "seguir.json", seg)
    antes = "Añadido al escaneo ORB de hoy: %s" % sym if nuevo else "%s ya estaba en la lista ORB de hoy" % sym
    return ("%s.\nLista total: %d valores. Se escanea cada 5 min y pasa por noticias, plan, "
            "Time Machine, tamaño, risk y criterios.\n"
            "No es una compra: si rompe el rango y pasa todo, llegará como SEÑAL A.\n"
            "Si lo haces antes de las 13:00, el premarket reconstruye la lista y se pierde." % (antes, len(syms)))


def c_seguir(bot, args):
    """Anade los ganadores de hoy a la lista que escanea el ORB. No los compra."""
    n = 5
    if args and str(args[0]).isdigit():
        n = max(1, min(15, int(args[0])))
    abierto = False
    start, end, _ = calendario.session_madrid(zt.madrid().date())
    if start and start <= zt.madrid() <= end:
        abierto = True
    doc = ganadores.intradia(top=n) if abierto else ganadores.premarket(top=n)
    filas = (doc.get("filas") or [])[:n]
    if not filas:
        return "Sin ganadores con liquidez ahora mismo. No se anade nada."
    path = cfg.STATE / "orb_candidates.json"
    actual = cfg.read_json(path, {}) or {}
    syms = [h.get("symbol") for h in (actual.get("hits") or []) if h.get("symbol")]
    nuevos = []
    for f in filas:
        if f["symbol"] not in syms:
            syms.append(f["symbol"])
            nuevos.append(f["symbol"])
    cfg.write_json(path, {"hits": [{"symbol": s} for s in syms]})
    seg = cfg.read_json(cfg.STATE / "seguir.json", {}) or {}
    hoy = zt.madrid().date().isoformat()
    if seg.get("date") != hoy:
        seg = {"date": hoy, "symbols": []}
    for f in filas:
        if f["symbol"] not in seg["symbols"]:
            seg["symbols"].append(f["symbol"])
    cfg.write_json(cfg.STATE / "seguir.json", seg)
    return ("Ganadores anadidos al escaneo ORB: %s.\n"
            "Lista total: %d valores. Se escanean cada 5 min y pasan por noticias, plan, "
            "Time Machine, tamano, risk y criterios.\n"
            "No es una recomendacion ni una compra: si alguno rompe el rango y pasa todo, "
            "llegara como SEÑAL A." % (
                ", ".join(nuevos) if nuevos else "ninguno nuevo (ya estaban)",
                len(syms)))


def c_elegir(bot, args):
    if len(args) != 1:
        return "Uso: /elegir 1  (numero de /hoy o /ganadores) o /elegir NVDA"
    if _ticker(args[0]):
        return _analisis_natural(_ticker(args[0]))
    if not str(args[0]).isdigit():
        return "Uso: /elegir 1  (numero de /hoy o /ganadores) o /elegir NVDA"
    n = int(args[0])
    lineas, filas, _ = _tabla_hoy()
    if not filas:
        abierto = False
        start, end, _ = calendario.session_madrid(zt.madrid().date())
        if start and start <= zt.madrid() <= end:
            abierto = True
        doc = ganadores.intradia(top=10) if abierto else ganadores.premarket(top=10)
        filas = doc.get("filas") or []
    if not filas:
        return "No hay tabla ni ganadores con liquidez ahora mismo. Escribe /hoy o /ganadores."
    if not 1 <= n <= len(filas):
        return "Ese numero no esta en la tabla (1-%d)." % len(filas)
    sym = filas[n - 1]["symbol"]
    return _analisis_natural(sym)


def c_resumen(bot, args):
    """Lo que hay que hacer hoy, en lenguaje llano."""
    hoy = zt.madrid().date().isoformat()
    evs = [e for e in diario.read_all() if e.get("event") == "evaluacion"
           and e.get("ts_madrid", "").startswith(hoy)]
    a = [e for e in evs if e.get("veredicto") == "SEÑAL A"]
    v = [e for e in evs if e.get("veredicto") == "VIGILAR"]
    d = [e for e in evs if e.get("veredicto") == "DESCARTADA"]
    abiertas = posiciones.abiertas()
    cfgd = cfg.config()
    lines = ["<b>Resumen de hoy</b> · %s" % zt.short_stamp()]
    if not evs:
        lines.append("Todavia no se ha evaluado nada. El escaneo empieza a las 15:50 Madrid.")
    else:
        lines.append("Evaluados %d valores: %d señal A, %d vigilar, %d descartadas." % (
            len(evs), len(a), len(v), len(d)))
    if a:
        for e in a[-3:]:
            lines.append("  SEÑAL A vigente en %s (plan en el aviso enviado)." % e.get("symbol"))
    else:
        lines.append("No hay ninguna señal A. Hoy no se compra nada. Eso es un resultado, no un fallo.")
    if abiertas:
        for p in abiertas:
            lines.append("  Tienes %s %s desde %s. Stop %s, objetivo %s." % (
                p["qty"], p["symbol"], p["entrada"], p.get("stop"), p.get("target")))
        lines.append("Al cierre: vender todo. No se mantiene nada.")
    else:
        lines.append("No tienes posiciones registradas.")
    lines.append("Limite de hoy: %s USD de riesgo total, %s operaciones." % (
        cfgd.get("max_daily_loss_usd"), cfgd.get("max_trades_per_day")))
    return "\n".join(lines)


def c_vender(bot, args):
    """Objetivo: si hay posicion abierta lo mueve; si no, deja una alerta para hoy."""
    if len(args) != 2:
        return "Uso: /vender NVDA 160.00"
    sym = _ticker(args[0])
    price = texto.safe_float(args[1], 0.0001, 1e7)
    if not sym or price is None:
        return "Uso: /vender NVDA 160.00 (precio valido)"
    if posiciones.abierta_de(sym):
        r = posiciones.cambiar(sym, target=price)
        c = (r or {}).get("cambios", [{}])[0]
        if c.get("aviso"):
            return ("Objetivo de %s movido a %s y aviso rearmado. Antes: %s." % (
                sym, _fmt(price), _fmt(c.get("antes"))))
        return ("Objetivo de %s guardado a %s, pero el aviso no se pudo armar: %s. "
                "Vigilalo a mano." % (sym, _fmt(price), c.get("motivo") or "ticker no soportado"))
    rid = "tg-venta-%s-%s-%s" % (sym.lower(), str(price).replace(".", "-"), alertas.hoy_ny())
    ok, motivo = alertas.armar(sym, "target", price, rid, label="venta")
    if not ok:
        return "No se pudo poner el aviso de venta de %s: %s." % (sym, motivo)
    return ("Aviso de venta puesto para hoy: %s cuando llegue a %s. Te aviso y decides." % (
        sym, _fmt(price)))


def c_stop(bot, args):
    """Stop: si hay posicion abierta lo mueve; si no, deja una alerta para hoy."""
    if len(args) != 2:
        return "Uso: /stop NVDA 154.00"
    sym = _ticker(args[0])
    price = texto.safe_float(args[1], 0.0001, 1e7)
    if not sym or price is None:
        return "Uso: /stop NVDA 154.00 (precio valido)"
    if posiciones.abierta_de(sym):
        r = posiciones.cambiar(sym, stop=price)
        c = (r or {}).get("cambios", [{}])[0]
        if c.get("aviso"):
            return ("Stop de %s movido a %s y aviso rearmado. Antes: %s." % (
                sym, _fmt(price), _fmt(c.get("antes"))))
        return ("Stop de %s guardado a %s, pero el aviso no se pudo armar: %s. "
                "Vigilalo a mano." % (sym, _fmt(price), c.get("motivo") or "ticker no soportado"))
    rid = "tg-stop-%s-%s-%s" % (sym.lower(), str(price).replace(".", "-"), alertas.hoy_ny())
    ok, motivo = alertas.armar(sym, "stop", price, rid, label="stop loss")
    if not ok:
        return "No se pudo poner el stop de %s: %s." % (sym, motivo)
    return ("Stop vigilado para hoy: %s si cae a %s. Te aviso cuando pase.\n"
            "Recuerda: en MyInvestor el stop se pone como orden aparte "
            "(NYSE/Nasdaq/Xetra, max 60 dias)." % (sym, _fmt(price)))


# ---------------------------------------------------------------- lenguaje natural (sin LLM)

def _norm(text):
    t = (text or "").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n"),
                 ("¿", ""), ("?", ""), ("¡", ""), ("!", "")):
        t = t.replace(a, b)
    t = " ".join(t.split())
    # abreviaturas de teclado
    abre = {"xq": "por que", "xk": "por que", "pq": "por que", "k": "que", "q": "que",
            "xo": "pero", "d": "de", "x": "por", "tmb": "tambien", "salu2": "saludos"}
    palabras = [abre.get(p, p) for p in t.split()]
    return " ".join(palabras)


TICKER_RX = r"([A-Za-z]{1,5}(?:\.[A-Za-z]{1,2})?)\b"
PRECIO_RX = r"(\d+(?:[.,]\d+)?)"
NO_TICKER = {"DE", "DEL", "EL", "LA", "LAS", "LOS", "EN", "A", "AL", "MI", "TU", "SU", "QUE",
             "POR", "PARA", "CON", "SIN", "UN", "UNA", "Y", "O", "SI", "NO", "ME", "TE", "SE"}


def _tk(raw):
    t = (raw or "").upper()
    if t in NO_TICKER or not texto.is_ticker(t):
        return None
    return t


def interpretar(texto_libre):
    """Traduce frases en español a un comando permitido. Determinista, sin LLM.

    Devuelve el comando (str) o None. Nunca ejecuta nada por si mismo.
    """
    t = _norm(texto_libre)
    # quitar cortesia
    for w in ("por favor", "oye", "hola", "buenas", "me puedes decir", "dime", "quiero saber", "puedes"):
        t = t.replace(w, " ")
    t = " ".join(t.split())

    if re.search(r"\b(vigila|sigue|anade|añade|mete)\s+(a\s+)?(los\s+)?(\d{1,2}\s+)?(ganadores|ganadoras|que mas suben)\b", t):
        m = re.search(r"\b(\d{1,2})\b", t)
        return "/seguir %s" % m.group(1) if m else "/seguir"
    if re.search(r"\b(evalua|evaluar|analiza|analizar)\s+(los\s+)?(\d{1,2}\s+)?(ganadores|ganadoras|que mas suben|el top)\b", t):
        m = re.search(r"\b(\d{1,2})\b", t)
        return "/evaluar %s" % m.group(1) if m else "/evaluar"
    if re.search(r"\b(cuales|cual)\b.*\b(probabilidad|cumplen|pasan|merecen|mejor)\b", t):
        return "/evaluar"
    if re.search(r"\b(analisis completo|estudio completo)\s+(de\s+)?" + TICKER_RX, t):
        m = re.search(r"\b(analisis completo|estudio completo)\s+(de\s+)?" + TICKER_RX, t)
        return "/elegir %s" % _tk(m.group(3)) if m and _tk(m.group(3)) else "/elegir"
    if re.search(r"\b(evalua|evaluar|estudia|estudiar)\s+" + TICKER_RX + r"\b", t):
        m = re.search(r"\b(evalua|evaluar|estudia|estudiar)\s+" + TICKER_RX, t)
        return "/elegir %s" % _tk(m.group(2)) if m and _tk(m.group(2)) else "/elegir"
    if re.search(r"\b(ganadores|ganadoras|que sube|que esta subiendo|las que mas suben|top del dia)\b", t):
        return "/ganadores"
    if re.search(r"\b(que hago ahora|que toca ahora|y ahora que|que debo hacer ahora|ahora que hago|guia|siguiente paso)\b", t):
        return "/guia"
    if re.search(r"\b(chuleta|ayuda operativa|como opero|como se opera|recordatorio de comandos)\b", t):
        return "/chuleta"
    if re.search(r"\b(que esta pasando|como esta el sistema|esta vivo|estado del sistema|como va todo)\b", t):
        return "/estado"
    if re.search(r"\b(ensename|explicame|que es|como funciona)\b", t):
        for k in ("orb", "time machine", "wilson", "flat by close", "senal a", "spread", "objetivo", "stop", "ev", "r"):
            if re.search(r"\b%s\b" % re.escape(k), t):
                return "/ensenar %s" % k
    if re.search(r"\b(explicame( esta| la| el)?( senal| ultima)?|explica( esta| la| el)?( senal)?)\b", t):
        m = re.search(r"\b(?:de|sobre|para)\s+" + TICKER_RX, t)
        return ("/explica %s" % _tk(m.group(1))) if m and _tk(m.group(1)) else "/explica"
    if re.search(r"\b(por que no hay senales|por que no hay senal|por que no compras|por que nada)\b", t):
        return "/porque"
    if re.search(r"\b(por que descartaste|por que descartado|por que no paso)\b", t):
        m = re.search(r"\b(?:descartaste|descartado|paso)\s+(?:a\s+)?" + TICKER_RX, t)
        return ("/porque %s" % _tk(m.group(1))) if m and _tk(m.group(1)) else "/porque"
    if re.search(r"\b(preparame la apertura|prepara la apertura|briefing|resumen previo)\b", t):
        return "/briefing"
    if re.search(r"\b(que pasa si no estoy comprado|coste de esperar|que me pierdo si no entro)\b", t):
        m = re.search(r"\b(?:de|en|para)\s+" + TICKER_RX, t)
        return ("/apertura %s" % _tk(m.group(1))) if m and _tk(m.group(1)) else "/apertura NVDA"
    if re.search(r"^\s*(entro|compro|comprar)\s*$", t):
        return "/resumen"
    if re.search(r"\b(entro|compro|comprar)\s+(en\s+)?" + TICKER_RX, t):
        m = re.search(r"\b(entro|compro|comprar)\s+(en\s+)?" + TICKER_RX, t)
        return ("/elegir %s" % _tk(m.group(3))) if m and _tk(m.group(3)) else "/resumen"
    m = re.search(r"\b(?:he\s+)?(?:entrado|entre|compre|compré|comprado)\s+(?:en\s+)?" + TICKER_RX +
                  r".*?" + PRECIO_RX + r".*?(?:con|de|por)?\s*(\d{1,6})\b", t)
    if m and _tk(m.group(1)):
        return "/entre %s %s %s" % (_tk(m.group(1)), m.group(2).replace(",", "."), m.group(3))
    m = re.search(r"\b(?:he\s+)?(?:salido|sali|vendi|vendí|cerrado)\s+(?:de\s+)?" + TICKER_RX +
                  r".*?" + PRECIO_RX, t)
    if m and _tk(m.group(1)):
        return "/sali %s %s" % (_tk(m.group(1)), m.group(2).replace(",", "."))
    if re.search(r"\b(que hago|plan de hoy|que hay hoy|hoy que)\b", t):
        return "/hoy"
    if re.search(r"\b(que compro|en que invierto|compro algo|hay algo que comprar)\b", t):
        return "/resumen"
    if re.search(r"\b(resumen|como va el dia|como vamos|que tal el dia)\b", t):
        return "/resumen"
    if re.search(r"\b(estado|como estas|sigues vivo|estas vivo)\b", t):
        return "/estado"
    if re.search(r"\b(como voy|pnl|ganancias|perdidas|resultado)\b", t):
        return "/pnl"
    if re.search(r"\b(posiciones|que tengo|mi cartera)\b", t):
        return "/posiciones"
    if re.search(r"\b(mantengo|aguanto|hold|dejo abierto|overnight)\b", t):
        return "RESPUESTA_MANTENER"
    m = re.search(r"\b(?:vende|vender|salir de|sal de|cierra)\s+(?:de\s+)?" + TICKER_RX + r".*?" + PRECIO_RX, t)
    if m and _tk(m.group(1)):
        return "/vender %s %s" % (_tk(m.group(1)), m.group(2).replace(",", "."))
    m = re.search(r"\bstop(?:\s*loss)?(?:\s+de)?\s+" + TICKER_RX + r".*?" + PRECIO_RX, t)
    if m and _tk(m.group(1)):
        return "/stop %s %s" % (_tk(m.group(1)), m.group(2).replace(",", "."))
    m = re.search(r"\b(?:compra|comprar|avisa(?:me)? si|alerta)\s+(?:de\s+)?" + TICKER_RX + r".*?" + PRECIO_RX, t)
    if m and _tk(m.group(1)):
        return "/alerta %s %s" % (_tk(m.group(1)), m.group(2).replace(",", "."))
    m = re.search(r"\b(?:noticias|que pasa con|que se dice de)\s+(?:(?:de|el|la|los|las)\s+){0,2}" + TICKER_RX, t)
    if m and _tk(m.group(1)):
        return "/noticias %s" % _tk(m.group(1))
    m = re.search(r"\b(?:analiza|mira|mirate|estudia|que tal|como ves|analisis de)\s+(?:(?:de|el|la|los|las)\s+)?" + TICKER_RX, t)
    if m and _tk(m.group(1)):
        return "/ticker %s" % _tk(m.group(1))
    m = re.search(r"\b(?:apertura|coste de esperar|hueco)\s+(?:(?:de|el|la|los|las)\s+)?" + TICKER_RX, t)
    if m and _tk(m.group(1)):
        return "/apertura %s" % _tk(m.group(1))
    m = re.search(r"\b(?:mercados|europa|alemania|xetra)\s+(?:(?:de|el|la|los|las)\s+)?" + TICKER_RX, t)
    if m and _tk(m.group(1)):
        return "/mercados %s" % _tk(m.group(1))
    m = re.search(r"\b(?:vigila|seguir|sigue)\s+(?:(?:de|el|la|los|las)\s+)?" + TICKER_RX, t)
    if m and _tk(m.group(1)):
        return "/vigila %s" % _tk(m.group(1))
    m = re.search(r"\b(?:incluye|incluir|anade|añade|mete|agrega)\s+(?:(?:en|al|a la)\s+)?(?:(?:lista|escaneo|orb)\s+)?" + TICKER_RX, t)
    if m and _tk(m.group(1)):
        return "/incluir %s" % _tk(m.group(1))
    m = re.search(r"\b(?:premarket|pre mercado)\s+(?:de\s+)?" + TICKER_RX, t)
    if m and _tk(m.group(1)):
        return "/pre %s" % _tk(m.group(1))
    m = re.search(r"\b(?:after hours|postmarket|post mercado)\s+(?:de\s+)?" + TICKER_RX, t)
    if m and _tk(m.group(1)):
        return "/post %s" % _tk(m.group(1))
    m = re.search(r"\b(?:precio|precios|cotizacion)\s+(?:de\s+|el\s+|la\s+)?\b" + TICKER_RX, t)
    if m and _tk(m.group(1)):
        return "/precios %s" % _tk(m.group(1))
    m = re.search(r"\b(?:compara|comparar)\s+(?:los\s+)?precios?\s+(?:de\s+)?\b" + TICKER_RX, t)
    if m and _tk(m.group(1)):
        return "/precios %s" % _tk(m.group(1))
    m = re.search(r"\b(?:compara|comparar)\s+\b" + TICKER_RX, t)
    if m and _tk(m.group(1)):
        return "/precios %s" % _tk(m.group(1))
    m = re.search(r"\b(?:apunta|guarda|referencia|ref)\s+(?:de\s+)?\b" + TICKER_RX + r"\s+" + PRECIO_RX, t)
    if m and _tk(m.group(1)):
        src = re.search(r"\b(borse|bf|xetra|tv|tradingview|investing|mx|myinvestor)\b", t)
        return "/ref %s %s %s" % (_tk(m.group(1)), m.group(2).replace(",", "."),
                                  src.group(1) if src else "manual")
    m = re.search(r"\b(?:apunta|guarda|referencia|ref)\s+" + PRECIO_RX + r"\s+(?:de|en)\s+\b" + TICKER_RX, t)
    if m and _tk(m.group(2)):
        src = re.search(r"\b(borse|bf|xetra|tv|tradingview|investing|mx|myinvestor)\b", t)
        return "/ref %s %s %s" % (_tk(m.group(2)), m.group(1).replace(",", "."),
                                  src.group(1) if src else "manual")
    return None


COMANDOS = {
    "estado": c_estado, "reloj": c_reloj, "briefing": c_briefing, "scan": c_scan,
    "ticker": c_ticker, "vigila": c_vigila, "dejar": c_dejar, "plan": c_plan, "tm": c_tm,
    "tamano": c_tamano, "risk": c_risk, "ticket": c_ticket, "alertas": c_alertas,
    "alerta": c_alerta, "noticias": c_noticias, "resultados": c_resultados, "pelosi": c_pelosi,
    "apertura": c_apertura, "mercados": c_mercados, "vigilar": c_vigilar,
    "descartadas": c_descartadas, "posiciones": c_posiciones, "entre": c_entre,
    "sali": c_sali, "pnl": c_pnl, "diario": c_diario, "registro": c_registro,
    "pausa": c_pausa, "reanudar": c_reanudar, "ayuda": c_ayuda, "start": c_ayuda,
    "hoy": c_hoy, "elegir": c_elegir, "resumen": c_resumen, "vender": c_vender, "stop": c_stop,
    "ahora": c_ahora, "explica": c_explica, "porque": c_porque, "ensenar": c_ensenar,
    "ganadores": c_ganadores, "ganadoras": c_ganadores, "suben": c_ganadores,
    "evaluar": c_evaluar, "seguir": c_seguir, "incluir": c_incluir,
    "ref": c_ref, "precios": c_precios, "guia": c_guia, "quepago": c_guia, "chuleta": c_chuleta,
    "pre": c_pre, "post": c_post, "nivel": c_nivel, "nivel_quitar": c_salir_nivel,
    "tesis": c_tesis, "raw": c_raw, "research": c_research,
}

PESADOS = {"scan", "ticker", "tm", "brevefing", "mercados", "apertura", "resultados", "briefing"}


def dispatch(bot, text):
    """Devuelve la respuesta. Acepta comandos y un conjunto cerrado de frases."""
    raw = (text or "").strip()
    if not raw:
        return "Escribe /ayuda."
    if not raw.startswith("/"):
        cmd = interpretar(raw)
        if cmd == "RESPUESTA_MANTENER":
            return ("Al final del dia no se mantiene nada: se cierra todo a las 15:55 ET "
                    "(21:55 Madrid; 18:55 en cierre anticipado). Es una regla del sistema, no una "
                    "preferencia. Si quieres cambiar esa regla, se cambia en CRITERIOS.md y se "
                    "documenta, no sobre la marcha.")
        if not cmd:
            ejemplos = ["que hago ahora", "que esta pasando", "analiza NVDA", "vende NVDA a 160",
                        "stop de NVDA en 154", "noticias de TSLA", "como voy", "por que no hay senales",
                        "explicame esta senal", "preparame la apertura"]
            import difflib
            cerca = difflib.get_close_matches(raw.lower(), ejemplos, n=3, cutoff=0.3)
            if not cerca:
                cerca = ejemplos[:3]
            return ("No te he entendido. Prueba con: " + " · ".join('"%s"' % c for c in cerca) +
                    "\nO escribe /ayuda.")
        raw = cmd
    parts = raw[1:].split()
    if not parts:
        return "Escribe /ayuda."
    cmd = parts[0].split("@")[0].lower()
    args = parts[1:]
    fn = COMANDOS.get(cmd)
    if not fn:
        return "Comando desconocido: /%s. Escribe /ayuda." % cmd
    cd = COOLDOWN.get(cmd)
    if cd:
        now = time.time()
        if now - _last.get(cmd, 0) < cd:
            return "Espera %d s antes de repetir /%s." % (cd - int(now - _last.get(cmd, 0)), cmd)
        _last[cmd] = now
    t0 = time.time()
    try:
        out = fn(bot, args)
    except Exception as exc:  # noqa: BLE001
        diario.append("bot_error", cmd=cmd, error=str(exc), output=str(exc))
        return "Fallo en /%s: %s" % (cmd, str(exc)[:300])
    diario.append("bot_cmd", cmd=cmd, args=args, seconds=round(time.time() - t0, 2),
                  output=(out or "")[:4000])
    return texto.recortar(out, 4000)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bot de Telegram del banco de pruebas")
    ap.add_argument("--simulate", help="ejecuta un comando y sale")
    ap.add_argument("--timeout", type=int, default=25)
    a = ap.parse_args(argv)
    bot = tg.Telegram()

    if a.simulate:
        print(dispatch(bot, a.simulate))
        return 0
    if bot.dry:
        print("Sin token/chat_id: esperando a que existan los secretos.")
        print("Ejecuta: python trader-ops/run/configurar_secretos.py")
        while bot.dry:
            time.sleep(30)
            bot = tg.Telegram()
        print("Secretos detectados: arrancando el bot.")

    offset = (cfg.read_json(OFFSET, {}) or {}).get("offset")
    me = bot.whoami() or {}
    diario.append("bot_arranque", bot=me.get("username"), output="arranque")
    print("Bot @%s escuchando. chat_id autorizado: %s" % (me.get("username"), bot.chat_id))
    while True:
        updates = bot.get_updates(offset=offset, timeout=a.timeout)
        for up in updates:
            offset = max(offset or 0, up.get("update_id", 0) + 1)
            cfg.write_json(OFFSET, {"offset": offset})
            msg = up.get("message") or {}
            cb = up.get("callback_query") or {}
            chat = str((msg.get("chat") or {}).get("id") or (cb.get("message") or {}).get("chat", {}).get("id") or "")
            if chat != str(bot.chat_id):
                diario.append("chat_ignorado", chat=chat, output=chat)
                continue
            if cb:
                bot.answer_callback(cb.get("id"), "Recibido")
                data = cb.get("data") or ""
                texto_cmd = {"plan": "/plan %s" % _ultimo_symbol(),
                             "tm": "/tm %s" % _ultimo_symbol(),
                             "risk": "/risk", "entre": "/posiciones",
                             "ignorar": "/estado", "silenciar": "/pausa"}.get(data, "/ayuda")
                bot.send(dispatch(bot, texto_cmd))
                continue
            if not msg.get("text"):
                continue
            bot.send(dispatch(bot, msg["text"]))
        time.sleep(1)


def _ultimo_symbol():
    sigs = registro.all_signals()
    return sigs[-1]["symbol"] if sigs else "NVDA"


if __name__ == "__main__":
    sys.exit(main())
