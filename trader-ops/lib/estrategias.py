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
                    entry_cutoff=ENTRADA_FIN, flat=FLAT, slippage_bps=0.0,
                    exit_mode="fixed", be_at_r=1.0, trail_r=1.0):
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

        exit_px, exit_reason, exit_bar = self._salida(
            bars, idx, stop, target, flat, entry=entry, mode=exit_mode,
            be_at_r=be_at_r, trail_r=trail_r)
        if exit_px is None:
            return None
        return self._ficha(symbol, day, high, low, mid, entry, stop, target, qty,
                           bars[idx], exit_px, exit_reason, exit_bar,
                           comision_fn=comision_fn, slippage_bps=slippage_bps)

    def _salida(self, bars, idx, stop, target, flat, *, entry=None,
                mode="fixed", be_at_r=1.0, trail_r=1.0):
        """(precio, motivo, barra) de salida, o (None, None, None) si no hay datos.

        mode="fixed": stop y objetivo fijos (comportamiento original).
        mode="be_trail": al llegar a `be_at_r` R mueve el stop a la entrada y luego
        lo persigue a `trail_r` R por debajo del maximo alcanzado.
        mode="trail": persigue desde el primer momento (sin objetivo fijo).

        El stop se actualiza con el maximo de la barra anterior y se comprueba con
        el minimo de la siguiente: conservador, nunca asume el mejor orden posible.
        """
        modo = str(mode or "fixed").lower()
        usar_trailing = modo in ("be_trail", "trail") and entry is not None
        cur = float(stop)
        hw = float(entry) if entry is not None else None
        risk = (float(entry) - float(stop)) if entry is not None else None
        exit_px = exit_reason = exit_bar = None
        for b in bars[idx + 1:]:
            o = b.get("o")
            h = b.get("h")
            l = b.get("l")
            c = b.get("c")
            if h is None or l is None:
                continue
            t = ny(b["t"]).time()
            # Hueco: el open ya esta fuera del stop o del objetivo.
            if o is not None and float(o) <= cur:
                exit_px, exit_reason, exit_bar = float(o), "stop_gap", b
                break
            if not usar_trailing and o is not None and float(o) >= target:
                exit_px, exit_reason, exit_bar = float(o), "target_gap", b
                break
            hit_stop = float(l) <= cur
            hit_target = (not usar_trailing) and float(h) >= target
            if hit_stop and hit_target:
                # Conservador: si en la misma barra toca los dos, asumimos stop.
                exit_px, exit_reason, exit_bar = cur, "stop_mismo_bar", b
                break
            if hit_stop:
                exit_px, exit_reason, exit_bar = cur, "stop", b
                break
            if hit_target:
                exit_px, exit_reason, exit_bar = target, "target", b
                break
            if usar_trailing and risk and risk > 0:
                hw = max(hw, float(h))
                avance = (hw - float(entry)) / risk
                if avance >= float(be_at_r):
                    cur = max(cur, float(entry))
                    cur = max(cur, hw - float(trail_r) * risk)
            if t >= flat:
                exit_px, exit_reason, exit_bar = float(c), "flat", b
                break
        if exit_px is None:
            last = bars[-1]
            if last.get("c") is None:
                return None, None, None
            exit_px, exit_reason, exit_bar = float(last["c"]), "eod", last
        return exit_px, exit_reason, exit_bar

    def _ficha(self, symbol, day, ref_high, ref_low, ref_mid, entry, stop, target,
               qty, entry_bar, exit_px, exit_reason, exit_bar, *,
               comision_fn=None, slippage_bps=0.0, extra=None):
        """Trade con el mismo esquema para todas las estrategias."""
        risk = entry - stop
        bps = max(0.0, float(slippage_bps or 0.0))
        entry_fill = entry * (1.0 + bps / 10000.0)
        exit_fill = exit_px * (1.0 - bps / 10000.0)
        gross_r = (exit_fill - entry_fill) / risk
        cost = float(comision_fn(entry_fill * qty)) if comision_fn else 0.0
        cost_r = cost / (qty * risk) if qty and risk else 0.0
        out = {
            "symbol": symbol.upper(),
            "date": day.isoformat(),
            "or_high": round(ref_high, 2),
            "or_low": round(ref_low, 2),
            "or_mid": round(ref_mid, 2),
            "entry": round(entry, 2),
            "entry_fill": round(entry_fill, 4),
            "stop": round(stop, 2),
            "target": round(target, 2),
            "qty": qty,
            "risk": round(risk, 4),
            "exit": round(exit_px, 2),
            "exit_fill": round(exit_fill, 4),
            "exit_reason": exit_reason,
            "entry_time": _hora(entry_bar, True),
            "exit_time": _hora(exit_bar, exit_reason not in ("stop_gap", "target_gap")),
            "gross_r": round(gross_r, 4),
            "net_r": round(gross_r - cost_r, 4),
            "cost_usd": round(cost, 2),
            "pnl_usd": round(qty * (exit_fill - entry_fill) - cost, 2),
        }
        if extra:
            out.update(extra)
        return out


class ORBBajo(ORB):
    """Variante del ORB con stop en el minimo del rango, no en el mid."""

    nombre = "orb_low"

    def simular_dia(self, *args, **kwargs):
        kwargs.setdefault("stop_rule", "low")
        return super().simular_dia(*args, **kwargs)


class GapReclaim(ORB):
    """Hueco a la baja + recuperacion: compra el cierre que supera la primera barra.

    Tesis: quien vendio en el hueco de apertura queda atrapado si el precio recupera el
    maximo de la primera barra; el objetivo natural es cerrar el hueco (cierre previo).
    Solo largo, una entrada por dia, stop en el minimo del dia hasta la entrada.
    """

    nombre = "gap_reclaim"
    necesita_prev_close = True
    GAP_MIN_PCT = 1.5
    MIN_ROOM_R = 0.8

    def simular_dia(self, symbol, day, bars, *, max_loss=50.0, comision_fn=None,
                    min_price=5.0, or_minutes=15, target_r=2.0, stop_rule="mid",
                    entry_cutoff=ENTRADA_FIN, flat=FLAT, slippage_bps=0.0,
                    prev_close=None, gap_min_pct=None, min_room_r=None,
                    exit_mode="fixed", be_at_r=1.0, trail_r=1.0):
        if prev_close is None or len(bars) < 3:
            return None
        prev_close = float(prev_close)
        if prev_close <= 0:
            return None
        first = bars[0]
        o, h = first.get("o"), first.get("h")
        if o is None or h is None:
            return None
        o, h = float(o), float(h)
        if o < float(min_price):
            return None
        gap_pct = (o - prev_close) / prev_close * 100.0
        gmin = self.GAP_MIN_PCT if gap_min_pct is None else abs(float(gap_min_pct))
        if gap_pct > -gmin:
            return None

        trigger = h
        entry = idx = stop = None
        for i, b in enumerate(bars[1:], start=1):
            if ny(b["t"]).time() >= entry_cutoff:
                break
            c = b.get("c")
            if c is not None and float(c) > trigger:
                lows = [float(x["l"]) for x in bars[:i + 1] if x.get("l") is not None]
                if not lows:
                    return None
                entry, idx, stop = float(c), i, cent_down(min(lows))
                break
        if entry is None or stop is None or stop >= entry:
            return None
        if entry < float(min_price):
            return None
        risk = entry - stop
        if risk <= 0 or risk / entry < 0.0005:
            return None

        target = cent_down(prev_close)
        room = (target - entry) / risk
        umbral = self.MIN_ROOM_R if min_room_r is None else float(min_room_r)
        if room < umbral:
            return None
        qty = int(float(max_loss) // risk)
        if qty <= 0:
            return None

        exit_px, exit_reason, exit_bar = self._salida(
            bars, idx, stop, target, flat, entry=entry, mode=exit_mode,
            be_at_r=be_at_r, trail_r=trail_r)
        if exit_px is None:
            return None
        return self._ficha(symbol, day, trigger, stop, prev_close, entry, stop, target,
                           qty, bars[idx], exit_px, exit_reason, exit_bar,
                           comision_fn=comision_fn, slippage_bps=slippage_bps,
                           extra={"prev_close": round(prev_close, 2),
                                  "gap_pct": round(gap_pct, 2),
                                  "room_r": round(room, 2)})


REGISTRO = {"orb": ORB(), "orb_low": ORBBajo(), "gap_reclaim": GapReclaim()}


def get(nombre="orb"):
    return REGISTRO.get(str(nombre).lower()) or REGISTRO["orb"]


def nombres():
    return sorted(REGISTRO)
