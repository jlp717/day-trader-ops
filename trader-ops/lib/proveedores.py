"""Interfaz de datos de nivel 2. Sin proveedor configurado no se inventa nada.

El nivel 2 (libro de ordenes) no esta en Yahoo/CNBC/Finnhub free. Para usarlo
hace falta un proveedor de pago y una clave; hasta entonces, cualquier llamada
falla de forma explicita.
"""


class ProveedorError(Exception):
    pass


class Nivel2:
    nombre = "ninguno"

    def libro(self, symbol):
        raise ProveedorError(
            "nivel 2 no configurado: requiere proveedor de pago (Polygon, Databento, etc.)")

    def profundidad(self, symbol):
        raise ProveedorError("profundidad no disponible: nivel 2 de pago")


class AlpacaIEX(Nivel2):
    """Top-of-book IEX gratis. No es libro completo: solo bid/ask y tamanos."""

    nombre = "alpaca_iex"

    def libro(self, symbol):
        from . import alpaca
        sym = str(symbol).upper()
        try:
            doc = alpaca.data_request(
                "/v2/stocks/%s/quotes/latest" % sym, params={"feed": "iex"})
        except alpaca.AlpacaError as exc:
            raise ProveedorError(str(exc))
        q = (doc or {}).get("quote") or {}
        if not q:
            raise ProveedorError("Alpaca IEX sin quote para %s" % sym)
        return {
            "symbol": sym,
            "bid": q.get("bp"),
            "ask": q.get("ap"),
            "bid_size": q.get("bs"),
            "ask_size": q.get("as"),
            "time": q.get("t"),
            "depth": 1,
            "source": "alpaca_iex",
            "completo": False,
            "spread_pct": (
                (float(q["ap"]) - float(q["bp"])) / float(q["bp"]) * 100.0
                if q.get("ap") and q.get("bp") else None),
        }

    def profundidad(self, symbol):
        raise ProveedorError(
            "Alpaca free/IEX solo da top-of-book; la profundidad completa es de pago")


class PolygonL2(Nivel2):
    nombre = "polygon"

    def __init__(self, key=None):
        self.key = key

    def libro(self, symbol):
        if not self.key:
            raise ProveedorError("Polygon L2 sin clave: secrets/polygon.json")
        raise ProveedorError("Polygon L2 no implementado: falta plan/contrato")


PROVEEDORES = {"ninguno": Nivel2(), "alpaca_iex": AlpacaIEX(), "polygon": PolygonL2()}


def get(nombre="ninguno", **kwargs):
    if nombre == "polygon":
        return PolygonL2(**kwargs)
    return PROVEEDORES.get(str(nombre).lower()) or Nivel2()
