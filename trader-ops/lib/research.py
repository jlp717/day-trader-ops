"""Mesa de research: fundamentales, noticias, analistas, insiders y tecnico.

No predice. Organiza la evidencia en cuatro vistas (como hace una mesa de
analisis), la enfrenta en toro/oso y devuelve escenarios con niveles, no con
certezas. El veredicto de corto plazo es el del trading; el de largo, el de la
tesis. Nunca decide el tamano de la posicion: eso es del modulo de riesgo.

Datos gratis: Finnhub (metricas, noticias, recomendaciones, insiders) y Yahoo
(precios diarios). Sin claves, las capas que dependen de Finnhub se omiten.
"""
from . import cfg
from . import datos
from . import tesis
from . import zonatiempo as zt

FINNHUB = "https://finnhub.io/api/v1"
CACHE = cfg.STATE / "research_cache.json"
TTL = 6 * 3600


def _key():
    return datos._finnhub_key() if hasattr(datos, "_finnhub_key") else None


def _get(path):
    key = _key()
    if not key:
        return None
    try:
        return datos.http_json_url(FINNHUB + path + ("&" if "?" in path else "?") + "token=" + key)
    except Exception:
        return None


def _cache(sym, clave, fn):
    doc = cfg.read_json(CACHE, {}) or {}
    fila = (doc.get(sym) or {}).get(clave) or {}
    if fila.get("ts") and (zt.now_utc().timestamp() - float(fila["ts"])) < TTL:
        return fila.get("datos")
    datos_ = fn()
    if datos_ is not None:
        doc.setdefault(sym, {})[clave] = {"ts": zt.now_utc().timestamp(), "datos": datos_}
        cfg.write_json(CACHE, doc)
    return datos_


def recomendaciones(symbol):
    """Consenso de analistas del ultimo mes: puntuacion -1..+1 y etiqueta."""
    sym = str(symbol).upper()

    def fetch():
        d = _get("/stock/recommendation?symbol=%s" % sym)
        if not isinstance(d, list) or not d:
            return None
        r = d[0]
        sb = float(r.get("strongBuy") or 0)
        b = float(r.get("buy") or 0)
        h = float(r.get("hold") or 0)
        s = float(r.get("sell") or 0)
        ss = float(r.get("strongSell") or 0)
        total = sb + b + h + s + ss
        if total <= 0:
            return None
        score = (2 * sb + b - s - 2 * ss) / (2 * total)
        etiqueta = ("compra fuerte" if score >= 0.5 else "compra" if score >= 0.15
                    else "venta fuerte" if score <= -0.5 else "venta" if score <= -0.15
                    else "neutral")
        return {"periodo": r.get("period"), "n": int(total), "score": round(score, 3),
                "etiqueta": etiqueta, "fuerte_compra": int(sb), "compra": int(b),
                "mantener": int(h), "venta": int(s), "fuerte_venta": int(ss)}

    return _cache(sym, "reco", fetch) or {}


def insiders(symbol, dias=90):
    """Compras y ventas de directivos en los ultimos `dias`."""
    sym = str(symbol).upper()

    def fetch():
        d = _get("/stock/insider-transactions?symbol=%s" % sym)
        filas = (d or {}).get("data") or []
        if not filas:
            return None
        corte = zt.madrid().date().toordinal() - int(dias)
        compras = ventas = 0.0
        n_c = n_v = 0
        for f in filas:
            fecha = str(f.get("transactionDate") or f.get("filingDate") or "")
            try:
                import datetime as dt
                if dt.date.fromisoformat(fecha[:10]).toordinal() < corte:
                    continue
            except Exception:
                pass
            cambio = float(f.get("change") or 0)
            if cambio > 0:
                compras += cambio
                n_c += 1
            elif cambio < 0:
                ventas += -cambio
                n_v += 1
        return {"compras": round(compras), "ventas": round(ventas),
                "n_compras": n_c, "n_ventas": n_v}

    return _cache(sym, "insiders", fetch) or {}


def analizar(symbol):
    """Informe completo: cuatro vistas, debate y escenarios."""
    sym = str(symbol).upper()
    try:
        e = tesis.estructura(sym)
    except Exception as exc:
        return {"symbol": sym, "error": str(exc)[:160]}
    f = tesis.fundamentos(sym)
    noticias = tesis.noticias(sym, limite=6)
    reco = recomendaciones(sym)
    insider = insiders(sym)
    t = tesis.evaluar(sym)

    # ── Vistas ──
    tecnico = {
        "tendencia": t["corto"]["veredicto"],
        "largo": t["largo"]["veredicto"],
        "rsi": e.get("rsi14"),
        "caida": e.get("drawdown_pct"),
        "sobre_sma200": bool(e.get("sma200") and e["close"] > e["sma200"]),
        "compresion": bool(t.get("largo") and t["largo"].get("score") is not None),
    }
    fundamental = {
        "ingresos": f.get("revenueGrowthTTMYoy"),
        "margen": f.get("netProfitMarginTTM"),
        "roe": f.get("roeTTM"),
        "per": f.get("peTTM"),
    }
    sentimiento = {
        "analistas": reco.get("etiqueta") if reco else None,
        "score": reco.get("score") if reco else None,
        "insiders_neto": (insider.get("compras", 0) - insider.get("ventas", 0)) if insider else None,
        "insiders": insider or None,
    }
    etiquetas = [tag for n in noticias for tag in (n.get("tags") or [])]
    negativo = sum(1 for x in etiquetas if x in ("downgrade", "riesgo", "empleo"))
    positivo = sum(1 for x in etiquetas if x in ("upgrade", "resultados", "acuerdo", "fusion"))

    # ── Debate ──
    toro, oso = [], []
    if tecnico["sobre_sma200"]:
        toro.append("precio sobre la SMA200")
    else:
        oso.append("precio bajo la SMA200")
    if e.get("sma50") and e.get("sma200") and e["sma50"] > e["sma200"]:
        toro.append("SMA50 sobre SMA200")
    else:
        oso.append("SMA50 bajo SMA200")
    if (e.get("drawdown_pct") or 0) <= -25:
        oso.append("caida de %.0f %% desde maximos" % abs(e["drawdown_pct"]))
    if (e.get("rsi14") or 50) < 30:
        toro.append("RSI %.0f: sobreventa" % e["rsi14"])
    if (e.get("rsi14") or 50) > 70:
        oso.append("RSI %.0f: sobrecompra" % e["rsi14"])
    if fundamental["ingresos"] is not None and float(fundamental["ingresos"]) > 0:
        toro.append("ingresos %+.1f %% interanual" % float(fundamental["ingresos"]))
    elif fundamental["ingresos"] is not None:
        oso.append("ingresos %+.1f %% interanual" % float(fundamental["ingresos"]))
    if fundamental["margen"] is not None:
        (toro if float(fundamental["margen"]) > 0 else oso).append(
            "margen neto %.1f %%" % float(fundamental["margen"]))
    if reco:
        (toro if reco["score"] > 0.15 else oso if reco["score"] < -0.15 else toro).append(
            "analistas: %s (%d)" % (reco["etiqueta"], reco["n"]))
    if insider and insider.get("compras", 0) + insider.get("ventas", 0) > 0:
        if insider["compras"] > insider["ventas"]:
            toro.append("insiders compran (%d ops)" % insider["n_compras"])
        else:
            oso.append("insiders venden (%d ops)" % insider["n_ventas"])
    if positivo > negativo:
        toro.append("noticias positivas %d vs %d negativas" % (positivo, negativo))
    elif negativo > positivo:
        oso.append("noticias negativas %d vs %d positivas" % (negativo, positivo))

    # ── Escenarios (niveles, no profecias) ──
    sma200 = e.get("sma200")
    low52 = e.get("low52")
    escenarios = []
    if sma200:
        escenarios.append({"nombre": "recuperacion", "nivel": round(sma200, 2),
                           "disparo": "cierre diario sobre la SMA200"})
    if low52:
        escenarios.append({"nombre": "ruptura", "nivel": round(low52, 2),
                           "disparo": "cierre diario bajo el minimo de 52 semanas"})
    escenarios.append({"nombre": "rango", "nivel": round(e["close"], 2),
                       "disparo": "entre los dos anteriores"})

    # ── Veredictos por horizonte ──
    corto = t["corto"]["veredicto"]
    largo = t["largo"]["veredicto"]
    medio = ("a favor" if tecnico["sobre_sma200"] and (e.get("rsi14") or 50) < 65
             else "en contra" if not tecnico["sobre_sma200"] else "neutral")
    return {
        "symbol": sym,
        "fecha": zt.madrid().date().isoformat(),
        "cierre": round(e["close"], 2),
        "tecnico": tecnico,
        "fundamental": fundamental,
        "sentimiento": sentimiento,
        "noticias": noticias,
        "toro": toro,
        "oso": oso,
        "escenarios": escenarios,
        "corto": corto,
        "medio": medio,
        "largo": largo,
        "regla_salida": ("en objetivo: 50% y resto tras SMA50 si la tesis sigue viva; "
                         "100% si esta en riesgo o rota"),
    }


def texto(symbol):
    r = analizar(symbol)
    if r.get("error"):
        return "Sin datos para %s: %s" % (symbol, r["error"])
    out = ["<b>Research %s</b> · %s · cierre %.2f" % (r["symbol"], r["fecha"], r["cierre"]),
           "Corto: %s · Medio: %s · Largo: %s" % (r["corto"].upper(), r["medio"].upper(),
                                                  r["largo"].upper()),
           "", "<b>Toro</b>"]
    out += ["  + " + x for x in r["toro"][:5]] or ["  (sin argumentos)"]
    out += ["", "<b>Oso</b>"]
    out += ["  - " + x for x in r["oso"][:5]] or ["  (sin argumentos)"]
    out += ["", "<b>Escenarios</b>"]
    for e in r["escenarios"]:
        out.append("  %s en %.2f (%s)" % (e["nombre"], e["nivel"], e["disparo"]))
    if r["sentimiento"].get("insiders"):
        i = r["sentimiento"]["insiders"]
        out.append("Insiders 90d: %d compras / %d ventas" % (i["n_compras"], i["n_ventas"]))
    out += ["", "Salida: " + r["regla_salida"]]
    out.append("No es una prediccion: es evidencia ordenada y niveles.")
    return "\n".join(out)
