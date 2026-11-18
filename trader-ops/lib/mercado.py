"""Comparacion EE. UU. vs Europa para el mismo valor (NVDA vs NVD.DE).

Mide liquidez, spread proxy, conversion EUR/USD, huecos de apertura europeos
frente al cierre americano y si la senal ORB es replicable. Todo con datos de
Yahoo y cuentas propias; sin mezclar niveles sin tipo de cambio explicito.
"""
import datetime as dt
import statistics

from . import datos
from . import zonatiempo as zt


def _sessions(symbol, tz=zt.NEW_YORK, min_bars=60):
    doc = datos.chart(symbol, "60d", "5m", ttl=12 * 3600)
    by_day = {}
    for b in doc["bars"]:
        day = dt.datetime.fromtimestamp(b["t"], tz=zt.UTC).astimezone(tz).date()
        by_day.setdefault(day, []).append(b)
    out = []
    for day in sorted(by_day):
        bars = sorted(by_day[day], key=lambda x: x["t"])
        if len(bars) >= min_bars:
            out.append((day, bars))
    return doc, out


def _orb_trigger(bars, n=3):
    hi = max(b["h"] or b["c"] for b in bars[:n])
    lo = min(b["l"] or b["c"] for b in bars[:n])
    for b in bars[n:]:
        if b["c"] > hi:
            return b["c"], (hi + lo) / 2.0, b
    return None, None, None


def comparar(us="NVDA", eu="NVD.DE", eur=None):
    eur = eur or datos.eurusd()
    q_us = datos.calidad(us)
    q_eu = datos.calidad(eu)
    doc_us, ses_us = _sessions(us, zt.NEW_YORK)
    doc_eu, ses_eu = _sessions(eu, zt.BERLIN, min_bars=50)

    # retornos de 5 min emparejados por hora de pared (aproximacion honesta: misma hora local)
    us_ret, eu_ret = {}, {}
    for day, bars in ses_us:
        for i in range(3, len(bars)):
            us_ret[(day, bars[i]["t"])] = (bars[i]["c"] / bars[i - 1]["c"] - 1.0)
    for day, bars in ses_eu:
        for i in range(3, len(bars)):
            eu_ret[(day, bars[i]["t"])] = (bars[i]["c"] / bars[i - 1]["c"] - 1.0)
    # correlacion contemporanea por fecha+hora de pared
    corr = None
    tu = {dt.datetime.fromtimestamp(t, tz=zt.UTC).strftime("%H:%M"): v for (d, t), v in us_ret.items()}
    te = {dt.datetime.fromtimestamp(t, tz=zt.UTC).strftime("%H:%M"): v for (d, t), v in eu_ret.items()}
    common = sorted(set(tu) & set(te))
    if len(common) > 30:
        xs = [tu[k] for k in common]
        ys = [te[k] for k in common]
        try:
            corr = statistics.correlation(xs, ys)
        except Exception:
            corr = None

    # huecos de apertura europeos frente al cierre americano previo (convertido a EUR)
    gaps_eu = []
    us_closes = {d: bars[-1]["c"] for d, bars in ses_us}
    for day, bars in ses_eu:
        prev_days = [d for d in us_closes if d < day]
        if not prev_days:
            continue
        prev = us_closes[max(prev_days)]
        open_eur = bars[0]["o"] or bars[0]["c"]
        gaps_eu.append((open_eur / (prev / eur) - 1.0) * 100.0)

    # replicabilidad ORB: dias en que US dispara y dias en que EU dispara
    us_days, eu_days = {}, {}
    for day, bars in ses_us:
        trig, _, _ = _orb_trigger(bars)
        us_days[day] = trig is not None
    for day, bars in ses_eu:
        trig, _, _ = _orb_trigger(bars)
        eu_days[day] = trig is not None
    co = sorted(set(us_days) & set(eu_days))
    both = [d for d in co if us_days[d] and eu_days[d]]
    only_us = [d for d in co if us_days[d] and not eu_days[d]]
    only_eu = [d for d in co if eu_days[d] and not us_days[d]]

    # diferencia de precio tras convertir (cierre mas reciente de cada uno)
    px_us = doc_us["bars"][-1]["c"]
    px_eu = doc_eu["bars"][-1]["c"]
    px_eu_usd = px_eu * eur
    dif = (px_eu_usd / px_us - 1.0) * 100.0

    return {
        "us": {"symbol": us, "quality": q_us, "price_usd": px_us, "sessions": len(ses_us)},
        "eu": {"symbol": eu, "quality": q_eu, "price_eur": px_eu, "price_usd": round(px_eu_usd, 4),
               "sessions": len(ses_eu)},
        "eurusd": round(eur, 4),
        "diferencia_precio_pct": round(dif, 3),
        "correlacion_5m": None if corr is None else round(corr, 3),
        "gap_eu_vs_cierre_us_pct": {
            "n": len(gaps_eu),
            "mediana": round(statistics.median(gaps_eu), 3) if gaps_eu else None,
            "p5": round(sorted(gaps_eu)[max(0, int(0.05 * len(gaps_eu)))], 3) if gaps_eu else None,
            "p95": round(sorted(gaps_eu)[min(len(gaps_eu) - 1, int(0.95 * len(gaps_eu)))], 3) if gaps_eu else None,
        },
        "orb_replicable": {"dias_comunes": len(co), "ambos": len(both),
                           "solo_us": len(only_us), "solo_eu": len(only_eu)},
        "ratio_liquidez": (round((q_us["dollar_volume_20d"] or 0) /
                                 ((q_eu["dollar_volume_20d"] or 0) * eur), 1)
                           if q_eu.get("dollar_volume_20d") else None),
    }


def recomendacion(r, execution="US"):
    liq = r.get("ratio_liquidez")
    lines = []
    lines.append("Liquidez: %s mueve %.1f veces mas dolares al dia que %s." % (
        r["us"]["symbol"], liq or 0, r["eu"]["symbol"]))
    lines.append("Precio: %s %.2f USD vs %s %.2f EUR = %.2f USD (diferencia %+.2f%%, EUR/USD %.4f)." % (
        r["us"]["symbol"], r["us"]["price_usd"], r["eu"]["symbol"], r["eu"]["price_eur"],
        r["eu"]["price_usd"], r["diferencia_precio_pct"], r["eurusd"]))
    lines.append("Correlacion de retornos de 5 min emparejados por hora: %s." % r.get("correlacion_5m"))
    o = r.get("orb_replicable") or {}
    lines.append("ORB replicable: en %s dias comunes, disparo en ambos %s, solo en EE. UU. %s, solo en Europa %s." % (
        o.get("dias_comunes"), o.get("ambos"), o.get("solo_us"), o.get("solo_eu")))
    lines.append("El motor del skill calcula el rango 9:30-9:45 de Nueva York: sobre el grafico europeo "
                 "no es aplicable sin recalcular el rango a 9:00-9:15 CET (no lo hace).")
    if execution.upper() == "US":
        lines.append("Recomendacion: calcular y ejecutar en EE. UU. (%s). Europa solo como referencia." % r["us"]["symbol"])
    else:
        lines.append("Recomendacion: ejecutar en Europa, pero la senal se calcula en EE. UU.; "
                     "niveles en USD convertidos a EUR con el tipo del dia y marcados como tales.")
    return lines
