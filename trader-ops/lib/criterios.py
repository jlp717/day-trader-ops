"""Motor de decision: filtros, Wilson, valor esperado en R y clasificacion.

Los umbrales viven aqui y se copian literalmente en CRITERIOS.md. No se relajan
despues. Un fallo de dato no se convierte en senal: se convierte en aviso.

Vocabulario:
  SEÑAL A   todo pasa -> se envia
  VIGILAR   falla algo no critico o falta muestra -> solo bajo demanda
  DESCARTADA motivo exacto -> solo bajo demanda
"""
import math
from statistics import fmean

# ---------------------------------------------------------------- umbrales (CRITERIOS.md)
UMBRALES = {
    "min_price": 5.0,
    "min_dollar_volume_20d": 20_000_000,
    "max_spread_pct_proxy": 0.80,
    "max_age_seconds": 300,
    "min_history_triggered": 12,
    "min_history_target_rate": 0.0,       # se compara con el break-even, no con un numero fijo
    "wilson_z": 1.96,
    "max_entry_drift_r": 0.50,            # si el precio se alejo mas de 0,5R, la senal caduca
    "max_a_per_hour": 2,
    "max_a_per_symbol_day": 2,
    "cooldown_minutes": 30,
    "target_r_estandar": 2.0,
    "max_signals_por_dia": 3,
}

CHECK_ORDEN = [
    "setup", "ventana", "noticias", "resultados", "plan", "risk", "frescura",
    "calidad", "contratable", "timemachine", "historial", "ev", "ruido", "presupuesto",
]

ETIQUETA = {
    "setup": "setup disparado",
    "ventana": "dentro de la ventana de entrada",
    "noticias": "sin noticias adversas",
    "resultados": "sin resultados hoy/manana",
    "plan": "plan de salida valido",
    "risk": "trader-risk PASS",
    "frescura": "dato fresco",
    "calidad": "liquidez y spread",
    "contratable": "contratable en MyInvestor",
    "timemachine": "Time Machine a favor",
    "historial": "historico con muestra",
    "ev": "valor esperado > 0 tras costes",
    "ruido": "limites de ruido",
    "presupuesto": "presupuesto de riesgo",
}


def wilson(k, n, z=None):
    """Intervalo de Wilson al 95 %. Devuelve (low, high). n=0 -> (0,1)."""
    z = z or UMBRALES["wilson_z"]
    if n <= 0:
        return 0.0, 1.0
    p = k / float(n)
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def break_even(target_r):
    """Tasa de objetivo-primero necesaria para EV=0 con un target de R dado."""
    return 1.0 / (1.0 + float(target_r))


def coste_en_r(coste_usd, shares, risk_per_share):
    if not shares or not risk_per_share:
        return None
    max_loss = float(shares) * float(risk_per_share)
    if max_loss <= 0:
        return None
    return float(coste_usd) / max_loss


def _pct(x):
    return "%.1f%%" % (100.0 * x)


def evaluar(ctx):
    """ctx: dict con todo lo necesario. Devuelve el veredicto y las comprobaciones.

    Claves de ctx:
      symbol, plan{entry,stop,target,risk_per_share,reward_risk,flat_by},
      quote{price,age_seconds}, quality{...}, tm{mc,history}, news{adverse[],earnings[]},
      risk{passed,reasons[]}, contracting{ok,market,note}, costs{total_usd,...},
      budget{shares,max_loss}, registro_stats{...}, ruido{ok,reasons[]}
    """
    checks = {}

    def add(key, ok, detail):
        checks[key] = {"ok": bool(ok), "detail": detail}

    plan = ctx.get("plan") or {}
    quote = ctx.get("quote") or {}
    quality = ctx.get("quality") or {}
    tm = ctx.get("tm") or {}
    mc = tm.get("mc") or {}
    hist = tm.get("history") or {}
    news = ctx.get("news") or {}
    risk = ctx.get("risk") or {}
    contracting = ctx.get("contracting") or {}
    costs = ctx.get("costs") or {}
    budget = ctx.get("budget") or {}
    ventana = ctx.get("ventana") or {}

    target_r = float(plan.get("target_r") or plan.get("reward_risk") or 0) or 0.0
    be = break_even(target_r) if target_r > 0 else 1.0

    # 1 setup y ventana
    add("setup", bool(ctx.get("setup_ok")), ctx.get("setup_detail") or "entry.py dice triggered")
    add("ventana", bool(ventana.get("ok", True)), ventana.get("detail") or "dentro de la ventana")

    # 2 noticias y resultados
    adverse = list(news.get("adverse") or [])
    add("noticias", not adverse, adverse[0] if adverse else "sin titulares adversos ni 8-K marcados")
    earnings = list(news.get("earnings") or [])
    add("resultados", not earnings, earnings[0] if earnings else "sin resultados hoy ni manana")

    # 3 plan de salida
    plan_ok = bool(plan.get("entry") and plan.get("stop") and plan.get("target")
                   and float(plan.get("stop")) < float(plan.get("entry")) < float(plan.get("target")))
    mrr = float(ctx.get("min_reward_risk") or 1.0)
    rr = float(plan.get("reward_risk") or 0)
    plan_ok = plan_ok and rr >= mrr
    add("plan", plan_ok, "stop %.2f / target %.2f / R:R %.2f (min %.2f)" % (
        float(plan.get("stop") or 0), float(plan.get("target") or 0), rr, mrr))

    # 4 risk
    add("risk", bool(risk.get("passed")), "; ".join(risk.get("reasons") or []) or "PASS")

    # 5 frescura
    age = quote.get("age_seconds")
    fresh = age is not None and age <= UMBRALES["max_age_seconds"]
    add("frescura", fresh, "dato de hace %ss (max %ss)" % (age, UMBRALES["max_age_seconds"]))

    # 6 calidad
    dv = quality.get("dollar_volume_20d") or 0
    sp = quality.get("spread_pct_proxy")
    px = quality.get("price") or 0
    q_ok = (px >= UMBRALES["min_price"] and dv >= UMBRALES["min_dollar_volume_20d"]
            and sp is not None and sp <= UMBRALES["max_spread_pct_proxy"])
    add("calidad", q_ok, "precio %.2f, $%.1fM/dia, rango proxy %.2f%%" % (
        px, dv / 1e6, sp or 0))

    # 7 contratable
    add("contratable", bool(contracting.get("ok")), contracting.get("note") or "")

    # 8 Time Machine
    p_t, p_s = float(mc.get("p_target") or 0), float(mc.get("p_stop") or 0)
    tm_ok = p_t > p_s and p_t > be
    add("timemachine", tm_ok, "MC objetivo %s vs stop %s (break-even %s), %s replays seed %s" % (
        _pct(p_t), _pct(p_s), _pct(be), mc.get("replays"), mc.get("seed")))

    # 9 historico real con Wilson
    trig = int(hist.get("triggered") or 0)
    tgt = int(hist.get("target") or 0)
    stp = int(hist.get("stop") or 0)
    lo, hi = wilson(tgt, trig) if trig else (0.0, 1.0)
    hist_ok = trig >= UMBRALES["min_history_triggered"] and tgt > stp and lo > be
    add("historial", hist_ok, "n=%d disparos: %d objetivo / %d stop, tasa %s (Wilson %s-%s), break-even %s" % (
        trig, tgt, stp, _pct(tgt / trig) if trig else "n/d", _pct(lo), _pct(hi), _pct(be)))

    # 10 EV tras costes
    shares = budget.get("shares")
    cost_r = coste_en_r(costs.get("total_usd") or 0, shares, plan.get("risk_per_share"))
    ev_mc = (float(mc.get("avg_R") or 0) - cost_r) if cost_r is not None else None
    ev_hist = (float(hist.get("avg_R") or 0) - cost_r) if cost_r is not None else None
    ev = min([x for x in (ev_mc, ev_hist) if x is not None], default=None)
    ev_ok = ev is not None and ev > 0
    add("ev", ev_ok, "EV MC %s R, EV historico %s R, coste %s R -> conservador %s R" % (
        _r(ev_mc), _r(ev_hist), _r(cost_r), _r(ev)))

    # 11 ruido y presupuesto
    ruido = ctx.get("ruido") or {}
    add("ruido", bool(ruido.get("ok", True)), "; ".join(ruido.get("reasons") or []) or "sin limites tocados")
    pres = ctx.get("presupuesto") or {}
    add("presupuesto", bool(pres.get("ok", True)), pres.get("detail") or "dentro del presupuesto diario")

    # 12 deriva del precio (segunda lectura)
    drift_ok, drift_detail = True, "precio dentro del plan"
    entry = float(plan.get("entry") or 0)
    risk_ps = float(plan.get("risk_per_share") or 0)
    if quote.get("price") and entry and risk_ps:
        drift = (float(quote["price"]) - entry) / risk_ps
        if drift > UMBRALES["max_entry_drift_r"]:
            drift_ok = False
            drift_detail = "el precio ya subio %.2fR sobre la entrada: senal caducada" % drift
        elif float(quote["price"]) <= float(plan.get("stop") or 0):
            drift_ok = False
            drift_detail = "el precio ya esta en el stop: senal caducada"
        else:
            drift_detail = "precio a %+.2fR de la entrada" % drift
    add("deriva", drift_ok, drift_detail)

    # clasificacion
    criticos = {"setup", "ventana", "plan", "risk", "frescura", "calidad", "contratable",
                "timemachine", "ev", "deriva"}
    fallos = [k for k, v in checks.items() if not v["ok"]]
    criticos_fallidos = [k for k in fallos if k in criticos]
    if not fallos:
        verdict = "SEÑAL A"
    elif not criticos_fallidos and len(fallos) <= 1 and "historial" in fallos:
        verdict = "VIGILAR"
    elif not criticos_fallidos and set(fallos) <= {"historial", "ruido", "presupuesto", "noticias", "resultados"}:
        verdict = "VIGILAR"
    else:
        verdict = "DESCARTADA"

    reasons = ["%s: %s" % (ETIQUETA.get(k, k), checks[k]["detail"]) for k in fallos]
    return {
        "symbol": ctx.get("symbol"),
        "verdict": verdict,
        "checks": checks,
        "failed": fallos,
        "critical_failed": criticos_fallidos,
        "reasons": reasons,
        "numbers": {
            "target_r": target_r, "break_even": be, "p_target_mc": p_t, "p_stop_mc": p_s,
            "hist_n": trig, "hist_target": tgt, "hist_stop": stp,
            "wilson_low": lo, "wilson_high": hi, "cost_r": cost_r,
            "ev_mc": ev_mc, "ev_hist": ev_hist, "ev": ev,
            "shares": shares, "max_loss": budget.get("max_loss"),
            "cost_usd": costs.get("total_usd"),
            "age_seconds": age, "price": quote.get("price"),
        },
        "umbrales": dict(UMBRALES),
    }


def _r(x):
    return "n/d" if x is None else "%+.3f" % x


def resumen_checks(ev):
    """Lineas cortas PASS/FALLA para Telegram o consola."""
    out = []
    for k in CHECK_ORDEN + ["deriva"]:
        c = (ev.get("checks") or {}).get(k)
        if not c:
            continue
        out.append("%s %s: %s" % ("OK " if c["ok"] else "NO ", ETIQUETA.get(k, k), c["detail"]))
    return out


def registro_libre(stats):
    """Texto honesto sobre el historial vivo de senales."""
    n = int((stats or {}).get("cerradas") or 0)
    if n < UMBRALES["min_history_triggered"]:
        return "SIN HISTORIAL VALIDADO (%d cerradas, minimo %d)" % (n, UMBRALES["min_history_triggered"])
    return "registro vivo: %d cerradas, %d objetivos, %d stops, R medio %+.2f" % (
        n, stats.get("objetivos", 0), stats.get("stops", 0), float(stats.get("r_medio") or 0))
