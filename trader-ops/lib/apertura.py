"""Coste de esperar: que pasa en los primeros minutos y si entrar por ruptura sale mejor.

Se calcula con 60 dias de barras de 5 min (Yahoo) y se guarda en cache diaria.
Ninguna cifra se estima: si falta muestra, se dice.
"""
import datetime as dt
import statistics

from . import cfg
from . import datos
from . import diario
from . import zonatiempo as zt

CACHE_HORAS = 12


def _sessions(symbol):
    doc = datos.chart(symbol, "60d", "5m", ttl=CACHE_HORAS * 3600)
    by_day = {}
    for b in doc["bars"]:
        day = dt.datetime.fromtimestamp(b["t"], tz=zt.UTC).astimezone(zt.NEW_YORK).date()
        by_day.setdefault(day, []).append(b)
    out = []
    for day in sorted(by_day):
        bars = sorted(by_day[day], key=lambda x: x["t"])
        # solo sesiones completas (>= 70 barras) y en el horario NY
        first = dt.datetime.fromtimestamp(bars[0]["t"], tz=zt.UTC).astimezone(zt.NEW_YORK)
        if len(bars) < 70 or first.hour != 9 or first.minute != 30:
            continue
        out.append((day, bars))
    return doc, out


def _pct(a, b):
    return None if not b else (a / b - 1.0) * 100.0


def _quantiles(values, qs=(5, 25, 50, 75, 95)):
    if not values:
        return {}
    s = sorted(values)
    n = len(s)
    out = {("p%d" % q): s[min(n - 1, max(0, int(round(q / 100.0 * (n - 1)))))] for q in qs}
    out["mediana"] = out["p50"]
    return out


def analizar(symbol):
    doc, sessions = _sessions(symbol)
    if len(sessions) < 20:
        return {"symbol": symbol.upper(), "ok": False,
                "motivo": "solo %d sesiones completas (minimo 20)" % len(sessions)}
    gaps, r5, r15, r30, first15share, orb_vs_open, gap_fill, stop_slip = [], [], [], [], [], [], [], []
    orb_wins = orb_losses = 0
    ret_open_all, ret_orb_days = [], []
    for i, (day, bars) in enumerate(sessions):
        o = bars[0]["o"] or bars[0]["c"]
        prev = sessions[i - 1][1][-1]["c"] if i else None
        close = bars[-1]["c"]
        if prev:
            g = _pct(o, prev)
            if g is not None:
                gaps.append(g)
            # hueco rellenado: el precio toca el cierre previo durante la sesion
            lo = min(b["l"] or b["c"] for b in bars)
            hi = max(b["h"] or b["c"] for b in bars)
            gap_fill.append(1.0 if (g > 0 and lo <= prev) or (g < 0 and hi >= prev) else 0.0)
        c5 = bars[1]["c"] if len(bars) > 1 else None
        c15 = bars[3]["c"] if len(bars) > 3 else None
        c30 = bars[6]["c"] if len(bars) > 6 else None
        for arr, val in ((r5, c5), (r15, c15), (r30, c30)):
            x = _pct(val, o) if val else None
            if x is not None:
                arr.append(x)
        if c15 and abs(close - o) > 1e-9:
            first15share.append(abs(c15 - o) / abs(close - o) * 100.0)
        # Estrategia A: comprar en la apertura todos los dias y salir al cierre.
        ret_open = _pct(close, o)
        if ret_open is not None:
            ret_open_all.append(ret_open)
        # Estrategia B: comprar solo si tras los primeros 15 min hay cierre por encima del rango.
        rng = bars[:3]
        hi = max(b["h"] or b["c"] for b in rng)
        lo = min(b["l"] or b["c"] for b in rng)
        entry = None
        for b in bars[3:]:
            if b["c"] > hi:
                entry = b["c"]
                break
        if entry:
            ret_orb = _pct(close, entry)
            if ret_orb is not None and ret_open is not None:
                orb_vs_open.append(ret_orb - ret_open)
                ret_orb_days.append(ret_orb)
                if ret_orb > ret_open:
                    orb_wins += 1
                elif ret_orb < ret_open:
                    orb_losses += 1
            # stop en el mid del rango: se ejecuta peor?
            mid = (hi + lo) / 2.0
            after = bars[bars.index(b) + 1:]
            for b2 in after:
                if (b2["l"] or b2["c"]) <= mid:
                    if b2["c"] < mid:
                        stop_slip.append((mid - b2["c"]) / mid * 100.0)
                    break
    n = len(sessions)
    res = {
        "symbol": symbol.upper(),
        "ok": True,
        "sesiones": n,
        "desde": sessions[0][0].isoformat(),
        "hasta": sessions[-1][0].isoformat(),
        "gap_pct": {"n": len(gaps), "mediana": round(statistics.median(gaps), 3) if gaps else None,
                    **_quantiles(gaps)},
        "ret_5m_pct": {"n": len(r5), "media": round(statistics.fmean(r5), 3) if r5 else None,
                       **_quantiles(r5)},
        "ret_15m_pct": {"n": len(r15), "media": round(statistics.fmean(r15), 3) if r15 else None,
                        **_quantiles(r15)},
        "ret_30m_pct": {"n": len(r30), "media": round(statistics.fmean(r30), 3) if r30 else None,
                        **_quantiles(r30)},
        "primeros_15m_del_movimiento_pct": {
            "n": len(first15share),
            "mediana": round(statistics.median(first15share), 1) if first15share else None,
        },
        "apertura_todos_los_dias": {
            "n": len(ret_open_all),
            "media_pct": round(statistics.fmean(ret_open_all), 3) if ret_open_all else None,
            "suma_pct": round(sum(ret_open_all), 2) if ret_open_all else None,
            "dias_positivos": len([x for x in ret_open_all if x > 0]),
        },
        "orb_solo_dias_que_dispara": {
            "n": len(ret_orb_days),
            "media_pct": round(statistics.fmean(ret_orb_days), 3) if ret_orb_days else None,
            "suma_pct": round(sum(ret_orb_days), 2) if ret_orb_days else None,
            "dias_positivos": len([x for x in ret_orb_days if x > 0]),
        },
        "orb_mejor_que_apertura": {"n": len(orb_vs_open), "orb_mejor": orb_wins, "orb_peor": orb_losses,
                                   "dif_media_pct": round(statistics.fmean(orb_vs_open), 3) if orb_vs_open else None},
        "hueco_rellenado_pct": {"n": len(gap_fill),
                                "tasa": round(100 * statistics.fmean(gap_fill), 1) if gap_fill else None},
        "stop_peor_que_precio": {"n": len(stop_slip),
                                 "mediana_pct": round(statistics.median(stop_slip), 3) if stop_slip else None,
                                 "peor_pct": round(max(stop_slip), 3) if stop_slip else None},
    }
    return res


def bloque_texto(res, dec=2):
    """Bloque fijo para el briefing, en texto plano (sin cifras inventadas)."""
    if not res.get("ok"):
        return "Coste de esperar %s: no disponible (%s)." % (res.get("symbol"), res.get("motivo"))
    g, r15, orb, fill, slip = (res["gap_pct"], res["ret_15m_pct"], res["orb_mejor_que_apertura"],
                               res["hueco_rellenado_pct"], res["stop_peor_que_precio"])
    a, o = res["apertura_todos_los_dias"], res["orb_solo_dias_que_dispara"]
    return (
        "COSTE DE ESPERAR %s (%d sesiones, 5 min, %s a %s)\n"
        "  Hueco de apertura: mediana %s%%, p5 %s%%, p95 %s%% (n=%d)\n"
        "  Primeros 15 min: media %s%%, mediana %s%%, p5 %s%%, p95 %s%% (n=%d)\n"
        "  El 50%% de las sesiones hace menos del %s%% de su movimiento del dia en esos 15 min\n"
        "  Comprar en la apertura y salir al cierre: %d dias, media %s%%, %d positivos\n"
        "  Comprar solo si hay ruptura tras 15 min: %d dias, media %s%%, %d positivos\n"
        "  La ruptura paga peor precio que la apertura en %d de %d casos (media %s%%): "
        "es el precio de la confirmacion\n"
        "  El hueco se relleno en el %s%% de las sesiones (n=%d)\n"
        "  Stop en el mid: cuando se cruzo, cerro por debajo del stop una mediana de %s%% "
        "(peor %s%%, n=%d)\n" % (
            res["symbol"], res["sesiones"], res["desde"], res["hasta"],
            _f(g.get("mediana")), _f(g.get("p5")), _f(g.get("p95")), g.get("n"),
            _f(r15.get("media")), _f(r15.get("mediana")), _f(r15.get("p5")), _f(r15.get("p95")),
            r15.get("n"),
            _f(res["primeros_15m_del_movimiento_pct"].get("mediana")),
            a.get("n"), _f(a.get("media_pct")), a.get("dias_positivos"),
            o.get("n"), _f(o.get("media_pct")), o.get("dias_positivos"),
            orb.get("orb_peor"), orb.get("n"), _f(orb.get("dif_media_pct")),
            _f(fill.get("tasa")), fill.get("n"),
            _f(slip.get("mediana_pct")), _f(slip.get("peor_pct")), slip.get("n")))


def _f(x):
    return "n/d" if x is None else ("%.2f" % float(x))


def plan_condicional(res, plan=None):
    """Si-entonces construido solo con los niveles del plan y del estudio."""
    if not res.get("ok"):
        return ["Sin plan condicional: faltan datos de apertura."]
    lines = []
    if plan:
        lines.append("Si rompe %s y cierra por encima en 5 min -> entrada en el cierre de esa barra; "
                     "stop %s, objetivo %s, fuera a las %s ET." % (
                         plan.get("level") or plan.get("or_high") or "el maximo del rango",
                         plan.get("stop"), plan.get("target"), plan.get("flat_by")))
        lines.append("Si el precio ya esta a mas de 0,5R de la entrada -> no perseguir: la senal caduca.")
    lines.append("Si el hueco supera el p95 (%s%%) -> el plan de hoy no aplica: es otra sesion." %
                 _f((res.get("gap_pct") or {}).get("p95")))
    lines.append("Si el stop se cruza, asumir que puede llenarse %s%% peor que su precio (mediana historica)." %
                 _f((res.get("stop_peor_que_precio") or {}).get("mediana_pct")))
    return lines
