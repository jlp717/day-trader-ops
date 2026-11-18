"""Briefing previo: candidatos, plan condicional y coste de esperar. Sin prosa inventada."""
from . import apertura
from . import cfg
from . import criterios
from . import datos
from . import registro
from . import skills
from . import texto
from . import zonatiempo as zt


def _linea_candidato(b, h, q=None):
    sets = ", ".join(h.get("setups") or [])
    b.line("  %s %s · %s" % (h.get("symbol"), b.num(h.get("price"), 2, "precio_cand"),
                             sets))
    if q:
        b.line("      $%.1fM/dia, rango proxy %.2f%%, precio %.2f" % (
            (q.get("dollar_volume_20d") or 0) / 1e6,
            q.get("spread_pct_proxy") or 0, q.get("price") or 0))


def construir(cfgd=None, symbols=None, scan_json=None):
    """Devuelve payload de texto para el briefing. `scan_json` = salida de scan daily."""
    cfgd = cfgd or cfg.config()
    watch = symbols or cfgd.get("watch") or ["NVDA"]
    b = texto.Builder()
    now = zt.now_utc()
    from . import calendario
    start, end, why = calendario.session_madrid(now.date())
    b.line("<b>Briefing previo</b> · %s" % zt.short_stamp(now))
    if start:
        b.line("Sesion NYSE %s a %s Madrid (%s)." % (start.strftime("%H:%M"), end.strftime("%H:%M"), why))
    else:
        b.line("Hoy no hay sesion NYSE (%s)." % why)

    hits = (scan_json or {}).get("hits") or []
    escaneados = (scan_json or {}).get("scanned")
    universo = (scan_json or {}).get("universe")
    b.line("Scanner: %s valores, %s escaneados, %d candidatos." % (universo, escaneados, len(hits)))
    if hits:
        b.line("Candidatos (los %d primeros por dolares):" % min(5, len(hits)))
        for h in hits[:5]:
            q = None
            try:
                q = datos.calidad(h["symbol"])
            except Exception:
                pass
            _linea_candidato(b, h, q)

    b.line("Vigilados fijos: %s" % ", ".join(watch))
    b.blank()
    for sym in watch[:3]:
        try:
            res = apertura.analizar(sym)
            b.raw(apertura.bloque_texto(res))
        except Exception as exc:
            b.line("Coste de esperar %s: no disponible (%s)" % (sym, exc))
        b.blank()

    b.line("Plan condicional (solo niveles calculados):")
    for sym in watch[:3]:
        b.line("  %s: si rompe el maximo del rango 9:30-9:45 y el primer cierre de 5 min queda "
               "por encima -> entrada en ese cierre, stop en el mid del rango, objetivo 2R, "
               "fuera a las %s ET. Si el precio ya esta a mas de 0,5R, no perseguir." % (
                   sym, cfgd.get("flat_by")))
    b.blank()
    st = registro.stats()
    b.line("Registro vivo: %d señales, %d cerradas, R medio %+.2f. %s" % (
        st["total"], st["cerradas"], st["r_medio"], criterios.registro_libre(st)))
    b.line("PRUEBA EN PAPEL · sin ordenes · datos Yahoo (pueden lag).")
    return b.payload()
