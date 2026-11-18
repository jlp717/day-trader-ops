"""Foto del sistema para los paneles y para /estado. Solo lee archivos: cero red.

Todo lo que muestra sale de un archivo escrito por un script; si falta, "n/d".
"""
import datetime as dt
import json
import os

from . import ahora, alertas, calendario, cfg, diario, posiciones, registro
from . import zonatiempo as zt


def _age(iso):
    if not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=zt.UTC)
    return int((zt.now_utc() - t).total_seconds())


def _precios():
    doc = cfg.read_json(cfg.TRADER / "prices.json", {}) or {}
    precios = doc.get("prices") or {}
    return {k.upper(): v for k, v in precios.items()}, doc.get("as_of")


def _alertas():
    hoy = zt.ny().date().isoformat()
    estado = (cfg.read_json(cfg.TRADER / "state" / "alerts.json", {}) or {}).get("rung") or {}
    estado_x = (cfg.read_json(alertas.XETRA, {}) or {}).get("rung") or {}
    armadas = []
    for r in alertas.reglas_skill(hoy):
        if r.get("id") not in estado:
            armadas.append(r)
    for r in alertas.reglas_xetra(hoy):
        if r.get("id") not in estado_x:
            armadas.append(r)
    return armadas


def _hits_orb():
    hoy = zt.madrid().date().isoformat()
    doc = cfg.read_json(cfg.STATE / "orb.json", {}) or {}
    if not (doc.get("as_of") or "").startswith(hoy):
        doc = cfg.read_json(cfg.STATE / "scan_orb.json", {}) or {}
    if not (doc.get("as_of") or "").startswith(hoy):
        return {}, None
    return {h.get("symbol"): h for h in (doc.get("hits") or [])}, doc.get("as_of")


def _hoy_evaluaciones():
    hoy = zt.madrid().date().isoformat()
    return [e for e in diario.read_all()
            if e.get("event") == "evaluacion" and (e.get("ts_madrid") or "").startswith(hoy)]


def foto(now=None):
    now = now or zt.madrid()
    hoy = now.date().isoformat()
    start, end, why = calendario.session_madrid(now.date())
    fase = ahora.fase(now)
    ev_titulo, ev_when = ahora.siguiente_evento(now)

    hb = cfg.read_json(cfg.STATE / "heartbeat.json", {}) or {}
    hb_age = _age(hb.get("ts_utc"))
    rows = diario.read_all()
    hace1h = (zt.now_utc() - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recientes = [r for r in rows if (r.get("ts_utc") or "") >= hace1h]
    errores = [r for r in recientes if r.get("event") in ("error", "bot_error", "telegram_error",
                                                          "validacion_fallida")]
    http429 = [r for r in recientes if "429" in (str(r.get("stderr") or "") + str(r.get("output") or ""))]
    cmds = [r for r in recientes if r.get("event") == "cmd"]
    cmds_1m = [r for r in cmds if (r.get("ts_utc") or "") >=
               (zt.now_utc() - dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")]

    precios, precios_as_of = _precios()
    hits, orb_as_of = _hits_orb()
    cfgd = cfg.config()
    watch = list(cfgd.get("watch") or [])
    for sym in hits:
        if sym not in watch:
            watch.append(sym)

    vigilados = []
    for sym in watch[:12]:
        px = precios.get(sym)
        nivel = (hits.get(sym) or {}).get("or_high")
        d = None
        if px and nivel:
            d = (px / float(nivel) - 1) * 100
        vigilados.append({"symbol": sym, "price": px, "level": nivel, "dist_pct": d})

    evs = _hoy_evaluaciones()
    por_nivel = {"SEÑAL A": [], "VIGILAR": [], "DESCARTADA": [], "SIN SEÑAL": [], "SIN DATOS": [],
                 "FRENO": [], "SEÑAL CADUCADA": []}
    for e in evs:
        por_nivel.setdefault(e.get("veredicto") or "?", []).append(e)
    senales_hoy = [e for e in evs if e.get("veredicto") == "SEÑAL A"]

    abiertas = []
    pos = posiciones.abiertas()
    minutos_cierre = None
    if end:
        minutos_cierre = int((end - now).total_seconds() // 60)
    for p in pos:
        px = precios.get(p["symbol"])
        d_stop = d_tgt = None
        if px and p.get("stop"):
            d_stop = (float(px) - float(p["stop"])) / float(px) * 100
        if px and p.get("target"):
            d_tgt = (float(p["target"]) - float(px)) / float(px) * 100
        abiertas.append({"symbol": p["symbol"], "qty": p["qty"], "entry": p["entrada"],
                         "stop": p.get("stop"), "target": p.get("target"), "price": px,
                         "dist_stop_pct": d_stop, "dist_target_pct": d_tgt})

    st = registro.stats()
    pnl = posiciones.pnl()
    freno, motivo_freno = registro.freno_activo()
    armadas = _alertas()

    riesgo_papel = sum(float((s.get("plan") or {}).get("risk_per_share") or 0) * float(s.get("shares") or 0)
                       for s in registro.all_signals() if (s.get("ts_madrid") or "").startswith(hoy))
    riesgo_manual = posiciones.riesgo_comprometido()
    riesgo_hoy = riesgo_papel + riesgo_manual
    trades_hoy = len([s for s in registro.all_signals()
                      if (s.get("ts_madrid") or "").startswith(hoy)])

    edad_datos = _age(precios_as_of) if precios_as_of else None
    if edad_datos is None:
        last_scan = diario.last_command("scanner")
        edad_datos = _age((last_scan or {}).get("ts_utc"))

    return {
        "now_madrid": now.strftime("%Y-%m-%d %H:%M:%S"),
        "now_ny": now.astimezone(zt.NEW_YORK).strftime("%H:%M"),
        "offset_h": zt.offset_hours(now),
        "session": {"start": start.strftime("%H:%M") if start else None,
                    "end": end.strftime("%H:%M") if end else None,
                    "why": why, "open": bool(start and start <= now <= end)},
        "phase": {"key": fase[0], "title": fase[1], "system": fase[2], "you": fase[3], "ignore": fase[4]},
        "next": {"title": ev_titulo, "at": ev_when.strftime("%H:%M") if ev_when else None,
                 "countdown": ahora.cuenta_atras(ev_when, now)},
        "health": {"heartbeat_age_s": hb_age, "heartbeat_phase": hb.get("phase"),
                   "alive": hb_age is not None and hb_age < (900 if start and start <= now <= end else 3600),
                   "errors_1h": len(errores), "http429_1h": len(http429),
                   "cmds_1m": len(cmds_1m)},
        "data": {"age_s": edad_datos, "prices_as_of": precios_as_of, "orb_as_of": orb_as_of},
        "watch": vigilados,
        "signals": {"counts": {k: len(v) for k, v in por_nivel.items()},
                    "A": [{"symbol": e.get("symbol"), "motivos": e.get("motivos")} for e in senales_hoy],
                    "watchlist": [{"symbol": e.get("symbol"), "motivos": (e.get("motivos") or [])[:2]}
                                  for e in evs if e.get("veredicto") == "VIGILAR"][:8],
                    "descartadas": [{"symbol": e.get("symbol"), "motivos": (e.get("motivos") or [])[:2]}
                                    for e in evs if e.get("veredicto") == "DESCARTADA"][:12]},
        "positions": abiertas,
        "minutes_to_close": minutos_cierre,
        "alerts": [{"id": a.get("id"), "symbol": a.get("symbol"), "type": a.get("type"),
                    "price": a.get("price") or a.get("at")} for a in armadas],
        "pnl": {"posiciones_cerradas": pnl["operaciones"], "pnl_usd": pnl["pnl_usd"],
                "r_total": pnl["r_total"]},
        "registro": st,
        "freno": {"activo": freno, "motivo": motivo_freno},
        "limits": {"risk_today_usd": round(riesgo_hoy, 2),
                   "risk_signals_usd": round(riesgo_papel, 2),
                   "risk_manual_usd": riesgo_manual,
                   "risk_cap_usd": cfgd.get("max_daily_loss_usd"),
                   "trades_today": trades_hoy,
                   "trades_cap": cfgd.get("max_trades_per_day")},
        "paused": bool((cfg.read_json(cfg.STATE / "pausa.json", {}) or {}).get("pausado")),
    }


def resumen_5_lineas(now=None):
    """El saludo de inicio de sesion: 5 lineas, sin relleno."""
    f = foto(now)
    l1 = "%s Madrid / %s NY · mercado %s · %s" % (
        f["now_madrid"][11:16], f["now_ny"],
        "ABIERTO" if f["session"]["open"] else "cerrado",
        f["phase"]["title"])
    edad = f["health"]["heartbeat_age_s"]
    l2 = "Sistema %s (latido %s, fase %s, errores 1h %d)" % (
        "VIVO" if f["health"]["alive"] else "PARADO",
        ("%ss" % edad) if edad is not None else "nunca",
        f["health"]["heartbeat_phase"] or "sin latido", f["health"]["errors_1h"])
    l3 = "Vigila: %s" % (", ".join(v["symbol"] for v in f["watch"][:8]) or "nada")
    l4 = "Señales hoy: %d A, %d vigilar, %d descartadas · registro %d cerradas R %+.2f" % (
        f["signals"]["counts"].get("SEÑAL A", 0), f["signals"]["counts"].get("VIGILAR", 0),
        f["signals"]["counts"].get("DESCARTADA", 0), f["registro"]["cerradas"], f["registro"]["r_medio"])
    l5 = "Proximo: %s a las %s (en %s)" % (
        f["next"]["title"] or "n/d", f["next"]["at"] or "-", f["next"]["countdown"])
    return [l1, l2, l3, l4, l5]
