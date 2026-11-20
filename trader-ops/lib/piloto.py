"""Piloto de papel: convierte la ultima SEÑAL A en una orden bracket PAPEL.

No toca MyInvestor, no usa dinero real y no se ejecuta solo: el CLI exige --confirm.
"""
from . import brokers, registro, zonatiempo as zt


def ultima_senal():
    hoy = zt.madrid().date().isoformat()
    abiertas = [s for s in registro.all_signals()
                if s.get("estado") == "abierta" and str(s.get("ts_madrid", "")).startswith(hoy)]
    return abiertas[-1] if abiertas else None


def propuesta(senal):
    if not senal:
        raise ValueError("no hay SEÑAL A abierta")
    plan = senal.get("plan") or {}
    qty = int(float(senal.get("shares") or 0))
    entry = float(plan.get("entry") or 0)
    stop = float(plan.get("stop") or 0)
    target = float(plan.get("target") or 0)
    if qty <= 0 or not (stop < entry < target):
        raise ValueError("plan invalido: qty/stop/entry/target")
    return {"signal_id": senal.get("id"), "symbol": senal.get("symbol"),
            "qty": qty, "entry": entry, "stop": stop, "target": target}


def ejecutar(senal, broker=None, confirm=False):
    p = propuesta(senal)
    if not confirm:
        return {"dry": True, "propuesta": p}
    b = broker or brokers.get("alpaca_paper")
    fn = getattr(b, "bracket", None)
    if not fn:
        raise ValueError("el broker %s no soporta bracket" % getattr(b, "nombre", "?"))
    key = "piloto:%s" % p["signal_id"]
    res = fn(p["symbol"], p["qty"], limit=p["entry"], stop=p["stop"],
             target=p["target"], key=key)
    return {"dry": False, "propuesta": p, "orden": res}
