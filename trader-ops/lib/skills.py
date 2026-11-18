"""Ejecutor de los scripts del skill. Determinista, sin shell, con diario.

Nunca se pasa texto libre a un shell: argv es una lista, cwd es la raiz del
proyecto y cada ejecucion queda en logs/diario.jsonl con su hash de salida.
"""
import json
import subprocess
import time
from dataclasses import dataclass, field

from . import cfg
from . import diario
from . import zonatiempo as zt


class SkillError(Exception):
    pass


@dataclass
class Result:
    name: str
    argv: list
    code: int
    seconds: float
    stdout: str
    stderr: str
    data: object = None
    started: object = None
    event: dict = field(default_factory=dict)

    @property
    def ok(self):
        return self.code == 0

    @property
    def text(self):
        return (self.stdout or "") + (("\n" + self.stderr) if self.stderr.strip() else "")

    def first_json(self):
        """Primer objeto/array JSON del stdout (los scripts a veces imprimen avisos)."""
        if self.data is not None:
            return self.data
        return parse_json(self.stdout)


def parse_json(text):
    if not text:
        return None
    t = text.strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    if start < 0:
        return None
    for end in range(len(t), start, -1):
        chunk = t[start:end]
        try:
            return json.loads(chunk)
        except ValueError:
            continue
    return None


def run(name, args, timeout=180, json_out=None, label=None, retries=0, retry_wait=20):
    """Ejecuta un script del skill. `json_out` fuerza el parseo del stdout.

    Devuelve Result. No lanza por codigo != 0: el pipeline decide.
    """
    script = cfg.SKILL_SCRIPTS.get(name)
    if not script or not script.exists():
        raise SkillError("script desconocido o ausente: %s" % name)
    argv = [cfg.python_exe(), str(script)] + [str(a) for a in args]
    attempt, last = 0, None
    while True:
        started = zt.now_utc()
        t0 = time.time()
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cfg.ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=cfg.env_with_sec(),
            )
            out, err, code = proc.stdout or "", proc.stderr or "", proc.returncode
        except subprocess.TimeoutExpired:
            out, err, code = "", "timeout tras %ss" % timeout, 124
        except OSError as exc:
            out, err, code = "", "no se pudo ejecutar: %s" % exc, 127
        seconds = round(time.time() - t0, 2)
        data = parse_json(out) if json_out else None
        res = Result(name=name, argv=argv, code=code, seconds=seconds,
                     stdout=out, stderr=err, data=data, started=started)
        last = res
        if code == 0 or attempt >= retries:
            break
        attempt += 1
        time.sleep(retry_wait)
    ev = diario.append(
        "cmd",
        name=name,
        label=label or "",
        argv=last.argv[2:],
        code=last.code,
        seconds=last.seconds,
        output=last.stdout if not last.stdout else last.stdout,
        stderr=(last.stderr or "")[:4000],
        cwd=str(cfg.ROOT),
        moment=last.started,
    )
    last.event = ev
    return last


# ---------------------------------------------------------------- atajos con contrato
# Cada uno devuelve Result. Los argumentos son los del SKILL.md; no inventamos flags.

def scanner_daily(symbols=None, watchlist=None, limit=None, min_volume=None, offline=None,
                  no_write=False, extra=None):
    """scan.py daily. Escribe trader/watchlist.json salvo no_write."""
    args = ["daily", "--json"]
    if symbols:
        args += ["--symbols", ",".join(symbols)]
    if watchlist:
        args += ["--watchlist", watchlist]
    if limit:
        args += ["--limit", str(limit)]
    if min_volume is not None:
        args += ["--min-volume", str(min_volume)]
    if offline:
        args += ["--offline", offline]
    if no_write:
        args += ["--no-write"]
    args += list(extra or [])
    return run("scanner", args, timeout=600, json_out=True, label="scan daily")


def scanner_orb(watchlist="trader/watchlist.json", at=None, or_minutes=15, out=None, extra=None):
    args = ["orb", "--json", "--watchlist", watchlist, "--or-minutes", str(or_minutes)]
    if out:
        args += ["--out", out]
    if at:
        args += ["--at", at]
    args += list(extra or [])
    return run("scanner", args, timeout=600, json_out=True, label="scan orb")


def entry_check(symbol, setup="orb", write=True, extra=None):
    args = ["check", symbol, "--setup", setup, "--json"]
    if write:
        args += ["--write"]
    args += list(extra or [])
    return run("entry", args, timeout=120, json_out=True, label="entry check %s" % symbol)


def exit_plan_from_entry(stop="or-mid", target="1R", write=True, extra=None):
    args = ["plan", "--stop", stop, "--target", target, "--json"]
    if write:
        args += ["--write"]
    args += list(extra or [])
    return run("exit", args, timeout=120, json_out=True, label="exit plan")


def timemachine(until=None, write=True, replays=10000, seed=19, extra=None):
    args = ["run", "--replays", str(replays), "--seed", str(seed), "--json"]
    if until:
        args += ["--until", until]
    if write:
        args += ["--write"]
    args += list(extra or [])
    return run("timemachine", args, timeout=600, json_out=True, label="timemachine")


def budget(limit=None, write=True, budget_usd=None, extra=None):
    args = ["--json"]
    if limit:
        args += ["--limit", str(limit)] if limit != "plan" else ["--limit"]
    if budget_usd:
        args += ["--budget", str(budget_usd)]
    if write:
        args += ["--write"]
    args += list(extra or [])
    return run("budget", args, timeout=120, json_out=True, label="budget size")


def risk_check(no_write=False, extra=None):
    args = ["--json"]
    if no_write:
        args += ["--no-write"]
    args += list(extra or [])
    return run("risk", args, timeout=120, json_out=True, label="risk check")


def ticket_show(json_out=True):
    args = ["show"] + (["--json"] if json_out else [])
    return run("broker", args, timeout=60, json_out=json_out, label="ticket show")


def alerts_quote(symbols, write=True):
    args = ["quote"] + list(symbols) + ["--json"]
    if write:
        args += ["--write"]
    return run("alerts", args, timeout=120, json_out=True, label="alerts quote")


def alerts_clock():
    return run("alerts", ["clock", "--json"], timeout=30, json_out=True, label="alerts clock")


def alerts_add_from_plan():
    # `alerts.py add` no acepta --json: devuelve texto
    return run("alerts", ["add", "--from-plan"], timeout=60, json_out=False, label="alerts add")


def alerts_check():
    return run("alerts", ["check", "--json"], timeout=120, json_out=True, label="alerts check")


def news(tickers=None, hours=24, no_sec=False, extra=None):
    args = ["--hours", str(hours), "--json"]
    if tickers:
        args += ["--tickers"] + list(tickers)
    if no_sec:
        args += ["--no-sec"]
    args += list(extra or [])
    return run("news", args, timeout=180, json_out=True, label="news")


def analyst(tickers, extra=None):
    args = list(tickers) + ["--json"]
    args += list(extra or [])
    return run("analyst", args, timeout=240, json_out=True, label="analyst")


def pelosi_new(read=True):
    args = ["new", "--json"] + (["--read"] if read else [])
    return run("pelosi", args, timeout=240, json_out=True, label="pelosi new")
