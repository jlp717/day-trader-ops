"""Estrategias simulables sobre barras de 5 minutos.

Solo mecanica de precio: no toca el pipeline vivo, no envia nada y no conoce
noticias ni Time Machine. El backtest usa estas funciones para medir el patron
bruto antes de anadir capas.
"""
import datetime as dt
import math
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

OR_INI = dt.time(9, 30)
OR_FIN = dt.time(9, 45)
ENTRADA_FIN = dt.time(15, 30)
FLAT = dt.time(15, 50)          # barra que cierra a las 15:55 ET


def ny(ts):
    return dt.datetime.fromtimestamp(int(ts), tz=NY)


def cent_down(x):
    return math.floor(float(x) * 100 + 1e-9) / 100.0


def cent(x):
    return math.floor(float(x) * 100 + 0.5 + 1e-9) / 100.0


def _hora(bar, cierre=True):
    t = ny(bar["t"])
    if cierre:
        t += dt.timedelta(minutes=5)
    return t.strftime("%H:%M")


class ORB:
    """Opening Range Breakout: rango 9:30-9:45, entrada al primer cierre por encima."""

    nombre = "orb"

    def simular_dia(self, symbol, day, bars, *, max_loss=50.0, comision_fn=None,
                    min_price=5.0, or_minutes=15, target_r=2.0, stop_rule="mid",
                    entry_cutoff=ENTRADA_FIN, flat=FLAT, slippage_bps=0.0):
        """Devuelve un trade (dict) o None. `bars` = barras ordenadas de ese dia NY."""
        minutos = max(5, int(or_minutes))
        n_or = max(1, minutos // 5)
        or_fin = (dt.datetime.combine(day, OR_INI) + dt.timedelta(minutes=minutos)).time()
        orb = [b for b in bars if OR_INI <= ny(b["t"]).time() < or_fin
               and b.get("h") is not None and b.get("l") is not None]
        if len(orb) < n_or:
            return None
        high = max(float(b["h"]) for b in orb)
        low = min(float(b["l"]) for b in orb)
        if high <= low:
            return None
        mid = cent_down((high + low) / 2.0)

        entry = None
        idx = None
        for i, b in enumerate(bars):
            t = ny(b["t"]).time()
            if t < or_fin:
                continue
            if t >= entry_cutoff:
                break
            c = b.get("c")
            if c is not None and float(c) > high:
                entry = float(c)
                idx = i
                break
        if entry is None or entry < float(min_price):
            return None

        stop = cent_down(low) if str(stop_rule).lower() == "low" else mid
        risk = entry - stop
        if risk <= 0 or risk / entry < 0.0005:
            return None
        target = cent(entry + float(target_r) * risk)
        qty = int(float(max_loss) // risk)
        if qty <= 0:
            return None

        exit_px = None
        exit_reason = None
        exit_bar = None
        for b in bars[idx + 1:]:
            o = b.get("o")
            h = b.get("h")
            l = b.get("l")
            c = b.get("c")
            if h is None or l is None:
                continue
            t = ny(b["t"]).time()
            # Hueco: el open ya esta fuera del stop o del objetivo.
            if o is not None and float(o) <= stop:
                exit_px, exit_reason, exit_bar = float(o), "stop_gap", b
                break
            if o is not None and float(o) >= target:
                exit_px, exit_reason, exit_bar = float(o), "target_gap", b
                break
            hit_stop = float(l) <= stop
            hit_target = float(h) >= target
            if hit_stop and hit_target:
                # Conservador: si en la misma barra toca los dos, asumimos stop.
                exit_px, exit_reason, exit_bar = stop, "stop_mismo_bar", b
                break
            if hit_stop:
                exit_px, exit_reason, exit_bar = stop, "stop", b
                break
            if hit_target:
                exit_px, exit_reason, exit_bar = target, "target", b
                break
            if t >= flat:
                exit_px, exit_reason, exit_bar = float(c), "flat", b
                break
        if exit_px is None:
            last = bars[-1]
            if last.get("c") is None:
                return None
            exit_px, exit_reason, exit_bar = float(last["c"]), "eod", last

        bps = max(0.0, float(slippage_bps or 0.0))
        entry_fill = entry * (1.0 + bps / 10000.0)
        exit_fill = exit_px * (1.0 - bps / 10000.0)
        gross_r = (exit_fill - entry_fill) / risk
        cost = float(comision_fn(entry_fill * qty)) if comision_fn else 0.0
        cost_r = cost / (qty * risk) if qty and risk else 0.0
        return {
            "symbol": symbol.upper(),
            "date": day.isoformat(),
            "or_high": round(high, 2),
            "or_low": round(low, 2),
            "or_mid": round(mid, 2),
            "entry": round(entry, 2),
            "entry_fill": round(entry_fill, 4),
            "stop": round(stop, 2),
            "target": round(target, 2),
            "qty": qty,
            "risk": round(risk, 4),
            "exit": round(exit_px, 2),
            "exit_fill": round(exit_fill, 4),
            "exit_reason": exit_reason,
            "entry_time": _hora(bars[idx], True),
            "exit_time": _hora(exit_bar, exit_reason not in ("stop_gap", "target_gap")),
            "gross_r": round(gross_r, 4),
            "net_r": round(gross_r - cost_r, 4),
            "cost_usd": round(cost, 2),
            "pnl_usd": round(qty * (exit_fill - entry_fill) - cost, 2),
        }


class ORBBajo(ORB):
    """Variante del ORB con stop en el minimo del rango, no en el mid."""

    nombre = "orb_low"

    def simular_dia(self, *args, **kwargs):
        kwargs.setdefault("stop_rule", "low")
        return super().simular_dia(*args, **kwargs)


REGISTRO = {"orb": ORB(), "orb_low": ORBBajo()}


def get(nombre="orb"):
    return REGISTRO.get(str(nombre).lower()) or REGISTRO["orb"]


def nombres():
    return sorted(REGISTRO)
