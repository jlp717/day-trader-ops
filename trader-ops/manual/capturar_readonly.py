import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Javier\Desktop\Repositorios\day-trader-ops")
sys.path.insert(0, str(ROOT / "trader-ops"))
sys.path.insert(0, str(ROOT / "trader-ops" / "run"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import telegram_bot as bot  # noqa: E402
from lib import telegram as tg  # noqa: E402

COMANDOS = [
    "/estado", "/ahora", "/reloj", "/hoy", "/resumen", "/registro", "/vigilar",
    "/descartadas", "/alertas", "/posiciones", "/pnl", "/ganadores 5", "/elegir NVDA",
    "/resultados NVDA", "/noticias NVDA", "/mercados NVDA", "/apertura NVDA",
    "/tm NVDA", "/plan NVDA", "/tamano NVDA", "/ticker NVDA", "/risk", "/ticket",
    "/pelosi", "/scan NVDA", "/ensenar orb", "/ensenar r", "/ensenar senal a", "/ayuda",
]

dry = tg.Telegram(dry=True)
out = {}
for c in COMANDOS:
    try:
        out[c] = bot.dispatch(dry, c)
    except Exception as exc:  # noqa: BLE001
        out[c] = "ERROR: %s" % exc
    print(c, "->", len(out[c]), "chars")

p = ROOT / "trader-ops" / "manual" / "salidas_readonly.json"
p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("guardado", p)
