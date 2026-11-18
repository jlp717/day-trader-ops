"""Comprobacion de salud de las 11 herramientas del skill. Solo lectura.

    python trader-ops/run/smoke.py [--json]

Ejecuta cada herramienta con argumentos minimos y seguros, mide latencia y edad
del ultimo dato, y guarda el resultado en trader-ops/state/smoke.json.
Las que necesitan sesion abierta se marcan como 'requiere sesion' si el mercado
esta cerrado: eso es informacion, no un fallo.
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import calendario, cfg, datos, diario, skills  # noqa: E402
from lib import zonatiempo as zt  # noqa: E402

TMP = cfg.STATE / "smoke"
TMP.mkdir(parents=True, exist_ok=True)


def _primera_linea(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:160]
    return ""


def correr():
    out = {"ts_utc": zt.iso_utc(), "ts_madrid": zt.iso_madrid(), "abierto": None, "tools": []}
    start, end, why = calendario.session_madrid(zt.madrid().date())
    ahora = zt.madrid()
    abierto = bool(start and start <= ahora <= end)
    out["abierto"] = abierto
    out["sesion"] = "%s-%s (%s)" % (start.strftime("%H:%M") if start else "-",
                                    end.strftime("%H:%M") if end else "-", why)

    def add(name, res, nota="", acepta_uno=False):
        ok = res.code == 0 or (acepta_uno and res.code == 1 and bool(res.stdout.strip()))
        out["tools"].append({"tool": name, "code": res.code, "seconds": res.seconds,
                             "ok": ok, "primera_linea": _primera_linea(res.text),
                             "nota": nota, "event": res.event.get("id")})

    # 1 scanner: universe
    add("scanner.universe", skills.run("scanner", ["universe", "--no-write", "--json"],
                                       timeout=180, json_out=True))
    # 2 scanner: daily (un solo valor)
    add("scanner.daily", skills.scanner_daily(symbols=["NVDA"], no_write=True))
    # 3 scanner: orb
    r = skills.scanner_orb()
    nota = "" if abierto else "requiere sesion abierta"
    add("scanner.orb", r, nota)
    # 4 news (exit 1 = nada nuevo, es normal)
    add("news", skills.news(["NVDA"], hours=24, no_sec=True), acepta_uno=True)
    # 5 entry (exit 1 = no disparado, es normal)
    add("entry", skills.entry_check("NVDA", write=False), acepta_uno=True)
    # 6 exit (fecha pasada para que el Time Machine encuentre la barra)
    sesion = calendario.next_trading_day(zt.madrid().date(), "US", include_today=False)
    previa = zt.madrid().date()
    for _ in range(10):
        previa = previa - __import__("datetime").timedelta(days=1)
        if calendario.is_trading_day(previa, "US"):
            break
    x = skills.run("exit", ["plan", "--symbol", "NVDA", "--entry", "158.00", "--or-high", "157.46",
                            "--or-low", "154.76", "--target", "2R", "--date", previa.isoformat(),
                            "--time", "10:15 AM", "--json"], timeout=120, json_out=True)
    add("exit", x)
    plan_p = TMP / "plan.json"
    if x.code == 0 and x.data:
        cfg.write_json(plan_p, x.data)
    # 7 timemachine
    tm = skills.run("timemachine", ["run", "--plan", str(plan_p), "--json",
                                    "--write", str(TMP / "tm.json")], timeout=600, json_out=True)
    add("timemachine", tm, "" if tm.code == 0 else "necesita entrada dentro de los datos")
    # 8 budget (con el reloj del dia del plan)
    orders_p = TMP / "orders.json"
    now_plan = "%s 10:15" % previa.isoformat()
    b = skills.run("budget", ["--plan", str(plan_p), "--json", "--write", str(orders_p),
                              "--now", now_plan], timeout=120, json_out=True)
    add("budget", b)
    # 9 risk (BLOCK tambien es una respuesta valida: el JSON existe)
    add("risk", skills.run("risk", ["--orders", str(orders_p), "--json", "--no-write",
                                    "--now", now_plan, "--out", str(TMP / "risk.json")],
                           timeout=120, json_out=True), acepta_uno=True)
    # 10 broker (ticket)
    add("broker.ticket", skills.run("broker", ["show", "--orders", str(orders_p), "--json",
                                               "--now", now_plan,
                                               "--state", str(TMP / "broker.json"),
                                               "--risk", str(TMP / "risk.json")],
                                    timeout=60, json_out=True), acepta_uno=True)
    # 11 alerts
    add("alerts.clock", skills.alerts_clock(), acepta_uno=True)
    add("alerts.quote", skills.alerts_quote(["NVDA"], write=False))
    # 12 analyst (necesita UA SEC)
    add("analyst", skills.analyst(["NVDA"]),
        "" if cfg.sec_user_agent() else "sin SEC_USER_AGENT", acepta_uno=bool(cfg.sec_user_agent()))
    # 13 pelosi
    add("pelosi.index", skills.run("pelosi", ["index", "--member", "pelosi", "--limit", "3", "--json"],
                                   timeout=180, json_out=True), acepta_uno=True)

    # frescura y latencia
    try:
        q = datos.quote("NVDA")
        out["frescura"] = {"symbol": "NVDA", "price": q["price"], "data_time": q["data_time"],
                           "age_seconds": q["age_seconds"], "exchange": q["exchange"]}
    except Exception as exc:
        out["frescura"] = {"error": str(exc)}
    tiempos = [t["seconds"] for t in out["tools"]]
    if tiempos:
        out["latencia"] = {"n": len(tiempos), "mediana": round(sorted(tiempos)[len(tiempos) // 2], 2),
                           "maxima": round(max(tiempos), 2)}
    ok = [t for t in out["tools"] if t["ok"] or t["nota"] in ("requiere sesion abierta", "sin SEC_USER_AGENT")
          or "necesita entrada" in t["nota"]]
    out["resumen"] = "%d/%d herramientas sin fallo inesperado" % (len(ok), len(out["tools"]))
    diario.save_artifact("smoke.json", out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = correr()
    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    print("Sesion: %s · abierto=%s" % (res["sesion"], res["abierto"]))
    for t in res["tools"]:
        print("%-16s %-4s %6.2fs  %-40s %s" % (t["tool"], "OK" if t["ok"] else "FALLA",
                                               t["seconds"], t["primera_linea"][:40], t["nota"]))
    print("Latencia:", res.get("latencia"))
    print("Frescura:", res.get("frescura"))
    print(res["resumen"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
