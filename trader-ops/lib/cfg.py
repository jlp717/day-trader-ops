"""Configuracion, rutas y secretos de trader-ops. Solo libreria estandar.

Regla: los secretos NUNCA viven en el repo. Viven en <ROOT>/secrets/*.json,
que esta en .gitignore, con permisos restringidos al usuario actual.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "vendor" / "day-trader-skill"
TRADER = ROOT / "trader"
OPS = ROOT / "trader-ops"
STATE = OPS / "state"
CACHE = OPS / "cache"
LOGS = ROOT / "logs"
SECRETS = ROOT / "secrets"
DIARIO = LOGS / "diario.jsonl"

SKILL_SCRIPTS = {
    "scanner": SKILL / "trader-scanner" / "scan.py",
    "news": SKILL / "trader-news" / "news.py",
    "entry": SKILL / "trader-entry" / "entry.py",
    "exit": SKILL / "trader-exit" / "exit.py",
    "timemachine": SKILL / "trader-timemachine" / "timemachine.py",
    "risk": SKILL / "trader-risk" / "check.py",
    "budget": SKILL / "trader-budget" / "size.py",
    "broker": SKILL / "trader-broker" / "ticket.py",
    "alerts": SKILL / "trader-alerts" / "alerts.py",
    "analyst": SKILL / "trader-analyst" / "facts.py",
    "pelosi": SKILL / "trader-pelosi" / "ptr.py",
}

for _d in (TRADER, OPS, STATE, CACHE, LOGS, SECRETS, TRADER / "state"):
    _d.mkdir(parents=True, exist_ok=True)


def python_exe():
    """El interprete en uso. En Windows es `python`; nunca asumimos `python3`."""
    return sys.executable or "python"


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def config():
    """trader/config.json + defaults de seguridad. Solo lectura."""
    cfg = read_json(TRADER / "config.json", {}) or {}
    cfg.setdefault("paper", True)
    cfg.setdefault("budget", 5000)
    cfg.setdefault("max_loss_per_trade_usd", 50)
    cfg.setdefault("max_daily_loss_usd", 100)
    cfg.setdefault("max_trades_per_day", 3)
    cfg.setdefault("min_reward_risk", 1.0)
    cfg.setdefault("flat_by", "15:55")
    cfg.setdefault("no_entries_after", "15:30")
    cfg.setdefault("watch", ["NVDA"])
    cfg.setdefault("execution_market", "US")
    return cfg


def _load_secret(name):
    return read_json(SECRETS / name, {}) or {}


def telegram_secret():
    return _load_secret("telegram.json")


def sec_user_agent():
    """Nombre y email para la SEC: env > secrets > config. Vacio = no disponible."""
    ua = (os.environ.get("SEC_USER_AGENT") or "").strip()
    if ua:
        return ua
    ua = (_load_secret("sec.json").get("user_agent") or "").strip()
    if ua:
        return ua
    cfg_ua = (config().get("sec_user_agent") or "").strip()
    if "pendiente" in cfg_ua.lower() or "email@" in cfg_ua.lower():
        return ""
    return cfg_ua


def env_with_sec():
    """Entorno para los scripts del skill: inyecta SEC_USER_AGENT si lo tenemos."""
    env = dict(os.environ)
    ua = sec_user_agent()
    if ua:
        env["SEC_USER_AGENT"] = ua
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env
