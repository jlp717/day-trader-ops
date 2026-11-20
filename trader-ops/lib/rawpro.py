"""Versión completa de la regla RAW: dirección + stop + objetivo + tamaño + filtros.

La version LITE solo dice COMPRA o VENTA. Esta añade lo que un trader necesita para
operar: donde esta el stop, cuanto se arriesga, cual es el objetivo y cuantas
acciones/contratos comprar. Ademas permite medir filtros (tendencia diaria, rango
de la primera vela, volumen relativo) para ver si mejoran la señal.

Nada de esto crea ventaja por si solo: se mide con `run/rawpro.py --variantes`.

Solo lectura. No envia ordenes.
"""
from . import raw


def _con_ema(bars, mercado):
    cfg = raw._cfg(mercado)
    tz = cfg["tz"]
    apertura = cfg["apertura"]
    grupos = raw._por_dia(raw.filtrar_sesion(bars, mercado), tz)
    ordenadas = [b for d in sorted(grupos) for b in grupos[d]]
    medias = raw.ema([float(b["c"]) for b in ordenadas])
    idx = {id(b): i for i, b in enumerate(ordenadas)}
    out = {}
    for dia in sorted(grupos):
        filas = grupos[dia]
        primera = next((b for b in filas if raw._local(b["t"], tz).time() == apertura), None)
        if primera is None:
            continue
        out[dia] = {"primera": primera, "ema": medias[idx[id(primera)]], "filas": filas,
                    "apertura": apertura}
    return out


def _volumen_relativo(dias, dia_actual, ventana=20):
    """Volumen de la primera vela frente a la media de las 20 anteriores."""
    fechas = [d for d in sorted(dias) if d < dia_actual][-ventana:]
    vols = [float(dias[d]["primera"].get("v") or 0) for d in fechas]
    vols = [v for v in vols if v > 0]
    if len(vols) < 5:
        return None
    media = sum(vols) / len(vols)
    actual = float(dias[dia_actual]["primera"].get("v") or 0)
    if media <= 0 or actual <= 0:
        return None
    return actual / media


def operar(bars, mercado="us", *, target_r=2.0, stop_buffer_pct=0.0,
           exit_mode="fixed", be_at_r=1.0, trail_r=1.0, cost_pct=0.0,
           tendencia=None, rango_min=None, rango_max=None, vol_min=None,
           gap_min=None, gap_max=None, pos_min=None, max_loss=50.0,
           min_risk_pct=0.20, max_notional=None, mercado_ok=None):
    """Simula la version completa. Devuelve lista de trades (solo largos).

    - stop: minimo de la primera vela (menos `stop_buffer_pct`).
    - objetivo: `target_r` veces el riesgo, o trailing si `exit_mode` lo pide.
    - tamano: `max_loss` / riesgo por accion, entero.
    - filtros opcionales: `tendencia` {fecha: bool}, rango % de la vela, volumen relativo.
    """
    dias = _con_ema(bars, mercado)
    fechas = sorted(dias)
    cierre_prev = {}
    for a, b in zip(fechas, fechas[1:]):
        cierre_prev[b] = float(dias[a]["filas"][-1]["c"])
    trades = []
    for dia in fechas:
        if mercado_ok is not None and not mercado_ok.get(dia.isoformat(), True):
            continue
        info = dias[dia]
        primera = info["primera"]
        c = float(primera["c"])
        e = info["ema"]
        if c <= e:                      # solo largos; sin direccion no se opera
            continue
        if tendencia is not None and not tendencia.get(dia.isoformat()):
            continue
        alto = float(primera.get("h") or c)
        bajo = float(primera.get("l") or c)
        rango_pct = ((alto - bajo) / c * 100.0) if c else 0.0
        if rango_min is not None and rango_pct < float(rango_min):
            continue
        if rango_max is not None and rango_pct > float(rango_max):
            continue
        if vol_min is not None:
            rel = _volumen_relativo(dias, dia)
            if rel is None or rel < float(vol_min):
                continue

        apertura_px = primera.get("o")
        if gap_min is not None or gap_max is not None:
            prev = cierre_prev.get(dia)
            if prev is None or apertura_px is None or prev <= 0:
                continue
            gap = (float(apertura_px) - prev) / prev * 100.0
            if gap_min is not None and gap < float(gap_min):
                continue
            if gap_max is not None and gap > float(gap_max):
                continue
        if pos_min is not None:
            if alto <= bajo:
                continue
            pos = (c - bajo) / (alto - bajo)
            if pos < float(pos_min):
                continue

        tz = raw._cfg(mercado)["tz"]
        despues = [b for b in info["filas"]
                   if raw._local(b["t"], tz).time() > info["apertura"]]
        if not despues:
            continue
        entrada_bar = despues[0]
        entry = float(entrada_bar.get("o") if entrada_bar.get("o") is not None
                      else entrada_bar.get("c"))
        if not entry:
            continue
        stop = bajo * (1.0 - abs(float(stop_buffer_pct)) / 100.0)
        riesgo = entry - stop
        # Un stop pegado al precio produce tamanos absurdos: se exige una distancia minima.
        minimo = entry * abs(float(min_risk_pct)) / 100.0
        if riesgo < minimo:
            stop = entry - minimo
            riesgo = minimo
        if riesgo <= 0:
            continue
        objetivo = entry + float(target_r) * riesgo
        qty = int(float(max_loss) / riesgo + 1e-9)
        if max_notional:
            tope = int(float(max_notional) // entry)
            qty = min(qty, tope)
        if qty <= 0:
            continue

        cur = stop
        hw = entry
        salida = None
        motivo = None
        for b in despues[1:]:
            o, h, l, cl = b.get("o"), b.get("h"), b.get("l"), b.get("c")
            if h is None or l is None:
                continue
            if o is not None and float(o) <= cur:
                salida, motivo = float(o), "stop_gap"
                break
            if exit_mode == "fixed" and o is not None and float(o) >= objetivo:
                salida, motivo = float(o), "objetivo_gap"
                break
            if float(l) <= cur:
                salida, motivo = cur, "stop"
                break
            if exit_mode == "fixed" and float(h) >= objetivo:
                salida, motivo = objetivo, "objetivo"
                break
            if exit_mode in ("be_trail", "trail"):
                hw = max(hw, float(h))
                avance = (hw - entry) / riesgo
                if avance >= float(be_at_r):
                    cur = max(cur, entry)
                    cur = max(cur, hw - float(trail_r) * riesgo)
        if salida is None:
            salida, motivo = float(despues[-1]["c"]), "cierre"
        bruto = (salida / entry - 1.0) * 100.0
        trades.append({
            "date": dia.isoformat(),
            "entry": round(entry, 2),
            "stop": round(stop, 2),
            "target": round(objetivo, 2),
            "qty": qty,
            "risk": round(riesgo, 3),
            "exit": round(salida, 2),
            "reason": motivo,
            "rango_pct": round(rango_pct, 2),
            "gross_pct": round(bruto, 3),
            "net_pct": round(bruto - float(cost_pct), 3),
            "r": round((salida - entry) / riesgo, 2),
        })
    return trades


def resumen(trades):
    n = len(trades)
    if not n:
        return {"n": 0, "win_rate": 0.0, "avg_net": 0.0, "total_net": 0.0,
                "avg_r": 0.0, "total_r": 0.0, "max_dd_r": 0.0}
    nets = [t["net_pct"] for t in trades]
    rs = [t["r"] for t in trades]
    eq = peak = dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {
        "n": n,
        "win_rate": sum(1 for x in nets if x > 0) / float(n),
        "avg_net": sum(nets) / n,
        "total_net": sum(nets),
        "avg_r": sum(rs) / n,
        "total_r": sum(rs),
        "max_dd_r": dd,
    }


def _sma(valores, n):
    out = [None] * len(valores)
    acc = 0.0
    for i, v in enumerate(valores):
        acc += float(v)
        if i >= n:
            acc -= float(valores[i - n])
        if i >= n - 1:
            out[i] = acc / n
    return out


def tendencia_diaria(symbol, desde=None, hasta=None, fuente="yahoo"):
    """{fecha: cierre del dia anterior > SMA200 de ese dia} sin mirar el futuro."""
    import datetime as dt
    from . import datos

    if str(fuente) == "alpaca":
        bars = raw.diarias_alpaca(symbol, desde or "2015-01-01", hasta)
    else:
        try:
            doc = datos.chart(symbol, "1y", "1d", ttl=6 * 3600)
        except Exception:
            return {}
        bars = [b for b in (doc.get("bars") or [])
                if b.get("c") is not None and b.get("t")]
    if len(bars) < 210:
        return {}
    cierres = [float(b["c"]) for b in bars]
    s200 = _sma(cierres, 200)
    out = {}
    prev = None
    for b, sma in zip(bars, s200):
        fecha = dt.datetime.fromtimestamp(int(b["t"]), tz=dt.timezone.utc).date().isoformat()
        if prev is not None:
            out[fecha] = prev
        prev = (float(b["c"]) > sma) if sma is not None else None
    return {k: v for k, v in out.items() if v is not None}


def bootstrap(trades, n=1000, seed=7):
    """Intervalo de confianza al 95 % de la media por operacion (bootstrap)."""
    import random
    vals = [t["net_pct"] for t in trades]
    if len(vals) < 10:
        return None
    rnd = random.Random(seed)
    medias = []
    for _ in range(int(n)):
        muestra = [rnd.choice(vals) for _ in range(len(vals))]
        medias.append(sum(muestra) / len(muestra))
    medias.sort()
    return {"media": sum(vals) / len(vals),
            "lo": medias[int(0.025 * len(medias))],
            "hi": medias[int(0.975 * len(medias))]}


def partir(trades, frac=0.7):
    fechas = sorted({t["date"] for t in trades})
    if len(fechas) < 2:
        return trades, []
    cut = max(1, min(len(fechas) - 1, int(round(len(fechas) * float(frac)))))
    dias = set(fechas[:cut])
    return ([t for t in trades if t["date"] in dias],
            [t for t in trades if t["date"] not in dias])
