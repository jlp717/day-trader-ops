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
    grupos = raw._por_dia(bars, tz)
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
           max_loss=50.0):
    """Simula la version completa. Devuelve lista de trades (solo largos).

    - stop: minimo de la primera vela (menos `stop_buffer_pct`).
    - objetivo: `target_r` veces el riesgo, o trailing si `exit_mode` lo pide.
    - tamano: `max_loss` / riesgo por accion, entero.
    - filtros opcionales: `tendencia` {fecha: bool}, rango % de la vela, volumen relativo.
    """
    dias = _con_ema(bars, mercado)
    trades = []
    for dia in sorted(dias):
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
        if riesgo <= 0:
            continue
        objetivo = entry + float(target_r) * riesgo
        qty = int(float(max_loss) // riesgo)
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


def partir(trades, frac=0.7):
    fechas = sorted({t["date"] for t in trades})
    if len(fechas) < 2:
        return trades, []
    cut = max(1, min(len(fechas) - 1, int(round(len(fechas) * float(frac)))))
    dias = set(fechas[:cut])
    return ([t for t in trades if t["date"] in dias],
            [t for t in trades if t["date"] not in dias])
