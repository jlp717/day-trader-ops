"""Cliente minimo de Alpaca en modo PAPEL (paper-api) y datos IEX.

Nunca usa el endpoint real. Las claves viven en secrets/alpaca.json o en las
variables ALPACA_KEY / ALPACA_SECRET. Sin claves, cualquier llamada falla.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import cfg

PAPER = "https://paper-api.alpaca.markets"
DATA = "https://data.alpaca.markets"
UA = "day-trader-ops/1.0 (paper)"


class AlpacaError(Exception):
    pass


def keys():
    k = os.environ.get("ALPACA_KEY")
    s = os.environ.get("ALPACA_SECRET")
    if k and s:
        return k.strip(), s.strip()
    p = cfg.ROOT / "secrets" / "alpaca.json"
    if p.exists():
        doc = cfg.read_json(p, {}) or {}
        k = (doc.get("api_key") or doc.get("key") or "").strip()
        s = (doc.get("secret_key") or doc.get("secret") or "").strip()
        if k and s and "PEGA" not in k.upper() and "PEGA" not in s.upper():
            return k, s
    raise AlpacaError("faltan claves validas: secrets/alpaca.json o ALPACA_KEY/ALPACA_SECRET")


def _request(base, method, path, body=None, params=None):
    k, s = keys()
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "APCA-API-KEY-ID": k,
        "APCA-API-SECRET-KEY": s,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": UA,
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", "replace")
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise AlpacaError("HTTP %d %s" % (exc.code, detail))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise AlpacaError("Alpaca no responde: %s" % exc)


def paper_request(method, path, body=None, params=None):
    if not PAPER.startswith("https://paper-api."):
        raise AlpacaError("endpoint de papel no valido")
    return _request(PAPER, method, path, body=body, params=params)


def data_request(path, params=None):
    return _request(DATA, "GET", path, params=params)
