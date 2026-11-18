"""Mensajes construidos con trazabilidad: cada cifra queda registrada al formatearla.

Un Builder acumula texto y, a la vez, la lista de cifras con su origen (el id del
evento del diario que las produjo). `validar` comprueba despues dos cosas:
  1. Todo token numerico del texto esta registrado (no hay cifras inventadas).
  2. Toda cifra con origen aparece de verdad en la salida de ese comando.
Si algo falla, el mensaje NO se envia y el fallo queda en el diario.
"""
import re

TOKEN = re.compile(r"(?<![\w:/.-])([+-]?\d+(?:[.,]\d+)?)(?![\w:])")
TICKER = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$")
SAFE_ARG = re.compile(r"^[A-Za-z0-9._:+-]{1,32}$")


class TraceError(Exception):
    pass


def is_ticker(text):
    return bool(TICKER.match((text or "").strip().upper()))


def safe_float(text, lo=None, hi=None):
    try:
        v = float(str(text).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if lo is not None and v < lo:
        return None
    if hi is not None and v > hi:
        return None
    return v


def tokens(text):
    return [m.group(1) for m in TOKEN.finditer(text or "")]


class Builder:
    def __init__(self):
        self.parts = []
        self.cifras = []          # [{label, value, fmt, src}]
        self.allowed = set()      # tokens permitidos tal cual

    # ---------------------------------------------------------------- texto
    def raw(self, text):
        """Bloque ya calculado (p.ej. un informe): sus cifras se aceptan tal cual."""
        self.parts.append(text)
        for t in tokens(text):
            self.allowed.add(t.replace(",", "."))
            self.allowed.add(t)
        return self

    def line(self, text=""):
        """Linea normal: las cifras deben venir de num() o ser estructurales."""
        self.parts.append(text + "\n")
        return self

    def blank(self):
        return self.line("")

    # ---------------------------------------------------------------- cifras
    def num(self, value, dec=2, label="", src=None, signed=False, money=False, pct=False):
        if value is None:
            return "n/d"
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "n/d"
        if pct:
            fmt = ("%+.*f%%" if signed else "%.*f%%") % (dec, v)
        elif money:
            fmt = ("%+.*f" if signed else "%.*f") % (dec, v)
        else:
            fmt = ("%+.*f" if signed else "%.*f") % (dec, v)
        self.cifras.append({"label": label, "value": v, "fmt": fmt, "src": src})
        variants = {fmt, fmt.lstrip("+"), fmt.replace(".", ","), fmt.lstrip("+").replace(".", ",")}
        variants |= {x.rstrip("%") for x in list(variants)}
        variants |= {x.lstrip("-") for x in list(variants)}
        variants |= {"%.*f" % (dec, abs(v)), "%.*f" % (dec, v), "%g" % v, "%g" % abs(v)}
        for variant in variants:
            self.allowed.add(variant)
        return fmt

    def add_allowed(self, *texts):
        for t in texts:
            self.allowed.add(str(t))
            for tok in tokens(str(t)):
                self.allowed.add(tok.replace(",", "."))
        return self

    def text(self):
        return "".join(self.parts)

    def payload(self):
        return {"texto": self.text(), "cifras": self.cifras, "allowed": sorted(self.allowed)}


def _numbers_in(text):
    out = set()
    for m in re.finditer(r"-?\d+(?:[.,]\d+)?", text or ""):
        out.add(m.group(0).replace(",", "."))
        try:
            out.add("%g" % float(m.group(0).replace(",", ".")))
        except ValueError:
            continue
    return out


def _structural(tok):
    """Tokens que no son cifras de mercado: horas, fechas, multiplos de R, conteos."""
    t = tok.replace(",", ".")
    if re.match(r"^\d{1,2}:\d{2}$", tok):
        return True
    if re.match(r"^\d{4}-\d{2}-\d{2}$", tok):
        return True
    if re.match(r"^\d+(?:\.\d+)?R$", tok, re.I):
        return True
    if re.match(r"^(19|20|21)\d{2}$", tok):
        return True          # ano dentro de una fecha ISO
    try:
        v = float(t)
    except ValueError:
        return False
    if v.is_integer() and abs(v) <= 12:
        return True          # conteos pequenos, minutos, dias, "2R", "8 acciones"
    return False


def validar(payload, eventos=None):
    """Devuelve (ok, problemas). `eventos` = {id: doc} con la salida de cada comando.

    Una cifra con `src` debe aparecer en la salida de ese evento, con el mismo valor
    (tolerancia 1e-6 relativa). Sin `src` se acepta como calculada, pero se registra.
    """
    eventos = eventos or {}
    problems = []
    texto_ = payload.get("texto") or ""
    allowed = {a.replace(",", ".") for a in payload.get("allowed") or []}

    for tok in tokens(texto_):
        norm = tok.replace(",", ".")
        if norm in allowed or tok in allowed:
            continue
        if _structural(tok):
            continue
        try:
            fv = float(norm)
        except ValueError:
            problems.append("token no trazable: %r" % tok)
            continue
        if ("%g" % fv) in allowed or ("%g" % abs(fv)) in allowed or norm.lstrip("-") in allowed:
            continue
        problems.append("token no trazable: %r" % tok)

    for c in payload.get("cifras") or []:
        src = c.get("src")
        if not src:
            continue
        ev = eventos.get(src)
        if not ev:
            problems.append("cifra %s: falta el evento %s" % (c.get("label"), src))
            continue
        nums = _numbers_in(ev.get("output") or "")
        target = "%g" % float(c["value"])
        if target not in nums:
            problems.append("cifra %s=%s no aparece en la salida de %s" % (
                c.get("label"), c.get("fmt"), ev.get("name") or src))
    return (not problems), problems


def recortar(texto, limite=4000):
    """Telegram corta a 4096: recortamos con aviso, nunca a mitad de una cifra."""
    texto = texto or ""
    if len(texto) <= limite:
        return texto
    cut = texto[:limite - 40]
    if "\n" in cut:
        cut = cut[:cut.rfind("\n")]
    return cut + "\n...[recortado, ver diario.jsonl]"


def esc(texto):
    """Escapa para parse_mode HTML de Telegram (usamos <b> y nada mas)."""
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
