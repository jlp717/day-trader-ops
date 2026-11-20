"""Interfaz de ejecucion. NullBroker no envia nada; PaperBroker simula y audita.

La ejecucion real NO esta implementada: exige un broker con API, claves y una
aprobacion explicita. Este modulo deja el contrato y el modo papel listos para
que el dia que se abra esa puerta no haya que reescribir el resto.
"""
import hashlib
import time

from . import cfg
from . import alpaca


class BrokerError(Exception):
    pass


class Broker:
    nombre = "null"
    real = False

    def comprar(self, symbol, qty, limit=None, key=None):
        raise BrokerError("ejecucion real no configurada: broker=%s" % self.nombre)

    def vender(self, symbol, qty, limit=None, key=None):
        raise BrokerError("ejecucion real no configurada: broker=%s" % self.nombre)


class PaperBroker(Broker):
    """Rellena al precio actual y guarda la orden. Nunca envia nada al mercado."""

    nombre = "paper"
    real = False

    def __init__(self, quote_fn=None, path=None):
        self.quote_fn = quote_fn
        self.path = path or (cfg.STATE / "paper_orders.json")

    def _quote(self, symbol):
        if self.quote_fn:
            return float(self.quote_fn(symbol))
        from . import datos
        return float(datos.quote(symbol)["price"])

    def _load(self):
        return cfg.read_json(self.path, {"ordenes": []}) or {"ordenes": []}

    def _save(self, doc):
        cfg.write_json(self.path, doc)

    def _orden(self, lado, symbol, qty, limit=None, key=None):
        qty = float(qty)
        if qty <= 0:
            raise BrokerError("cantidad invalida")
        doc = self._load()
        if key:
            for o in doc.get("ordenes") or []:
                if o.get("key") == key:
                    return o
        px = self._quote(symbol)
        lim = None if limit is None else float(limit)
        if lim is not None:
            if lado == "compra" and lim < px:
                raise BrokerError("limite de compra por debajo del precio actual")
            if lado == "venta" and lim > px:
                raise BrokerError("limite de venta por encima del precio actual")
        fill = px if lim is None else (min(px, lim) if lado == "compra" else max(px, lim))
        o = {
            "id": hashlib.sha1((key or "%s-%s-%s" % (symbol, lado, time.time()))
                               .encode("utf-8")).hexdigest()[:12],
            "key": key,
            "symbol": str(symbol).upper(),
            "side": lado,
            "qty": qty,
            "limit": lim,
            "fill": round(float(fill), 4),
            "ts": round(time.time(), 3),
            "broker": "paper",
            "real": False,
        }
        doc.setdefault("ordenes", []).append(o)
        self._save(doc)
        return o

    def comprar(self, symbol, qty, limit=None, key=None):
        return self._orden("compra", symbol, qty, limit=limit, key=key)

    def vender(self, symbol, qty, limit=None, key=None):
        return self._orden("venta", symbol, qty, limit=limit, key=key)


REGISTRO = {"null": Broker(), "paper": PaperBroker()}


class AlpacaPaperBroker(Broker):
    """Ordenes en la cuenta PAPEL de Alpaca. Nunca usa el endpoint real."""

    nombre = "alpaca_paper"
    real = False

    def _orden(self, side, symbol, qty, limit=None, key=None):
        qty = float(qty)
        if qty <= 0:
            raise BrokerError("cantidad invalida")
        body = {
            "symbol": str(symbol).upper(),
            "qty": ("%g" % qty),
            "side": side,
            "time_in_force": "day",
            "type": "limit" if limit is not None else "market",
        }
        if limit is not None:
            body["limit_price"] = "%.2f" % float(limit)
        if key:
            body["client_order_id"] = str(key)[:48]
        try:
            return alpaca.paper_request("POST", "/v2/orders", body=body)
        except alpaca.AlpacaError as exc:
            raise BrokerError(str(exc))

    def comprar(self, symbol, qty, limit=None, key=None):
        return self._orden("buy", symbol, qty, limit=limit, key=key)

    def vender(self, symbol, qty, limit=None, key=None):
        return self._orden("sell", symbol, qty, limit=limit, key=key)

    def bracket(self, symbol, qty, limit, stop, target, key=None):
        """Orden bracket PAPEL: entrada limitada + stop + objetivo."""
        qty = float(qty)
        if qty <= 0:
            raise BrokerError("cantidad invalida")
        if not (float(stop) < float(limit) < float(target)):
            raise BrokerError("el bracket exige stop < entrada < objetivo")
        body = {
            "symbol": str(symbol).upper(),
            "qty": ("%g" % qty),
            "side": "buy",
            "type": "limit",
            "limit_price": "%.2f" % float(limit),
            "time_in_force": "day",
            "order_class": "bracket",
            "take_profit": {"limit_price": "%.2f" % float(target)},
            "stop_loss": {"stop_price": "%.2f" % float(stop)},
        }
        if key:
            body["client_order_id"] = str(key)[:48]
        try:
            return alpaca.paper_request("POST", "/v2/orders", body=body)
        except alpaca.AlpacaError as exc:
            raise BrokerError(str(exc))

    def cuenta(self):
        try:
            return alpaca.paper_request("GET", "/v2/account")
        except alpaca.AlpacaError as exc:
            raise BrokerError(str(exc))


REGISTRO["alpaca_paper"] = AlpacaPaperBroker()


def get(nombre="null", **kwargs):
    if nombre == "paper":
        return PaperBroker(**kwargs)
    return REGISTRO.get(str(nombre).lower()) or Broker()


def nombres():
    return sorted(REGISTRO)
