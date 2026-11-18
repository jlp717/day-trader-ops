"""Ensayo general: reproduce el pipeline con la sesion cerrada del 19-oct-2026 (fixtures).

Comprueba de una pasada: cadena completa, aritmetica, mensaje, validador,
deduplicacion y comandos de Telegram. Todo etiquetado ENSAYO. No toca el plan vivo.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import avisos, cfg, criterios, datos, diario, proceso, registro, skills, telegram as tg  # noqa: E402
from lib import texto, zonatiempo as zt  # noqa: E402

FX = cfg.SKILL / "tests" / "fixtures"
NOW = "2026-10-19 10:15"
DATE = "2026-10-19"
SYMBOL = "TSLA"


def _dir():
    d = cfg.STATE / "ensayo"
    d.mkdir(parents=True, exist_ok=True)
    return d


def correr(send=False):
    d = _dir()
    out = {"date": DATE, "symbol": SYMBOL, "pasos": {}, "ok": False, "fallos": []}
    bot = tg.Telegram(dry=not send)
    entry_p = d / "entry.json"
    plan_p = d / "plan.json"
    tm_p = d / "tm.json"
    orders_p = d / "orders.json"

    # 1 entry (fixture real de la sesion)
    e = skills.run("entry", ["check", SYMBOL, "--offline", str(FX / "trader-entry" / "TSLA-2026-10-19-5m.json"),
                             "--now", NOW, "--write", str(entry_p), "--json"], timeout=120, json_out=True)
    edoc = e.data or {}
    out["pasos"]["entry"] = {"status": edoc.get("status"),
                             "price": (edoc.get("trigger") or {}).get("price"),
                             "code": e.code, "event": e.event.get("id")}
    if edoc.get("status") != "triggered":
        out["fallos"].append("entry no disparo: %s" % edoc.get("reason"))
        return out

    # 2 exit
    x = skills.run("exit", ["plan", "--from", str(entry_p), "--stop", "or-mid", "--target", "1R",
                            "--write", str(plan_p), "--json"], timeout=120, json_out=True)
    plan = x.data or {}
    out["pasos"]["exit"] = {"entry": plan.get("entry"), "stop": plan.get("stop"),
                            "target": plan.get("target"), "risk": plan.get("risk_per_share"),
                            "event": x.event.get("id")}
    if not plan.get("entry"):
        out["fallos"].append("exit sin plan: %s" % x.stderr[:200])
        return out

    # 3 time machine (fixture de 60 dias)
    t = skills.run("timemachine", ["run", "--plan", str(plan_p), "--offline",
                                   str(FX / "trader-timemachine" / "TSLA-60d5m.json.gz"),
                                   "--until", "15:55", "--write", str(tm_p), "--json"],
                   timeout=600, json_out=True)
    tm = t.data or {}
    out["pasos"]["tm"] = {"p_target": (tm.get("mc") or {}).get("p_target"),
                          "p_stop": (tm.get("mc") or {}).get("p_stop"),
                          "replays": (tm.get("mc") or {}).get("replays"),
                          "history_n": (tm.get("history") or {}).get("triggered"),
                          "verdict": tm.get("verdict"), "event": t.event.get("id")}

    # 4 budget
    b = skills.run("budget", ["--plan", str(plan_p), "--write", str(orders_p), "--json",
                              "--now", NOW], timeout=120, json_out=True)
    bdoc = b.data or {}
    order = (bdoc.get("orders") or [bdoc])[0] if (bdoc.get("orders") or bdoc.get("symbol")) else {}
    out["pasos"]["budget"] = {"qty": order.get("qty"), "why": order.get("why"),
                              "event": b.event.get("id")}
    shares = int(float(order.get("qty") or 0))
    risk_ps = float(plan.get("risk_per_share") or 0)
    out["aritmetica"] = {"shares": shares, "riesgo_por_accion": risk_ps,
                         "perdida_al_stop": round(shares * risk_ps, 2),
                         "limite": cfg.config().get("max_loss_per_trade_usd"),
                         "cumple": shares * risk_ps <= cfg.config().get("max_loss_per_trade_usd")}

    # 5 risk
    r = skills.run("risk", ["--orders", str(orders_p), "--now", NOW, "--json", "--no-write"],
                   timeout=120, json_out=True)
    rdoc = r.data or {}
    res0 = (rdoc.get("results") or [{}])[0]
    out["pasos"]["risk"] = {"verdict": res0.get("verdict"), "reasons": res0.get("reasons"),
                            "event": r.event.get("id")}

    # 6 contexto para criterios (calidad en vivo, marcada)
    try:
        qa = datos.calidad(SYMBOL)
    except Exception as exc:
        qa = {"price": plan.get("entry"), "dollar_volume_20d": None, "spread_pct_proxy": None,
              "error": str(exc)}
    out["calidad"] = {"fuente": "datos en vivo, no del fixture", **qa}
    costs = datos.coste_ida_vuelta_usd(shares * float(plan.get("entry") or 0), "USD", cuenta_eur=True)
    costs_alt = datos.coste_ida_vuelta_usd(shares * float(plan.get("entry") or 0), "USD", cuenta_eur=False)
    ctx = {
        "symbol": SYMBOL, "plan": plan,
        "quote": {"price": float(plan.get("entry") or 0), "age_seconds": 0,
                  "data_time": DATE + "T14:15:00Z"},
        "quality": qa, "tm": tm,
        "news": {"adverse": [], "earnings": ["ENSAYO: no se consulta SEC en la repeticion"]},
        "risk": {"passed": res0.get("verdict") == "PASS", "reasons": res0.get("reasons") or []},
        "contracting": proceso.contratable(SYMBOL),
        "costs": costs,
        "costs_alt": costs_alt,
        "budget": {"shares": shares, "max_loss": round(shares * risk_ps, 2)},
        "ventana": {"ok": True, "detail": "ENSAYO con reloj fijado"},
        "setup_ok": True, "setup_detail": "fixture: TRIGGERED 10:15 a 364.18",
        "min_reward_risk": cfg.config().get("min_reward_risk"),
        "ruido": {"ok": True, "reasons": []},
        "presupuesto": {"ok": True, "detail": "ENSAYO"},
        "entry_time_et": "10:15 AM",
        "now": zt.now_utc().replace(year=2026, month=10, day=19, hour=14, minute=15, second=0, microsecond=0),
        "src": {"exit": x.event.get("id"), "budget": b.event.get("id"), "entry": e.event.get("id")},
    }
    ev = criterios.evaluar(ctx)
    out["evaluacion"] = {"verdict": ev["verdict"], "numbers": ev["numbers"],
                         "reasons": ev["reasons"], "checks": {k: v["ok"] for k, v in ev["checks"].items()}}
    payload = proceso.construir_mensaje_senal(ctx, ev, etiqueta="ENSAYO · formato de aviso")
    evs = {r.event["id"]: r.event for r in (e, x, b, t, r) if r.event}
    ok, problems = texto.validar(payload, evs)
    out["validador"] = {"ok": ok, "problemas": problems}
    out["etiqueta"] = "ENSAYO · veredicto real: %s" % ev["verdict"]

    # 7 envio + deduplicacion
    key = "ensayo:%s:%s" % (SYMBOL, DATE)
    mid1 = avisos.send_once(bot, key, payload["texto"], buttons=proceso.botones_senal())
    mid2 = avisos.send_once(bot, key, payload["texto"], buttons=proceso.botones_senal())
    out["telegram"] = {"primer_envio": mid1, "segundo_envio": mid2,
                       "dedupe_ok": mid2 is None and mid1 is None}
    if not bot.dry:
        out["telegram"]["dedupe_ok"] = mid2 is None
    out["mensaje"] = payload["texto"]
    out["ok"] = bool(out["pasos"]["entry"]["status"] == "triggered" and out["validador"]["ok"]
                     and out["aritmetica"]["cumple"])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ensayo general del pipeline")
    ap.add_argument("--send", action="store_true", help="envia de verdad a Telegram")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = correr(send=a.send)
    cfg.write_json(cfg.STATE / "ensayo_resultado.json", res)
    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print("ENSAYO", "OK" if res["ok"] else "CON FALLOS")
        for k, v in res.get("pasos", {}).items():
            print("  %-8s %s" % (k, v))
        print("  aritmetica", res.get("aritmetica"))
        print("  evaluacion", (res.get("evaluacion") or {}).get("verdict"))
        print("  validador", res.get("validador"))
        print("  telegram", res.get("telegram"))
        if res.get("fallos"):
            print("  fallos", res["fallos"])
        print("\n--- MENSAJE ---\n" + (res.get("mensaje") or ""))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
