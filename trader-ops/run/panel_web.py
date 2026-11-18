"""Panel web local de solo lectura. Se refresca solo, sin secretos, sin botones.

    python trader-ops/run/panel_web.py            # http://127.0.0.1:8765
    python trader-ops/run/panel_web.py --puerto 9000

Liga solo a 127.0.0.1: no se expone en la red. No ejecuta nada: solo lee archivos
de estado y pinta HTML.
"""
import argparse
import html
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "trader-ops"))

from lib import estado_vivo  # noqa: E402

CSS = """
:root{--bg:#0f1115;--fg:#e6e6e6;--dim:#8b93a1;--ok:#39d353;--bad:#f85149;--warn:#d29922;--acc:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.45 ui-monospace,Consolas,monospace}
header{padding:14px 18px;border-bottom:1px solid #22262e;display:flex;gap:18px;flex-wrap:wrap;align-items:baseline}
h1{font-size:16px;margin:0;letter-spacing:.5px}
.muted{color:var(--dim)}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}.acc{color:var(--acc)}
main{padding:14px 18px;display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}
section{background:#151920;border:1px solid #22262e;border-radius:8px;padding:12px 14px}
h2{font-size:13px;margin:0 0 8px;color:var(--acc);text-transform:uppercase;letter-spacing:.6px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:3px 6px;border-bottom:1px solid #1d222b}
th{color:var(--dim);font-weight:400}td.num{text-align:right}
.big{font-size:20px}
footer{padding:10px 18px;color:var(--dim);border-top:1px solid #22262e}
"""


def _f(x, dec=2):
    try:
        return ("%%.%df" % dec) % float(x)
    except (TypeError, ValueError):
        return "n/d"


def _pct(x):
    return "n/d" if x is None else "%+.2f%%" % x


def _sec(x):
    if x is None:
        return "n/d"
    if x < 120:
        return "%ds" % x
    if x < 7200:
        return "%dm" % (x // 60)
    return "%dh %02dm" % (x // 3600, (x % 3600) // 60)


def pagina(f):
    e = html.escape
    ses = f["session"]
    h = f["health"]
    filas_watch = "".join(
        "<tr><td>%s</td><td class=num>%s</td><td class=num>%s</td><td class=num>%s</td></tr>" % (
            e(v["symbol"]), _f(v["price"]) if v["price"] else "n/d",
            _f(v["level"]) if v["level"] else "-", _pct(v["dist_pct"]))
        for v in f["watch"]) or "<tr><td colspan=4 class=muted>nada vigilado</td></tr>"
    filas_pos = "".join(
        "<tr><td>%s</td><td class=num>%s</td><td class=num>%.2f</td><td class=num>%s</td>"
        "<td class=num>%s</td><td class=num>%s</td><td class=num>%s</td></tr>" % (
            e(p["symbol"]), p["qty"], float(p["entry"]),
            _f(p["stop"]) if p["stop"] else "-", _f(p["target"]) if p["target"] else "-",
            _f(p["price"]) if p["price"] else "n/d", _pct(p["dist_stop_pct"]))
        for p in f["positions"]) or "<tr><td colspan=7 class=muted>sin posiciones</td></tr>"
    filas_al = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td class=num>%s</td></tr>" % (
        e(str(a["id"])), e(str(a["symbol"] or "")), e(str(a["type"] or "")), e(str(a["price"] or "")))
        for a in f["alerts"][:12]) or "<tr><td colspan=4 class=muted>sin alertas armadas</td></tr>"
    desc = "".join("<li><b>%s</b> · %s</li>" % (e(str(d["symbol"])), e("; ".join(d["motivos"])))
                   for d in f["signals"]["descartadas"][:8]) or "<li class=muted>ninguna</li>"
    a_list = "".join("<li><b>%s</b> · %s</li>" % (e(str(a["symbol"])), e("; ".join(a["motivos"] or [])))
                     for a in f["signals"]["A"]) or "<li class=muted>ninguna</li>"
    return """<!doctype html><html lang=es><head><meta charset=utf-8>
<meta http-equiv=refresh content=5><title>Day Trader PAPEL</title><style>%s</style></head><body>
<header><h1>DAY TRADER · PAPEL</h1>
<span class=big>%s</span><span class=muted>Madrid · %s NY · desfase %dh</span>
<span>%s</span><span class=muted>%s</span></header>
<main>
<section><h2>Ahora</h2>
<p><b>%s</b></p>
<p class=muted>Sistema: %s</p>
<p>Tu: <b>%s</b></p>
<p class=muted>Puedes ignorar: %s</p></section>
<section><h2>Salud</h2>
<p>Orquestador: %s · latido %s (%s)</p>
<p>Errores 1h: %d · 429: %d · comandos/min: %d · datos: %s</p>
<p>%s</p></section>
<section><h2>Proximo evento</h2>
<p class=big>%s</p><p class=muted>a las %s · en %s</p></section>
<section><h2>Vigilados</h2><table><tr><th>valor</th><th>precio</th><th>nivel</th><th>dist.</th></tr>
%s</table></section>
<section><h2>Señales de hoy</h2>
<p>A: %d · vigilar: %d · descartadas: %d</p>
<p class=ok>SEÑAL A</p><ul>%s</ul>
<p class=muted>Descartadas (muestra)</p><ul>%s</ul></section>
<section><h2>Posiciones</h2>
<p class=muted>Cierre en %s min</p>
<table><tr><th>valor</th><th>acc</th><th>entrada</th><th>stop</th><th>objetivo</th><th>precio</th><th>a stop</th></tr>
%s</table></section>
<section><h2>Alertas armadas</h2><table><tr><th>id</th><th>valor</th><th>tipo</th><th>nivel</th></tr>
%s</table></section>
<section><h2>Resultado</h2>
<p>P&L a mano: <b>%+.2f USD</b> · señales cerradas: %d · R medio: %+.2f</p>
<p>Riesgo hoy: %.2f / %s USD (papel %.2f + manual %.2f) · operaciones %d / %s</p>
<p>Freno por evidencia: %s</p></section>
</main>
<footer>solo lectura · sin secretos · refresco 5 s · 127.0.0.1</footer></body></html>""" % (
        CSS, e(f["now_madrid"][11:16]), e(f["now_ny"]), f["offset_h"],
        "<span class=ok>MERCADO ABIERTO</span>" if ses["open"] else "<span class=bad>MERCADO CERRADO</span>",
        e(ses["why"]), e(f["phase"]["title"]), e(f["phase"]["system"]), e(f["phase"]["you"]),
        e(f["phase"]["ignore"]),
        "<span class=ok>VIVO</span>" if h["alive"] else "<span class=bad>PARADO</span>",
        _sec(h["heartbeat_age_s"]), e(str(h["heartbeat_phase"])), h["errors_1h"], h["http429_1h"],
        h["cmds_1m"], _sec(f["data"]["age_s"]),
        "<span class=warn>PAUSADO</span>" if f["paused"] else "<span class=muted>sin pausa</span>",
        e(str(f["next"]["title"] or "n/d")), e(str(f["next"]["at"] or "-")), e(str(f["next"]["countdown"])),
        filas_watch,
        f["signals"]["counts"].get("SEÑAL A", 0), f["signals"]["counts"].get("VIGILAR", 0),
        f["signals"]["counts"].get("DESCARTADA", 0), a_list, desc,
        f["minutes_to_close"] if f["minutes_to_close"] is not None else "n/d",
        filas_pos, filas_al,
        f["pnl"]["pnl_usd"], f["registro"]["cerradas"], f["registro"]["r_medio"],
        f["limits"]["risk_today_usd"], f["limits"]["risk_cap_usd"],
        f["limits"].get("risk_signals_usd", 0), f["limits"].get("risk_manual_usd", 0),
        f["limits"]["trades_today"], f["limits"]["trades_cap"],
        ("<span class=bad>ACTIVO</span> · " + e(f["freno"]["motivo"])) if f["freno"]["activo"] else "no")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        try:
            body = pagina(estado_vivo.foto()).encode("utf-8")
        except Exception as exc:  # noqa: BLE001
            body = ("<h1>Panel no disponible</h1><pre>%s</pre>" % html.escape(str(exc))).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


def main(argv=None):
    ap = argparse.ArgumentParser(description="Panel web local de solo lectura")
    ap.add_argument("--puerto", type=int, default=8765)
    a = ap.parse_args(argv)
    srv = ThreadingHTTPServer(("127.0.0.1", a.puerto), Handler)
    print("Panel en http://127.0.0.1:%d  (Ctrl+C para parar)" % a.puerto)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nPanel web cerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
