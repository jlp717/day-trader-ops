"""Cliente minimo del Client Portal Web API de Interactive Brokers, SOLO PAPEL.

Requiere el Gateway de IBKR abierto en el equipo (por defecto https://localhost:5000)
y la sesion iniciada. La cuenta de papel de IBKR empieza por **DU**: si la cuenta no
empieza por DU, este cliente se niega a enviar cualquier orden. No hay endpoint real
en el codigo y no se envia nada sin `confirm` en la capa de arriba.

Configuracion (opcional) en `secrets/ibkr.json`:

    {"account_id": "DU1234567", "base_url": "https://localhost:5000/v1/api", "paper": true}

Nunca se guardan credenciales de IBKR: el Gateway es quien tiene la sesion.
"""
import http.cookiejar
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

from . import cfg

DEFAULT_BASE = "https://localhost:5000/v1/api"


class IBKRError(Exception):
    pass


def _conf():
    return cfg.read_json(cfg.ROOT / "secrets" / "ibkr.json", {}) or {}


def base_url():
    return (os.environ.get("IBKR_BASE_URL") or _conf().get("base_url")
            or DEFAULT_BASE).rstrip("/")


def account_id():
    return str(os.environ.get("IBKR_ACCOUNT") or _conf().get("account_id") or "").strip()


_OPENER = None


def _opener():
    """Cookie jar + certificado del gateway local (autofirmado) sin verificar."""
    global _OPENER
    if _OPENER is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        jar = http.cookiejar.CookieJar()
        _OPENER = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ctx),
            urllib.request.HTTPCookieProcessor(jar))
    return _OPENER


def _req(method, path, body=None, timeout=15):
    url = base_url() + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "day-trader-ops/1.0",
    })
    try:
        with _opener().open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detalle = exc.read()[:200].decode("utf-8", "replace")
        raise IBKRError("HTTP %s en %s: %s" % (exc.code, path, detalle))
    except Exception as exc:
        raise IBKRError("sin conexion con IBKR en %s (%s)" % (base_url(), exc))
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        raise IBKRError("respuesta no JSON en %s" % path)


def estado():
    return _req("GET", "/iserver/auth/status")


def cuentas():
    doc = _req("GET", "/portfolio/accounts")
    return doc if isinstance(doc, list) else [doc]


def es_papel(account):
    """Una cuenta de papel de IBKR empieza por DU. Se niega cualquier otra."""
    cuenta = str(account or "").upper()
    if not cuenta.startswith("DU"):
        raise IBKRError("cuenta '%s' no es de papel: debe empezar por DU" % (cuenta or "?"))
    return True


def conid(symbol):
    sym = str(symbol or "").upper().strip()
    if not sym:
        raise IBKRError("simbolo vacio")
    doc = _req("GET", "/iserver/secdef/search?symbol=%s" % urllib.parse.quote(sym))
    for fila in (doc if isinstance(doc, list) else []):
        if fila.get("conid"):
            return int(fila["conid"])
    raise IBKRError("IBKR no devolvio conid para %s" % sym)


def posiciones(account=None):
    cuenta = account or account_id()
    es_papel(cuenta)
    return _req("GET", "/portfolio/%s/positions" % cuenta)


def orden(account, symbol, side, qty, limit=None, tif="DAY"):
    """Orden limitada o de mercado en cuenta de PAPEL. Devuelve la respuesta cruda."""
    cuenta = account or account_id()
    es_papel(cuenta)
    qty = float(qty)
    if qty <= 0:
        raise IBKRError("cantidad invalida")
    lado = str(side or "").upper()
    if lado not in ("BUY", "SELL"):
        raise IBKRError("lado invalido: %s" % side)
    cuerpo = {
        "conid": conid(symbol),
        "side": lado,
        "orderType": "LMT" if limit is not None else "MKT",
        "quantity": qty,
        "tif": str(tif or "DAY").upper(),
    }
    if limit is not None:
        cuerpo["price"] = round(float(limit), 4)
    return _req("POST", "/iserver/account/%s/orders" % cuenta, [cuerpo])


def confirmar(respuesta):
    """Confirma los mensajes de replica de IBKR (order reply). Devuelve la respuesta."""
    if not isinstance(respuesta, list):
        return respuesta
    for item in respuesta:
        rid = (item or {}).get("id")
        if rid:
            return _req("POST", "/iserver/reply/%s" % rid, {"confirmed": True})
    return respuesta
