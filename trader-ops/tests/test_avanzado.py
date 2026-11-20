"""Tests de Alpaca papel, IEX top-of-book, ML basico y pre/post."""
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "trader-ops"))

from lib import alertas, alpaca, brokers, ml, piloto, prepost, proveedores  # noqa: E402

NY = ZoneInfo("America/New_York")


class AlpacaPaper(unittest.TestCase):
    def test_compra_limitada_papel(self):
        with mock.patch.object(alpaca, "paper_request",
                               return_value={"id": "o1", "status": "accepted"}) as m:
            b = brokers.AlpacaPaperBroker()
            r = b.comprar("NVDA", 3, limit=100, key="k1")
        self.assertEqual(r["id"], "o1")
        body = m.call_args.kwargs["body"]
        self.assertEqual(body["side"], "buy")
        self.assertEqual(body["type"], "limit")
        self.assertEqual(body["limit_price"], "100.00")
        self.assertEqual(body["client_order_id"], "k1")
        self.assertFalse(b.real)

    def test_cuenta(self):
        with mock.patch.object(alpaca, "paper_request",
                               return_value={"status": "ACTIVE", "currency": "USD"}):
            self.assertEqual(brokers.AlpacaPaperBroker().cuenta()["status"], "ACTIVE")

    def test_bracket(self):
        with mock.patch.object(alpaca, "paper_request",
                               return_value={"id": "b1", "order_class": "bracket"}) as m:
            r = brokers.AlpacaPaperBroker().bracket(
                "NVDA", 10, limit=100, stop=99, target=102, key="k1")
        self.assertEqual(r["id"], "b1")
        body = m.call_args.kwargs["body"]
        self.assertEqual(body["order_class"], "bracket")
        self.assertEqual(body["take_profit"]["limit_price"], "102.00")
        self.assertEqual(body["stop_loss"]["stop_price"], "99.00")
        self.assertEqual(body["client_order_id"], "k1")

    def test_bracket_invalido(self):
        with self.assertRaises(brokers.BrokerError):
            brokers.AlpacaPaperBroker().bracket("NVDA", 1, limit=100, stop=101, target=102)


class Piloto(unittest.TestCase):
    class Fake:
        nombre = "fake"

        def bracket(self, symbol, qty, limit, stop, target, key=None):
            return {"symbol": symbol, "qty": qty, "key": key}

    def test_propuesta_y_dry(self):
        senal = {"id": "s1", "symbol": "NVDA", "shares": 10,
                 "plan": {"entry": 100, "stop": 99, "target": 102}}
        p = piloto.propuesta(senal)
        self.assertEqual(p["qty"], 10)
        self.assertTrue(piloto.ejecutar(senal, broker=self.Fake(), confirm=False)["dry"])

    def test_bracket_papel(self):
        senal = {"id": "s1", "symbol": "NVDA", "shares": 10,
                 "plan": {"entry": 100, "stop": 99, "target": 102}}
        res = piloto.ejecutar(senal, broker=self.Fake(), confirm=True)
        self.assertFalse(res["dry"])
        self.assertEqual(res["orden"]["key"], "piloto:s1")


class IEX(unittest.TestCase):
    def test_top_of_book(self):
        doc = {"quote": {"bp": 99.5, "ap": 100.5, "bs": 10, "as": 12, "t": "2026-11-19T15:00:00Z"}}
        with mock.patch.object(alpaca, "data_request", return_value=doc):
            q = proveedores.AlpacaIEX().libro("NVDA")
        self.assertEqual(q["depth"], 1)
        self.assertEqual(q["bid"], 99.5)
        self.assertFalse(q["completo"])

    def test_no_pretende_profundidad(self):
        with self.assertRaises(proveedores.ProveedorError):
            proveedores.AlpacaIEX().profundidad("NVDA")


class ML(unittest.TestCase):
    def test_logistica_separa(self):
        X = [[0.0], [1.0], [2.0], [3.0]]
        y = [0, 0, 1, 1]
        model = ml.entrenar(X, y, epochs=1500)
        self.assertGreater(ml.predecir(model, [3.0]), 0.7)
        self.assertLess(ml.predecir(model, [0.0]), 0.3)

    def test_auc_perfecta(self):
        self.assertEqual(ml._auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]), 1.0)

    def test_walk_forward(self):
        trades = []
        for i, dia in enumerate(("2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20")):
            trades.append({
                "date": dia, "entry_time": "09:50", "risk": 1.0, "entry": 100.0,
                "or_high": 101.0, "or_low": 100.0, "qty": 10, "cost_usd": 1.0,
                "exit_reason": "target" if i % 2 else "stop",
            })
        res = ml.walk_forward(trades, frac=0.5, epochs=200)
        self.assertEqual(res["n_train"], 2)
        self.assertEqual(res["n_test"], 2)
        self.assertIn("accuracy", res)


class PrePost(unittest.TestCase):
    def _bar(self, h, m, c):
        return {"t": int(dt.datetime(2026, 11, 19, h, m, tzinfo=NY).timestamp()),
                "c": c, "v": 100}

    def test_pre(self):
        bars = [self._bar(8, 0, 101), self._bar(8, 30, 102),
                self._bar(15, 55, 100), self._bar(16, 30, 103)]
        r = prepost._resumen("X", bars, 100.0, "pre")
        self.assertEqual(r["n"], 2)
        self.assertEqual(r["last"], 102)
        self.assertAlmostEqual(r["pct"], 2.0)
        self.assertEqual(r["high"], 102)
        self.assertEqual(r["low"], 101)

    def test_post(self):
        bars = [self._bar(8, 0, 101), self._bar(15, 55, 100),
                self._bar(16, 30, 103), self._bar(17, 0, 104)]
        r = prepost._resumen("X", bars, 100.0, "post")
        self.assertEqual(r["n"], 2)
        self.assertEqual(r["ref"], 100)
        self.assertEqual(r["last"], 104)
        self.assertAlmostEqual(r["pct"], 4.0)

    def test_radar_ordena(self):
        def fake(sym, modo):
            return {"symbol": sym, "modo": modo, "n": 1, "ref": 100.0,
                    "high": 102.0, "low": 100.0, "last": 102.0,
                    "pct": 2.0 if sym == "A" else 5.0, "volume": 1.0}
        with mock.patch.object(prepost, "resumen", side_effect=fake):
            filas = prepost.radar(["A", "B"], "pre")
        self.assertEqual([f["symbol"] for f in filas], ["B", "A"])

    def test_radar_vacio(self):
        self.assertIn("Sin datos", prepost.texto([], "pre"))


class BotPrePost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tgbot_prepost", ROOT / "trader-ops" / "run" / "telegram_bot.py")
        cls.bot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bot)

    def test_pre_ticker(self):
        r = {"symbol": "NVDA", "modo": "pre", "n": 1, "ref": 100.0,
             "high": 102.0, "low": 100.0, "last": 102.0, "pct": 2.0,
             "volume": None, "rango_pct": 2.0}
        with mock.patch.object(self.bot.prepost, "resumen", return_value=r):
            txt = self.bot.c_pre(None, ["NVDA"])
        self.assertIn("Radar pre", txt)
        self.assertIn("NVDA", txt)


class VigilanteRapido(unittest.TestCase):
    def _doc(self, rules, rung=None):
        return {"rules": rules, "rung": rung or {}}

    def test_comprobar_stop_y_target(self):
        doc = self._doc([
            {"id": "r1", "symbol": "NVDA", "type": "stop", "price": 100},
            {"id": "r2", "symbol": "AMD", "type": "target", "price": 200},
        ])
        with mock.patch.object(alertas, "_load", return_value=doc), \
                mock.patch.object(alertas.cfg, "read_json", return_value={}), \
                mock.patch.object(alertas.cfg, "write_json"):
            rings = alertas.comprobar({"NVDA": 99.5, "AMD": 201.0})
        self.assertEqual(len(rings), 2)
        self.assertIn("stop", rings[0][0]["message"])
        self.assertIn("objetivo", rings[1][0]["message"])

    def test_no_repite_si_ya_sono(self):
        doc = self._doc([{"id": "r1", "symbol": "NVDA", "type": "stop", "price": 100}])
        with mock.patch.object(alertas, "_load", return_value=doc), \
                mock.patch.object(alertas.cfg, "read_json",
                                  return_value={"rung": {"r1": "2026-11-20T15:00:00Z"}}), \
                mock.patch.object(alertas.cfg, "write_json"):
            self.assertEqual(alertas.comprobar({"NVDA": 90.0}), [])

    def test_precio_ausente_no_rompe(self):
        doc = self._doc([{"id": "r1", "symbol": "NVDA", "type": "stop", "price": 100}])
        with mock.patch.object(alertas, "_load", return_value=doc), \
                mock.patch.object(alertas.cfg, "read_json", return_value={}), \
                mock.patch.object(alertas.cfg, "write_json"):
            self.assertEqual(alertas.comprobar({"AMD": 1.0}), [])

    def test_simbolos_une_reglas_y_posiciones(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "vigia_mod", ROOT / "trader-ops" / "run" / "vigia.py")
        vigia = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vigia)
        with mock.patch.object(vigia.alertas, "reglas_skill",
                               return_value=[{"symbol": "NVDA"}, {"symbol": "NVDA"}]), \
                mock.patch.object(vigia.posiciones, "abiertas",
                                  return_value=[{"symbol": "AMD"}]), \
                mock.patch.object(vigia, "revisar", return_value=[]):
            self.assertEqual(vigia.simbolos(), ["NVDA", "AMD"])


if __name__ == "__main__":
    unittest.main()
