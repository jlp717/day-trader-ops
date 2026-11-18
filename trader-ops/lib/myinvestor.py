"""Cliente minimo del MCP oficial de MyInvestor (solo lectura).

Endpoint: https://mcp.myinvestor.es/mcp  (JSON-RPC 2.0 sobre HTTP, respuestas SSE)
Herramientas usadas: search_stocks, get_instruments, compare_instruments.

Sirve para comprobar que un valor es contratable y en que mercados y divisas cotiza,
que es justo lo que pide el diseno. Nunca envia ordenes: el servidor no las tiene.
"""
import json
import time
import urllib.error
import urllib.request

from . import cfg

URL = "https://mcp.myinvestor.es/mcp"
UA = "day-trader-ops/1.0 (paper testing)"
CACHE_TTL = 6 * 3600
_id = [0]


class MyInvestorError(Exception):
    pass


def _rpc(method, params=None, timeout=25):
    _id[0] += 1
    body = json.dumps({"jsonrpc": "2.0", "id": _id[0], "method": method,
                       "params": params or {}}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        raise MyInvestorError("MCP MyInvestor no responde: %s" % exc)
    if raw.lstrip().startswith("event:"):
        data = []
        for line in raw.splitlines():
            if line.startswith("data:"):
                data.append(line[5:].strip())
        raw = "\n".join(data)
    try:
        doc = json.loads(raw)
    except ValueError:
        raise MyInvestorError("respuesta no JSON del MCP")
    if doc.get("error"):
        raise MyInvestorError("MCP: %s" % (doc["error"].get("message") or doc["error"]))
    return doc.get("result") or {}


def _texto(result):
    out = []
    for c in result.get("content") or []:
        if c.get("type") == "text" and c.get("text"):
            out.append(c["text"])
    return "\n".join(out)


def _cache_key(ticker):
    return cfg.CACHE / ("myinvestor_%s.json" % ticker.upper().replace("/", "_"))


def _cache_get(ticker):
    doc = cfg.read_json(_cache_key(ticker), None)
    if not doc or time.time() - float(doc.get("fetched_at") or 0) > CACHE_TTL:
        return None
    return doc.get("payload")


def _cache_put(ticker, payload):
    cfg.write_json(_cache_key(ticker), {"fetched_at": time.time(), "payload": payload})


def ficha(ticker, forzar=False):
    """Ficha del valor segun el catalogo de MyInvestor. Cache 6 h."""
    t = ticker.upper().strip()
    if not forzar:
        hit = _cache_get(t)
        if hit:
            return hit
    res = _rpc("tools/call", {"name": "get_instruments", "arguments": {"tickers": [t]}})
    texto = _texto(res)
    payload = {"ticker": t, "texto": texto, "encontrado": ("(%s," % t) in texto or t in texto.split("\n")[0],
               "is_error": bool(res.get("isError")), "fuente": URL}
    _cache_put(t, payload)
    return payload


def contratable(ticker):
    """{ok, mercados, monedas, nota, fuente}. ok=None si el MCP no responde."""
    t = ticker.upper().strip()
    try:
        f = ficha(t)
    except MyInvestorError as exc:
        return {"ok": None, "mercados": [], "monedas": [],
                "nota": "MCP MyInvestor no disponible (%s); sin verificar" % str(exc)[:80],
                "fuente": URL}
    texto = f.get("texto") or ""
    if not f.get("encontrado") or f.get("is_error"):
        return {"ok": False, "mercados": [], "monedas": [],
                "nota": "%s no aparece en el catalogo de MyInvestor" % t, "fuente": URL}
    mercado_principal = "USA" if " USA" in texto else ""
    moneda = "USD" if "USD" in texto else ("EUR" if "EUR" in texto else "")
    mercados = [m for m in ("USA", "NVD.DE") if m in texto]
    monedas = [c for c in ("USD", "EUR") if c in texto]
    nota = "catalogo MyInvestor: %s" % texto.split("\n")[1].strip()[:160] if "\n" in texto else "catalogo MyInvestor"
    return {"ok": True, "mercados": mercados or ([mercado_principal] if mercado_principal else []),
            "monedas": monedas or ([moneda] if moneda else []), "nota": nota,
            "fuente": URL, "texto": texto[:400]}


def buscar(query, limite=3):
    res = _rpc("tools/call", {"name": "search_stocks",
                              "arguments": {"query": query, "limit": int(limite)}})
    return _texto(res)
