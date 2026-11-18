"""Pipeline de decision para un valor: de la barra al mensaje validado.

Orden fijo (FASE 6): quote -> entry -> exit -> timemachine -> budget -> risk
-> news -> calidad -> criterios -> validacion -> (si SEÑAL A) Telegram.

Nada de esto improvisa cifras: todas salen de un script o de datos.py, y el
mensaje se valida contra la salida guardada antes de enviarse.
"""
import time

from . import cfg
from . import criterios
from . import datos
from . import diario
from . import posiciones
from . import referencias
from . import registro
from . import skills
from . import telegram as tg
from . import texto
from . import zonatiempo as zt

ADVERSE_WORDS = ("halt", "bankrupt", "delist", "restat", "offering", "recall", "breach",
                 "hack", "lawsuit", "investigation", "fraud", "guidance cut", "misses")
EARNINGS_WORDS = ("earnings", "results", "quarter", "q1", "q2", "q3", "q4", "report")


def _num(x, dec=2):
    return ("%%.%df" % dec) % float(x)


def _edad_horas(it, now):
    when = it.get("time") or ""
    try:
        return (now - __import__("datetime").datetime.fromisoformat(when)).total_seconds() / 3600.0
    except Exception:
        return 0.0


def _es_adversa(it):
    low = (it.get("title") or "").lower()
    return bool(any(w in low for w in ADVERSE_WORDS)
                or it.get("important")
                or (it.get("kind") == "filing" and "2.02" in str(it)))


def _es_resultado(it, now):
    low = (it.get("title") or "").lower()
    tags = [str(t).lower() for t in (it.get("tags") or [])]
    age_h = _edad_horas(it, now)
    return ("earnings" in tags and age_h <= 30) or (any(w in low for w in EARNINGS_WORDS) and age_h <= 18)


def clasificar_noticias(doc, symbol):
    """(adverse[], earnings[]) a partir del JSON de news.py. Conservador: bloquea de mas."""
    adverse, earnings = [], []
    if not isinstance(doc, dict):
        return adverse, earnings
    now = zt.now_utc()
    for it in doc.get("items") or []:
        title = (it.get("title") or "")
        if _es_adversa(it):
            adverse.append("%s (%s)" % (title[:90], it.get("source") or "?"))
        if _es_resultado(it, now):
            earnings.append("%s (%s)" % (title[:90], it.get("time", "")[:16]))
    return adverse[:3], earnings[:3]


def simbolos_afectados(doc, tipo="earnings"):
    """Tickers concretos con titular adverso o de resultados, con la misma regla que arriba.

    El aviso de premarket nombraba toda la watchlist aunque el titular fuera de un solo
    valor; esto devuelve solo los que de verdad aparecen en las noticias.
    """
    if not isinstance(doc, dict):
        return []
    now = zt.now_utc()
    fuera = []
    for it in doc.get("items") or []:
        sym = str(it.get("ticker") or it.get("symbol") or "").upper()
        if not sym or sym in fuera:
            continue
        if (tipo == "adverse" and _es_adversa(it)) or (tipo != "adverse" and _es_resultado(it, now)):
            fuera.append(sym)
    return fuera


def contratable(symbol, market="US"):
    """Contratabilidad real: primero el MCP oficial de MyInvestor; si no responde, heuristica."""
    from . import myinvestor
    sym = symbol.upper()
    real = myinvestor.contratable(sym)
    if real.get("ok") is not None:
        if real.get("ok"):
            real["market"] = market
            real["note"] = "%s · mercados %s · monedas %s" % (
                real.get("nota") or "catalogo MyInvestor",
                ", ".join(real.get("mercados") or []) or "n/d",
                ", ".join(real.get("monedas") or []) or "n/d")
        return real
    # sin MCP: lo documentado, marcado como no verificado
    if market.upper() != "US":
        return {"ok": True, "market": market,
                "note": "mercado %s: catalogo no verificado (MCP no disponible)" % market}
    if any(ch.isdigit() for ch in sym) or sym.endswith((".DE", ".PA", ".AS", ".L", ".MC")):
        return {"ok": False, "market": market, "note": "%s no es un ticker estadounidense simple" % sym}
    return {"ok": True, "market": "US",
            "note": "ticker US: MyInvestor opera NDQ y NYS (myinvestor.es, 18-nov-2026); "
                    "contratacion exacta no verificada (MCP no disponible)"}


def ventana(now=None, cfgd=None):
    cfgd = cfgd or cfg.config()
    now = now or zt.now_utc()
    ny = now.astimezone(zt.NEW_YORK)
    day = ny.date()
    from . import calendario
    o, c, why = calendario.nyse_session(day)
    if o is None:
        return {"ok": False, "detail": "mercado cerrado: %s" % why}
    if c == calendario.NYSE_EARLY:
        cutoff = "12:30"
    else:
        cutoff = cfgd.get("no_entries_after") or "15:30"
    before = cfgd.get("no_entries_before") or "09:45"
    t = ny.strftime("%H:%M")
    ok = before <= t <= cutoff
    return {"ok": ok, "detail": "NY %s, ventana %s-%s" % (t, before, cutoff)}


def _limites_ruido(symbol, cfgd, veredicto_previo=None):
    reasons = []
    hoy = zt.madrid().date().isoformat()
    sigs = [s for s in registro.all_signals() if s.get("ts_madrid", "").startswith(hoy)]
    if len(sigs) >= criterios.UMBRALES["max_signals_por_dia"]:
        reasons.append("ya hay %d señales hoy (max %d)" % (len(sigs), criterios.UMBRALES["max_signals_por_dia"]))
    por_symbol = [s for s in sigs if s["symbol"] == symbol.upper()]
    if len(por_symbol) >= criterios.UMBRALES["max_a_per_symbol_day"]:
        reasons.append("%s ya tuvo %d señales hoy" % (symbol.upper(), len(por_symbol)))
    now = time.time()
    for s in sigs:
        try:
            ts = __import__("datetime").datetime.fromisoformat(s["ts_madrid"]).timestamp()
        except Exception:
            continue
        if now - ts < criterios.UMBRALES["cooldown_minutes"] * 60:
            reasons.append("enfriamiento: ultima señal hace %d min" % int((now - ts) / 60))
            break
    return {"ok": not reasons, "reasons": reasons}


def _presupuesto(cfgd, shares, risk_ps):
    hoy = zt.madrid().date().isoformat()
    sigs = [s for s in registro.all_signals() if s.get("ts_madrid", "").startswith(hoy)]
    usado = sum(float((s.get("plan") or {}).get("risk_per_share") or 0) * float(s.get("shares") or 0)
                for s in sigs)
    nuevo = float(shares or 0) * float(risk_ps or 0)
    tope = float(cfgd.get("max_daily_loss_usd") or 100)
    ok = (usado + nuevo) <= tope + 1e-6
    return {"ok": ok, "detail": "riesgo comprometido hoy %.2f USD + %.2f = %.2f (tope %.2f)" % (
        usado, nuevo, usado + nuevo, tope)}


def construir_mensaje_senal(ctx, ev, *, etiqueta="SEÑAL A"):
    """Mensaje de Telegram con Builder trazable. Devuelve payload de texto."""
    plan = ctx["plan"]
    b = texto.Builder()
    b.line("<b>%s · %s</b> · PAPEL" % (ctx["symbol"], etiqueta))
    b.line("Setup: %s · entrada %s" % (
        plan.get("setup", "orb"),
        ctx["entry_time_et"]))
    b.line("Ahora: %s" % zt.short_stamp(ctx.get("now") or None))
    b.line("Dato: %s · edad %s s" % (ctx["quote"]["data_time"], ctx["quote"]["age_seconds"]))
    b.line("Cierre de vela %s ET · señal %s s después del cierre (pipeline %s s)." % (
        ctx.get("entry_time_et") or "n/d",
        b.num(ctx.get("trigger_delay_s"), 0, "trigger_delay"),
        b.num(ctx.get("latency_s"), 0, "latency")))
    refs = referencias.get(ctx['symbol'])
    if refs:
        b.raw("Referencias externas: %s\n" % " · ".join(
            "%s %s %s" % (r['source'], r['price'], r['currency']) for r in refs))
    b.blank()
    b.line("Entrada %s %s" % (b.num(plan["entry"], 2, "entrada", src=ctx["src"]["exit"]), "USD"))
    b.line("Stop    %s %s" % (b.num(plan["stop"], 2, "stop", src=ctx["src"]["exit"]),
                              "(mid del rango, redondeado abajo)"))
    b.line("Objetivo %s (%sR) · flat by %s ET" % (
        b.num(plan["target"], 2, "target", src=ctx["src"]["exit"]),
        b.num(plan.get("target_r") or 0, 1, "target_r"), plan.get("flat_by")))
    b.line("Tamano  %s acc. · riesgo %s USD al stop (%s por accion)" % (
        b.num(ctx["budget"]["shares"], 0, "acciones"),
        b.num(ctx["budget"]["max_loss"], 2, "max_loss", src=ctx["src"]["budget"]),
        b.num(plan["risk_per_share"], 2, "riesgo_accion", src=ctx["src"]["exit"])))
    b.line("Coste estimado ida+vuelta: %s USD (MyInvestor 0,12%% + 0,30%% FX) · con cuenta USD: %s USD" % (
        b.num((ctx.get("costs") or {}).get("total_usd") or 0, 2, "coste", src=None),
        b.num((ctx.get("costs_alt") or {}).get("total_usd") or 0, 2, "coste_usd_acct")))
    b.add_allowed("0,12", "0,30")
    if ctx.get("cross_check"):
        b.raw("Contraste: %s\n" % ctx["cross_check"])
    b.blank()
    nums = ev["numbers"]
    b.line("Time Machine: objetivo primero %s, stop primero %s, nada %s (%s replays, seed %s)" % (
        b.num(100 * nums["p_target_mc"], 1, "p_t_mc", pct=True),
        b.num(100 * nums["p_stop_mc"], 1, "p_s_mc", pct=True),
        b.num(100 * float(ctx["tm"]["mc"].get("p_neither") or 0), 1, "p_n_mc", pct=True),
        b.num(ctx["tm"]["mc"].get("replays") or 0, 0, "replays"),
        b.num(ctx["tm"]["mc"].get("seed") or 0, 0, "seed")))
    b.line("Historico real: %s disparos, %s objetivo, %s stop, tasa %s (Wilson %s-%s), break-even %s" % (
        b.num(nums["hist_n"], 0, "hist_n"),
        b.num(nums["hist_target"], 0, "hist_target"),
        b.num(nums["hist_stop"], 0, "hist_stop"),
        b.num(100 * (nums["hist_target"] / nums["hist_n"]) if nums["hist_n"] else 0, 1, "tasa_hist", pct=True),
        b.num(100 * nums["wilson_low"], 1, "wilson_low", pct=True),
        b.num(100 * nums["wilson_high"], 1, "wilson_high", pct=True),
        b.num(100 * nums["break_even"], 1, "break_even", pct=True)))
    b.line("EV conservador tras costes: %s R (coste %s R)" % (
        b.num(nums["ev"] or 0, 3, "ev", signed=True),
        b.num(nums["cost_r"] or 0, 3, "cost_r")))
    b.blank()
    b.line("Frecuencias de una simulacion y de un historico, no promesas.")
    b.line("Salida: stop, objetivo o flat by close, lo que llegue antes. No se mantiene.")
    b.line("Operar: compra limitada; /entre con el fill; stop-loss y venta limitada. /guia para el paso a paso.")
    b.line("Re-entrada: este setup no se repite hoy. Maximo 2 SEÑAL A por valor y 3 al dia.")
    ana = ctx.get("analyst") or {}
    if ana.get("filed"):
        b.line("Ultimo trimestre presentado a la SEC: %s (%s)." % (ana["filed"], ana.get("fiscal") or "n/d"))
    b.line(registro_libre_txt())
    b.line("PRUEBA EN PAPEL · no se ha enviado ninguna orden")
    return b.payload()


def registro_libre_txt():
    return "Registro vivo: " + criterios.registro_libre(registro.stats())


def analyst_info(symbol):
    """Ultimo trimestre presentado segun la SEC. Sin cifras en el aviso: solo fecha y periodo."""
    try:
        r = skills.analyst([symbol])
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:120]}
    d = r.data
    if isinstance(d, list) and d:
        d = d[0]
    res = (d or {}).get("result") or {}
    rows = res.get("rows") or []
    if not rows:
        return {"error": (r.stderr or "sin filas XBRL")[:120]}
    last = rows[0]
    return {"filed": last.get("filed"), "fiscal": last.get("fiscal"), "form": last.get("form"),
            "entity": res.get("entity"), "event": r.event.get("id") if r.event else None}


def _dias_desde(iso):
    try:
        d = __import__("datetime").date.fromisoformat(iso)
    except Exception:
        return None
    return (zt.madrid().date() - d).days


def _trigger_delay(entry_time_et):
    """Segundos desde el cierre de la vela (HH:MM ET) hasta ahora. None si no cuadra."""
    if not entry_time_et:
        return None
    try:
        hh, mm = [int(x) for x in str(entry_time_et).split(":")[:2]]
        now_et = zt.ny()
        t = now_et.replace(hour=hh, minute=mm, second=0, microsecond=0)
        d = (now_et - t).total_seconds()
        return round(d, 1) if 0 <= d < 3600 else None
    except (TypeError, ValueError):
        return None


def contexto_desde_cadena(symbol, cadena, cfgd=None):
    """Contexto de criterios a partir de una cadena ejecutada en sandbox.

    No escribe en el plan vivo, no registra señales y no envia nada: sirve para
    responder "analiza X" sin alterar el estado del dia.
    """
    cfgd = cfgd or cfg.config()
    symbol = symbol.upper()
    edoc = cadena.get("entry") or {}
    plan = cadena.get("plan") or {}
    tm = cadena.get("tm") or {}
    bdoc = cadena.get("budget") or {}
    rdoc = cadena.get("risk") or {}
    orders = bdoc.get("orders") or ([bdoc] if bdoc.get("symbol") else [])
    order = orders[0] if orders else {}
    res0 = (rdoc.get("results") or [{}])[0]
    risk = {"passed": res0.get("verdict") == "PASS", "reasons": res0.get("reasons") or []}

    q = datos.quote(symbol)
    qa = datos.calidad(symbol)
    nw = skills.news([symbol], hours=24)
    adverse, earnings = clasificar_noticias(nw.data, symbol)
    ana = analyst_info(symbol)
    filed_dias = _dias_desde(ana.get("filed")) if ana.get("filed") else None
    if filed_dias is not None and filed_dias <= 3:
        earnings.append("ultimo trimestre presentado hace %d dia(s) (%s)" % (filed_dias, ana.get("fiscal")))

    shares = int(float(order.get("qty") or 0))
    notional = shares * float(plan.get("entry") or 0)
    cuenta_eur = bool(cfgd.get("cuenta_eur", True))
    costs = datos.coste_ida_vuelta_usd(notional, currency=qa.get("currency") or "USD",
                                       cuenta_eur=cuenta_eur)
    ctx = {
        "symbol": symbol,
        "plan": plan,
        "quote": q,
        "quality": qa,
        "tm": tm,
        "news": {"adverse": adverse, "earnings": earnings},
        "risk": risk,
        "contracting": contratable(symbol, cfgd.get("execution_market") or "US"),
        "costs": costs,
        "budget": {"shares": shares,
                   "max_loss": round(shares * float(plan.get("risk_per_share") or 0), 2)},
        "ventana": ventana(cfgd=cfgd),
        "setup_ok": True,
        "setup_detail": "entry.py TRIGGERED a %s" % (edoc.get("time") or "n/d"),
        "min_reward_risk": cfgd.get("min_reward_risk"),
        "ruido": _limites_ruido(symbol, cfgd),
        "presupuesto": _presupuesto(cfgd, shares, plan.get("risk_per_share")),
        "entry_time_et": edoc.get("time"),
        "analyst": ana,
    }
    return ctx, criterios.evaluar(ctx)


def evaluar_symbol(symbol, *, cfgd=None, enviar=True, bot=None, forzar=False):
    """Cadena completa. Devuelve dict con veredicto y, si procede, el mensaje enviado."""
    t0 = time.time()
    cfgd = cfgd or cfg.config()
    out = {"symbol": symbol.upper(), "verdict": None, "steps": [], "ctx": None,
           "payload": None, "message_id": None, "reasons": []}

    # 0) freno por evidencia
    freno, motivo = registro.freno_activo()
    if freno and not forzar:
        out["verdict"] = "FRENO"
        out["reasons"] = [motivo]
        return out

    # 1) precio y frescura
    try:
        q = datos.quote(symbol)
    except datos.DataError as exc:
        out["verdict"] = "SIN DATOS"
        out["reasons"] = ["Yahoo no da precio: %s" % exc]
        return out
    out["steps"].append(("quote", q["price"], q["age_seconds"]))

    # 2) segunda lectura en prices.json via alerts (la usa budget/risk)
    skills.alerts_quote([symbol], write=True)

    # 3) entry.py
    entry = skills.entry_check(symbol, write=True)
    edoc = entry.data or {}
    if edoc.get("status") != "triggered":
        out["verdict"] = "SIN SEÑAL"
        out["reasons"] = ["entry.py: %s (%s)" % (edoc.get("status") or "sin datos",
                                                 edoc.get("reason") or entry.stderr.strip()[:120])]
        return out
    out["entry_time_et"] = edoc.get("time")

    # 4) exit.py (2R por politica, ver CRITERIOS.md)
    exit_ = skills.exit_plan_from_entry(stop="or-mid", target="%gR" % criterios.UMBRALES["target_r_estandar"],
                                       write=True)
    plan = exit_.data or {}
    if not plan.get("entry"):
        out["verdict"] = "DESCARTADA"
        out["reasons"] = ["exit.py rechaza el plan: %s" % (exit_.stderr.strip()[:160] or "sin plan")]
        return out

    # 5) Time Machine con flat_by
    tmres = skills.timemachine(until=plan.get("flat_by"), write=True)
    tm = tmres.data or {}
    if not tm.get("mc"):
        out["verdict"] = "DESCARTADA"
        out["reasons"] = ["Time Machine no pudo correr: %s" % (tmres.stderr.strip()[:160] or "sin datos")]
        return out

    # 6) budget (usa prices.json fresco: si el precio subio, menos acciones)
    bg = skills.budget(limit="plan", write=True)
    bdoc = bg.data or {}
    orders = bdoc.get("orders") or ([bdoc] if bdoc.get("symbol") else [])
    order = orders[0] if orders else {}
    if not order.get("symbol"):
        out["verdict"] = "DESCARTADA"
        out["reasons"] = ["budget no propone orden: %s" % (bg.stderr.strip()[:160] or "sin orden")]
        return out

    # 7) risk
    rk = skills.risk_check()
    rdoc = rk.data or {}
    res0 = (rdoc.get("results") or [{}])[0]
    passed = res0.get("verdict") == "PASS"
    risk = {"passed": passed, "reasons": res0.get("reasons") or []}

    # 8) noticias
    nw = skills.news([symbol], hours=24)
    adverse, earnings = clasificar_noticias(nw.data, symbol)

    # 8b) fundamentales: si el ultimo 10-Q/8-K se presento hace <=3 dias, hay riesgo de resultados
    ana = analyst_info(symbol)
    filed_dias = _dias_desde(ana.get("filed")) if ana.get("filed") else None
    if filed_dias is not None and filed_dias <= 3:
        earnings.append("ultimo trimestre presentado hace %d dia(s) (%s)" % (filed_dias, ana.get("fiscal")))

    # 9) calidad, ventana, contratable
    try:
        qa = datos.calidad(symbol)
    except datos.DataError as exc:
        out["verdict"] = "SIN DATOS"
        out["reasons"] = ["calidad: %s" % exc]
        return out
    win = ventana(cfgd=cfgd)
    contr = contratable(symbol, cfgd.get("execution_market") or "US")

    # 10) costes con el tamano real (cuenta en EUR por defecto; se puede cambiar en config)
    cuenta_eur = bool(cfgd.get("cuenta_eur", True))
    notional = float(order.get("qty") or 0) * float(plan.get("entry") or 0)
    costs = datos.coste_ida_vuelta_usd(notional, currency=qa.get("currency") or "USD",
                                       cuenta_eur=cuenta_eur)
    costs_alt = datos.coste_ida_vuelta_usd(notional, currency=qa.get("currency") or "USD",
                                           cuenta_eur=not cuenta_eur)

    shares = int(float(order.get("qty") or 0))
    budget_info = {"shares": shares, "max_loss": round(shares * float(plan.get("risk_per_share") or 0), 2)}

    ctx = {
        "symbol": symbol.upper(),
        "plan": plan,
        "quote": q,
        "quality": qa,
        "tm": tm,
        "news": {"adverse": adverse, "earnings": earnings},
        "risk": risk,
        "contracting": contr,
        "costs": costs,
        "costs_alt": costs_alt,
        "budget": budget_info,
        "ventana": win,
        "setup_ok": True,
        "setup_detail": "entry.py TRIGGERED a %s" % edoc.get("time"),
        "min_reward_risk": cfgd.get("min_reward_risk"),
        "ruido": _limites_ruido(symbol, cfgd),
        "presupuesto": _presupuesto(cfgd, shares, plan.get("risk_per_share")),
        "entry_time_et": edoc.get("time"),
        "latency_s": round(time.time() - t0, 1),
        "trigger_delay_s": _trigger_delay(edoc.get("time")),
        "analyst": ana,
        "src": {"exit": exit_.event.get("id") if exit_.event else None,
                "budget": bg.event.get("id") if bg.event else None,
                "entry": entry.event.get("id") if entry.event else None},
    }
    ev = criterios.evaluar(ctx)
    out["ctx"] = ctx
    out["evaluacion"] = ev
    out["verdict"] = ev["verdict"]
    out["reasons"] = ev["reasons"]

    diario.append("evaluacion", symbol=symbol.upper(), veredicto=ev["verdict"],
                  checks={k: v["ok"] for k, v in ev["checks"].items()},
                  numbers=ev["numbers"], motivos=ev["reasons"][:6],
                  plan={k: plan.get(k) for k in ("entry", "stop", "target", "risk_per_share",
                                                 "target_r", "flat_by", "date", "setup")},
                  quality={k: qa.get(k) for k in ("price", "dollar_volume_20d", "spread_pct_proxy")},
                  latency_s=ctx.get("latency_s"), trigger_delay_s=ctx.get("trigger_delay_s"),
                  output=str(ev["reasons"]))

    if ev["verdict"] != "SEÑAL A":
        return out

    # 11) mensaje + validacion + segunda lectura
    payload = construir_mensaje_senal(ctx, ev)
    evs = {}
    for r in (entry, exit_, bg, tmres, rk, nw):
        if r.event:
            evs[r.event["id"]] = r.event
    ok, problems = texto.validar(payload, evs)
    if not ok:
        out["verdict"] = "DESCARTADA"
        out["reasons"] = ["validador: " + "; ".join(problems[:4])]
        diario.append("validacion_fallida", symbol=symbol.upper(), problemas=problems,
                      mensaje=payload["texto"], output="; ".join(problems))
        return out

    q2 = datos.quote(symbol)  # cache 30 s: segunda lectura real
    drift = (q2["price"] - float(plan["entry"])) / float(plan["risk_per_share"])
    if drift > criterios.UMBRALES["max_entry_drift_r"] or q2["price"] <= float(plan["stop"]):
        out["verdict"] = "SEÑAL CADUCADA"
        out["reasons"] = ["el precio se movio a %+.2fR de la entrada" % drift]
        diario.append("senal_caducada", symbol=symbol.upper(), drift=round(drift, 3),
                      output="drift %.3f" % drift)
        return out

    # 12) segundo testigo: Yahoo vs CNBC. Si difieren mucho, no se envia.
    cross_ok, cross_detail, _alt = datos.cross_check(symbol, q2["price"])
    if not cross_ok:
        out["verdict"] = "DESCARTADA"
        out["reasons"] = ["datos discrepantes: " + cross_detail]
        diario.append("datos_discrepantes", symbol=symbol.upper(), detail=cross_detail)
        if enviar:
            try:
                (bot or tg.Telegram()).send(
                    "⚠️ Señal bloqueada por datos discrepantes: %s" % cross_detail)
            except Exception:
                pass
        return out
    ctx["cross_check"] = cross_detail

    out["payload"] = payload
    if enviar:
        from . import avisos
        bot = bot or tg.Telegram()
        try:
            key = "senal:%s:%s:%s" % (symbol.upper(), plan.get("date"), plan.get("entry"))
            mid = avisos.send_once(bot, key, payload["texto"], buttons=botones_senal())
            out["message_id"] = mid
            sig = registro.add(symbol, plan, ev, mensaje_id=mid, extra={"shares": shares,
                                                                       "coste_usd": costs["total_usd"]})
            out["signal_id"] = sig["id"]
            diario.append("senal_enviada", symbol=symbol.upper(), signal_id=sig["id"],
                          message_id=mid, output=payload["texto"])
        except tg.TelegramError as exc:
            out["verdict"] = "ERROR TELEGRAM"
            out["reasons"] = [str(exc)]
            diario.append("telegram_error", symbol=symbol.upper(), error=str(exc), output=str(exc))
    return out


def botones_senal():
    return [[("Ver plan", "plan"), ("Time Machine", "tm")],
            [("Riesgo", "risk"), ("Ya entre", "entre")],
            [("Ignorar", "ignorar"), ("Silenciar 1 h", "silenciar")]]
