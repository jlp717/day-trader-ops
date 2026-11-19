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


class PolygonL2(Nivel2):
    nombre = "polygon"

    def __init__(self, key=None):
        self.key = key

    def libro(self, symbol):
        if not self.key:
            raise ProveedorError("Polygon L2 sin clave: secrets/polygon.json")
        raise ProveedorError("Polygon L2 no implementado: falta plan/contrato")


PROVEEDORES = {"ninguno": Nivel2(), "polygon": PolygonL2()}


def get(nombre="ninguno", **kwargs):
    if nombre == "polygon":
        return PolygonL2(**kwargs)
    return PROVEEDORES.get(str(nombre).lower()) or Nivel2()
