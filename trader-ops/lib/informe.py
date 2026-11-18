"""Informe diario y semanal. Lo que paso de verdad, contado sin adornos."""
import datetime as dt
import json
import statistics

from . import apertura
from . import cfg
from . import criterios
from . import datos
from . import diario
from . import posiciones
from . import registro
from . import texto
from . import zonatiempo as zt

HIST = cfg.OPS / "historico"
HIST.mkdir(parents=True, exist_ok=True)


def _bar_after(symbol, when_utc):
    """Barras de 5 min posteriores a la hora de la senal, del mismo dia."""
    doc = datos.chart(symbol, "1d", "5m", ttl=300)
    ts = int(when_utc.timestamp())
    return [b for b in doc["bars"] if b["t"] >= ts - 300]


def _resultado(symbol, plan, when_utc, flat_by_et="15:55"):
    """(resultado, precio, R) recorriendo las velas posteriores. Sin inventar."""
    bars = _bar_after(symbol, when_utc)
    if not bars:
        return "sin datos", None, None
    entry = float(plan.get("entry") or 0)
    stop = float(plan.get("stop") or 0)
    target = float(plan.get("target") or 0)
    risk = entry - stop
    for b in bars:
        if b["l"] is not None and b["l"] <= stop:
            r = -1.0
            return "stop tocado", round(stop, 2), r
        if b["h"] is not None and b["h"] >= target:
            r = (target - entry) / risk if risk else None
            return "objetivo tocado", round(target, 2), round(r, 3) if r else None
    last = bars[-1]["c"]
    r = (last - entry) / risk if risk else None
    return "cerrada al final", round(last, 2), round(r, 3) if r is not None else None


def generar(now=None, day=None):
    now = now or zt.now_utc()
    day = day or zt.madrid().date()
    cfgd = cfg.config()
    b = texto.Builder()
    b.line("<b>Informe de sesion</b> · %s" % zt.short_stamp(now))

    eventos = [e for e in diario.read_all() if e.get("ts_madrid", "").startswith(day.isoformat())]
    cmds = [e for e in eventos if e.get("event") == "cmd"]
    evals = [e for e in eventos if e.get("event") == "evaluacion"]
    senales = [s for s in registro.all_signals() if s.get("ts_madrid", "").startswith(day.isoformat())]
    a_ = [e for e in evals if e.get("veredicto") == "SEÑAL A"]
    v_ = [e for e in evals if e.get("veredicto") == "VIGILAR"]
    d_ = [e for e in evals if e.get("veredicto") == "DESCARTADA"]
    sin_datos = [e for e in evals if e.get("veredicto") in ("SIN DATOS", "FRENO", "SIN SEÑAL")]

    b.line("Valores analizados: %d · SEÑAL A: %d · VIGILAR: %d · DESCARTADAS: %d · sin señal/datos: %d" % (
        len({e.get("symbol") for e in evals}), len(a_), len(v_), len(d_), len(sin_datos)))

    # seleccion
    scans = [e for e in eventos if e.get("event") == "artifact" and e.get("name") == "scan_daily.json"]
    scan = diario.load_artifact("scan_daily.json", {}) or {}
    b.line("Sesgo de seleccion: scanner sobre %s valores, %s escaneados, %d candidatos, %d llegaron a evaluacion." % (
        scan.get("universe"), scan.get("scanned"), len(scan.get("hits") or []), len(evals)))

    # senales y resultado real
    if senales:
        b.blank()
        b.line("<b>Señales</b>")
        for s in senales:
            plan = s.get("plan") or {}
            res, px, r = _resultado(s["symbol"], plan, _utc(s.get("ts_utc")), plan.get("flat_by") or "15:55")
            b.line("  %s %s · entrada %s · stop %s · objetivo %s · resultado: %s (%s R)" % (
                s["symbol"], s.get("ts_madrid", "")[11:16], plan.get("entry"), plan.get("stop"),
                plan.get("target"), res, b.num(r or 0, 3, "r_real", signed=True)))
            if s.get("estado") == "abierta":
                estado = "stop" if res.startswith("stop") else "objetivo" if res.startswith("objetivo") else "cerrada"
                registro.close(s["id"], estado, px, nota="informe")
    else:
        b.line("Sin SEÑAL A hoy. Es un resultado valido: los filtros no se relajan.")

    # ganadoras descartadas
    ganadoras = []
    for e in evals:
        if e.get("veredicto") == "SEÑAL A" or not e.get("plan"):
            continue
        res, px, r = _resultado(e["symbol"], e["plan"], _utc(e.get("ts_utc")), e["plan"].get("flat_by") or "15:55")
        if res.startswith("objetivo"):
            ganadoras.append((e["symbol"], e.get("veredicto"), e.get("motivos") or []))
    if ganadoras:
        b.line("Descartadas/VIGILAR que habrian tocado objetivo: %s" % ", ".join(
            "%s (%s)" % (g[0], g[1]) for g in ganadoras))
    else:
        b.line("Ninguna descartada habria tocado el objetivo con los datos actuales.")

    # comparacion con el Time Machine
    if evals:
        pts = [e["numbers"].get("p_target_mc") for e in evals if e.get("numbers")]
        b.line("Time Machine medio de los evaluados: objetivo primero %s." % (
            "n/d" if not pts else "%.1f%%" % (100 * statistics.fmean(pts))))

    # coste de esperar real
    b.blank()
    b.line("<b>Coste de esperar (sesion de hoy)</b>")
    for sym in (cfgd.get("watch") or ["NVDA"])[:3]:
        try:
            res = apertura.analizar(sym)
            if res.get("ok"):
                g = res["gap_pct"]
                r15 = res["ret_15m_pct"]
                b.line("  %s: hueco %s%%, primeros 15 min %s%%, %s%% del movimiento del dia en 15 min" % (
                    sym, _f(g.get("mediana")), _f(r15.get("mediana")),
                    _f(res["primeros_15m_del_movimiento_pct"].get("mediana"))))
            else:
                b.line("  %s: %s" % (sym, res.get("motivo")))
        except Exception as exc:
            b.line("  %s: no disponible (%s)" % (sym, exc))

    # latencias y fallos
    if cmds:
        times = sorted(float(c.get("seconds") or 0) for c in cmds)
        b.line("Comandos ejecutados: %d · latencia mediana %.2f s · maxima %.2f s" % (
            len(cmds), statistics.median(times), times[-1]))
    errs = [e for e in eventos if e.get("event") in ("error", "telegram_error", "validacion_fallida")]
    b.line("Fallos registrados: %d%s" % (len(errs), (": " + "; ".join(
        str(e.get("where") or e.get("symbol") or "") for e in errs[:3])) if errs else ""))

    # posiciones
    pnl = posiciones.pnl()
    if pnl["operaciones"]:
        b.line("Posiciones cerradas a mano: %d · PnL %+.2f USD · R total %+.2f" % (
            pnl["operaciones"], pnl["pnl_usd"], pnl["r_total"]))

    st = registro.stats()
    b.line("Registro vivo: %d señales, %d cerradas, %d objetivos, %d stops, R medio %+.2f." % (
        st["total"], st["cerradas"], st["objetivos"], st["stops"], st["r_medio"]))
    freno, motivo = registro.freno_activo()
    b.line("Freno por evidencia: %s (%s)." % ("ACTIVO" if freno else "no activo", motivo))
    b.line("Conclusion honesta: %s" % _conclusion(a_, d_, senales, errs))
    b.line("PRUEBA EN PAPEL · nada de esto es una recomendacion.")

    payload = b.payload()
    doc = {"date": day.isoformat(), "texto": payload["texto"], "payload": payload,
           "senales": len(a_), "vigilar": len(v_), "descartadas": len(d_), "evaluados": len(evals)}
    cfg.write_json(HIST / ("%s.json" % day.isoformat()), doc)
    with open(HIST / "index.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": day.isoformat(), "senales": len(a_),
                             "evaluados": len(evals), "fallos": len(errs)}) + "\n")
    return doc


def _conclusion(a_, d_, senales, errs):
    if errs:
        return "hubo fallos tecnicos; antes de sacar conclusiones hay que arreglarlos."
    if not senales:
        return ("no hubo señal; el sistema prefirio no avisar. Eso no es exito ni fracaso: "
                "es la ausencia de una configuracion que supere los filtros.")
    if not a_:
        return "se evaluo pero nada paso los filtros; revisar si los umbrales son alcanzables."
    return "hubo señal y su resultado esta arriba medido en R; con esta muestra no se concluye nada."


def _utc(iso):
    try:
        return dt.datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except Exception:
        return zt.now_utc()


def _f(x):
    return "n/d" if x is None else "%.2f" % float(x)


def semanal(now=None):
    now = now or zt.now_utc()
    day = now.date()
    rows = []
    for i in range(7):
        d = day - dt.timedelta(days=i)
        p = HIST / ("%s.json" % d.isoformat())
        if p.exists():
            rows.append(cfg.read_json(p, {}) or {})
    st = registro.stats()
    pnl = posiciones.pnl()
    total = sum(r.get("evaluados", 0) for r in rows)
    senales = sum(r.get("senales", 0) for r in rows)
    por_setup, por_hora = rendimiento()
    extra = ""
    if por_setup:
        extra += "\nPor setup: " + ", ".join("%s %d (R %+.2f)" % (k, v["n"], v["r"])
                                             for k, v in sorted(por_setup.items()))
    if por_hora:
        extra += "\nPor hora (Madrid): " + ", ".join("%s %d" % (k, v["n"])
                                                     for k, v in sorted(por_hora.items()))
    return ("<b>Resumen semanal</b> · %s\n"
            "Dias con informe: %d · valores evaluados: %d · SEÑAL A: %d\n"
            "Registro vivo: %d cerradas, %d objetivos, %d stops, R medio %+.2f\n"
            "Posiciones a mano: %d cerradas, PnL %+.2f USD%s\n"
            "PRUEBA EN PAPEL · informativo, no cambia filtros" % (
                zt.human(now, zt.MADRID), len(rows), total, senales,
                st["cerradas"], st["objetivos"], st["stops"], st["r_medio"],
                pnl["operaciones"], pnl["pnl_usd"], extra))


def rendimiento():
    """Rendimiento por setup y por hora de Madrid. Informativo, con muestra."""
    por_setup, por_hora = {}, {}
    for s in registro.all_signals():
        if s.get("estado") not in ("objetivo", "stop", "cerrada"):
            continue
        setup = (s.get("plan") or {}).get("setup") or "?"
        hora = (s.get("ts_madrid") or "")[11:13] + ":00"
        r = float(s.get("R") or 0)
        for bucket, key in ((por_setup, setup), (por_hora, hora)):
            d = bucket.setdefault(key, {"n": 0, "r": 0.0})
            d["n"] += 1
            d["r"] = round(d["r"] + r, 3)
    return por_setup, por_hora
