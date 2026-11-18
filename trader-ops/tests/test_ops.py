"""Tests del codigo propio (trader-ops), con Telegram y Yahoo simulados.

    python -m unittest discover -s trader-ops/tests -v
"""
import datetime as dt
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "trader-ops"))

from lib import avisos, calendario, cfg, criterios, datos, diario, posiciones  # noqa: E402
from lib import registro, telegram as tg, texto, zonatiempo as zt  # noqa: E402


def ctx_base(**over):
    plan = {"entry": 100.0, "stop": 98.0, "target": 104.0, "risk_per_share": 2.0,
            "reward_risk": 2.0, "target_r": 2.0, "flat_by": "15:55", "date": "2026-11-18",
            "setup": "orb"}
    ctx = {
        "symbol": "TEST", "plan": plan,
        "quote": {"price": 100.5, "age_seconds": 30, "data_time": "2026-11-18T15:31:00Z"},
        "quality": {"price": 100.0, "dollar_volume_20d": 50_000_000, "spread_pct_proxy": 0.4},
        "tm": {"mc": {"p_target": 0.40, "p_stop": 0.30, "p_neither": 0.30, "avg_R": 0.30,
                      "replays": 10000, "seed": 19},
               "history": {"triggered": 40, "target": 20, "stop": 15, "avg_R": 0.25}},
        "news": {"adverse": [], "earnings": []},
        "risk": {"passed": True, "reasons": []},
        "contracting": {"ok": True, "note": "US"},
        "costs": {"total_usd": 4.0},
        "budget": {"shares": 10, "max_loss": 20.0},
        "ventana": {"ok": True, "detail": "ok"},
        "setup_ok": True, "setup_detail": "triggered",
        "min_reward_risk": 1.0,
        "ruido": {"ok": True, "reasons": []},
        "presupuesto": {"ok": True, "detail": "ok"},
        "entry_time_et": "10:15 AM",
        "src": {},
        "now": zt.now_utc(),
    }
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(ctx.get(k), dict):
            ctx[k] = dict(ctx[k], **v)
        else:
            ctx[k] = v
    return ctx


class Wilson(unittest.TestCase):
    def test_known_interval(self):
        lo, hi = criterios.wilson(20, 40)
        self.assertAlmostEqual(lo, 0.352, places=3)
        self.assertAlmostEqual(hi, 0.648, places=3)

    def test_extremes(self):
        lo, hi = criterios.wilson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertLess(hi, 0.35)
        lo, hi = criterios.wilson(10, 10)
        self.assertGreater(lo, 0.65)
        self.assertEqual(hi, 1.0)

    def test_zero_sample(self):
        self.assertEqual(criterios.wilson(0, 0), (0.0, 1.0))

    def test_break_even(self):
        self.assertAlmostEqual(criterios.break_even(1), 0.5)
        self.assertAlmostEqual(criterios.break_even(2), 1 / 3)

    def test_cost_in_r(self):
        self.assertAlmostEqual(criterios.coste_en_r(10, 10, 2.0), 0.5)
        self.assertIsNone(criterios.coste_en_r(10, 0, 2.0))


class Veredictos(unittest.TestCase):
    def test_senal_a_con_todo_en_verde(self):
        ev = criterios.evaluar(ctx_base())
        self.assertEqual(ev["verdict"], "SEÑAL A", ev["reasons"])

    def test_descartada_por_ev_negativo(self):
        ev = criterios.evaluar(ctx_base(costs={"total_usd": 60.0}))
        self.assertEqual(ev["verdict"], "DESCARTADA")
        self.assertIn("ev", ev["critical_failed"])

    def test_descartada_por_dato_viejo(self):
        ev = criterios.evaluar(ctx_base(quote={"price": 100.5, "age_seconds": 999,
                                               "data_time": "x"}))
        self.assertEqual(ev["verdict"], "DESCARTADA")

    def test_descartada_por_calidad(self):
        ev = criterios.evaluar(ctx_base(quality={"price": 2.0, "dollar_volume_20d": 1000,
                                                 "spread_pct_proxy": 5.0}))
        self.assertEqual(ev["verdict"], "DESCARTADA")

    def test_vigilar_sin_muestra(self):
        ev = criterios.evaluar(ctx_base(tm={"mc": {"p_target": 0.40, "p_stop": 0.30,
                                                   "p_neither": 0.30, "avg_R": 0.3,
                                                   "replays": 10000, "seed": 19},
                                          "history": {"triggered": 4, "target": 3, "stop": 1,
                                                      "avg_R": 0.4}}))
        self.assertEqual(ev["verdict"], "VIGILAR")

    def test_caducada_por_deriva(self):
        ev = criterios.evaluar(ctx_base(quote={"price": 102.0, "age_seconds": 10,
                                               "data_time": "x"}))
        self.assertEqual(ev["verdict"], "DESCARTADA")
        self.assertIn("deriva", ev["critical_failed"])

    def test_resultados_bloquean(self):
        ev = criterios.evaluar(ctx_base(news={"adverse": [], "earnings": ["resultados hoy"]}))
        self.assertEqual(ev["verdict"], "VIGILAR")


class Mensajes(unittest.TestCase):
    def test_builder_registra_cifras(self):
        b = texto.Builder()
        b.line("Entrada %s" % b.num(364.18, 2, "entrada", src="e1"))
        payload = b.payload()
        evs = {"e1": {"id": "e1", "name": "exit", "output": '{"entry": 364.18}'}}
        ok, problems = texto.validar(payload, evs)
        self.assertTrue(ok, problems)

    def test_validador_detecta_cifra_inventada(self):
        b = texto.Builder()
        b.line("Entrada 364.18")
        b.line("Objetivo 999.99")   # no registrada
        ok, problems = texto.validar(b.payload(), {})
        self.assertFalse(ok)
        self.assertTrue(any("999" in p for p in problems))

    def test_validador_detecta_origen_que_no_coincide(self):
        b = texto.Builder()
        b.line("Entrada %s" % b.num(364.18, 2, "entrada", src="e1"))
        evs = {"e1": {"id": "e1", "output": '{"entry": 300.00}'}}
        ok, problems = texto.validar(b.payload(), evs)
        self.assertFalse(ok)

    def test_recorte(self):
        self.assertLessEqual(len(texto.recortar("x" * 9000)), 4096)


class Reloj(unittest.TestCase):
    def test_desfase_cambia_con_el_cambio_de_hora(self):
        # Europa cambia el 25-oct-2026; EE. UU. el 1-nov-2026: esa semana son 5 h
        a = dt.datetime(2026, 10, 28, 12, tzinfo=zt.UTC)
        self.assertEqual(zt.offset_hours(a), 5)
        b = dt.datetime(2026, 11, 10, 12, tzinfo=zt.UTC)
        self.assertEqual(zt.offset_hours(b), 6)

    def test_calendario_nyse(self):
        self.assertIsNone(calendario.nyse_session("2026-11-26")[0])       # Accion de Gracias
        o, c, why = calendario.nyse_session("2026-11-27")                  # cierre anticipado
        self.assertEqual(c, dt.time(13, 0))
        self.assertIn("anticipado", why)
        self.assertEqual(calendario.nyse_session("2026-11-28")[0], None)  # sabado

    def test_flat_by_en_cierre_anticipado(self):
        normal = calendario.flat_by_madrid("2026-11-25", "15:55")
        early = calendario.flat_by_madrid("2026-11-27", "15:55")
        self.assertEqual(normal.strftime("%H:%M"), "21:55")
        self.assertEqual(early.strftime("%H:%M"), "18:55")

    def test_sesion_madrid(self):
        start, end, why = calendario.session_madrid("2026-11-18")
        self.assertEqual(start.strftime("%H:%M"), "15:30")
        self.assertEqual(end.strftime("%H:%M"), "22:00")


class TelegramDry(unittest.TestCase):
    def test_send_dry_no_falla(self):
        bot = tg.Telegram(token=None, chat_id=None, dry=True)
        self.assertIsNone(bot.send("hola", buttons=[[("x", "y")]]))

    def test_dedupe(self):
        bot = tg.Telegram(token=None, chat_id=None, dry=True)
        key = "test:%s" % dt.datetime.now().isoformat()
        avisos.send_once(bot, key, "uno")
        self.assertTrue(avisos.ya_enviado(key))
        self.assertIsNone(avisos.send_once(bot, key, "dos"))


class RegistroYPosiciones(unittest.TestCase):
    def setUp(self):
        self._reg = cfg.read_json(registro.PATH, None)
        self._pos = cfg.read_json(posiciones.PATH, None)
        cfg.write_json(registro.PATH, {"senales": []})
        cfg.write_json(posiciones.PATH, {"posiciones": []})

    def tearDown(self):
        cfg.write_json(registro.PATH, self._reg or {"senales": []})
        cfg.write_json(posiciones.PATH, self._pos or {"posiciones": []})

    def test_ciclo_de_senal(self):
        s = registro.add("TEST", {"entry": 100, "stop": 98, "target": 104,
                                  "risk_per_share": 2, "target_r": 2, "flat_by": "15:55"},
                         {"verdict": "SEÑAL A"})
        self.assertEqual(registro.stats()["abiertas"], 1)
        registro.close(s["id"], "objetivo", 104)
        st = registro.stats()
        self.assertEqual(st["objetivos"], 1)
        self.assertAlmostEqual(st["r_medio"], 2.0)

    def test_ciclo_de_posicion(self):
        p = posiciones.abrir("TEST", 101.0, 5, stop=98, target=107,
                             plan={"entry": 100, "risk_per_share": 2})
        self.assertAlmostEqual(p["deslizamiento_entrada"], 1.0)
        c = posiciones.cerrar("TEST", 107.0, motivo="objetivo")
        self.assertAlmostEqual(c["pnl_usd"], 30.0)
        self.assertAlmostEqual(c["R"], 2.0)

    def test_freno_con_muestra(self):
        cfg.write_json(registro.PATH, {"senales": [
            {"id": "a", "symbol": "X", "estado": "stop", "R": -1.0, "plan": {}, "ts_madrid": "2026-11-01T10:00"},
            {"id": "b", "symbol": "X", "estado": "stop", "R": -1.0, "plan": {}, "ts_madrid": "2026-11-02T10:00"},
        ]})
        freno, _ = registro.freno_activo()
        self.assertFalse(freno)  # muestra insuficiente


class Robustez(unittest.TestCase):
    def test_json_corrupto_no_rompe(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write("{esto no es json")
            name = fh.name
        try:
            self.assertIsNone(cfg.read_json(name, None))
            self.assertEqual(cfg.read_json(name, {"a": 1}), {"a": 1})
        finally:
            os.unlink(name)

    def test_ticker_regex(self):
        for good in ("NVDA", "BRK.B", "NVD.DE", "TSLA"):
            self.assertTrue(texto.is_ticker(good), good)
        for bad in ("../../etc", "NVDA;rm", "A" * 9, "NV DA", "$(x)", "NVDA|ls"):
            self.assertFalse(texto.is_ticker(bad), bad)

    def test_safe_float(self):
        self.assertEqual(texto.safe_float("155.20"), 155.2)
        self.assertEqual(texto.safe_float("155,20"), 155.2)
        self.assertIsNone(texto.safe_float("-5", 0.0001))
        self.assertIsNone(texto.safe_float("abc"))


class BotComandos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "trader-ops" / "run" / "telegram_bot.py"
        spec = importlib.util.spec_from_file_location("tgbot", path)
        cls.bot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bot)
        cls.dry = tg.Telegram(token=None, chat_id=None, dry=True)

    def test_texto_libre_rechazado(self):
        out = self.bot.dispatch(self.dry, "hazme un cafe")
        self.assertIn("No te he entendido", out)

    def test_comando_desconocido(self):
        out = self.bot.dispatch(self.dry, "/rm -rf /")
        self.assertIn("desconocido", out)

    def test_inyeccion_en_ticker(self):
        out = self.bot.dispatch(self.dry, "/ticker ../../etc/passwd")
        self.assertIn("Uso:", out)

    def test_inyeccion_en_entre(self):
        out = self.bot.dispatch(self.dry, "/entre NVDA;ls 1 1")
        self.assertIn("Uso:", out)

    def test_ayuda_lista_comandos(self):
        out = self.bot.dispatch(self.dry, "/ayuda")
        for c in ("/estado", "/ticker", "/entre", "/registro"):
            self.assertIn(c, out)


if __name__ == "__main__":
    unittest.main()
