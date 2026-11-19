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
                    min_price=5.0):
        """Devuelve un trade (dict) o None. `bars` = barras ordenadas de ese dia NY."""
        orb = [b for b in bars if OR_INI <= ny(b["t"]).time() < OR_FIN
               and b.get("h") is not None and b.get("l") is not None]
        if len(orb) < 3:
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
            if t < OR_FIN:
                continue
            if t >= ENTRADA_FIN:
                break
            c = b.get("c")
            if c is not None and float(c) > high:
                entry = float(c)
                idx = i
                break
        if entry is None or entry < float(min_price):
            return None

        risk = entry - mid
        if risk <= 0 or risk / entry < 0.0005:
            return None
        target = cent(entry + 2.0 * risk)
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
            if o is not None and float(o) <= mid:
                exit_px, exit_reason, exit_bar = float(o), "stop_gap", b
                break
            if o is not None and float(o) >= target:
                exit_px, exit_reason, exit_bar = float(o), "target_gap", b
                break
            hit_stop = float(l) <= mid
            hit_target = float(h) >= target
            if hit_stop and hit_target:
                # Conservador: si en la misma barra toca los dos, asumimos stop.
                exit_px, exit_reason, exit_bar = mid, "stop_mismo_bar", b
                break
            if hit_stop:
                exit_px, exit_reason, exit_bar = mid, "stop", b
                break
            if hit_target:
                exit_px, exit_reason, exit_bar = target, "target", b
                break
            if t >= FLAT:
                exit_px, exit_reason, exit_bar = float(c), "flat", b
                break
        if exit_px is None:
            last = bars[-1]
            if last.get("c") is None:
                return None
            exit_px, exit_reason, exit_bar = float(last["c"]), "eod", last

        gross_r = (exit_px - entry) / risk
        cost = float(comision_fn(entry * qty)) if comision_fn else 0.0
        cost_r = cost / (qty * risk) if qty and risk else 0.0
        return {
            "symbol": symbol.upper(),
            "date": day.isoformat(),
            "or_high": round(high, 2),
            "or_low": round(low, 2),
            "or_mid": round(mid, 2),
            "entry": round(entry, 2),
            "stop": round(mid, 2),
            "target": round(target, 2),
            "qty": qty,
            "risk": round(risk, 4),
            "exit": round(exit_px, 2),
            "exit_reason": exit_reason,
            "entry_time": _hora(bars[idx], True),
            "exit_time": _hora(exit_bar, exit_reason not in ("stop_gap", "target_gap")),
            "gross_r": round(gross_r, 4),
            "net_r": round(gross_r - cost_r, 4),
            "cost_usd": round(cost, 2),
            "pnl_usd": round(qty * (exit_px - entry) - cost, 2),
        }


REGISTRO = {"orb": ORB()}


def get(nombre="orb"):
    return REGISTRO.get(str(nombre).lower()) or REGISTRO["orb"]


def nombres():
    return sorted(REGISTRO)
