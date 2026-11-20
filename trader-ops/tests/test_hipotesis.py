"""Tests de las hipotesis nuevas: hueco a la baja (gap reclaim) y swing RSI-2."""
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "trader-ops"))

from lib import estrategias, niveles, swing  # noqa: E402

NY = ZoneInfo("America/New_York")
DAY = dt.date(2026, 11, 19)


def bar(h, m, o, hi, lo, c, day=DAY):
    t = int(dt.datetime(day.year, day.month, day.day, h, m, tzinfo=NY).timestamp())
    return {"t": t, "o": o, "h": hi, "l": lo, "c": c, "v": 1000}


class GapReclaim(unittest.TestCase):
    def _dia(self):
        return [
            bar(9, 30, 97.0, 97.5, 96.8, 97.2),
            bar(9, 35, 97.2, 97.9, 97.0, 97.8),   # cierre por encima del maximo inicial
            bar(9, 40, 97.9, 100.5, 97.8, 100.2),  # toca el cierre previo
        ]

    def test_entra_en_la_recuperacion_y_cobra_el_hueco(self):
        t = estrategias.GapReclaim().simular_dia(
            "X", DAY, self._dia(), prev_close=100.0, comision_fn=None)
        self.assertIsNotNone(t)
        self.assertAlmostEqual(t["entry"], 97.8, places=2)
        self.assertAlmostEqual(t["stop"], 96.8, places=2)
        self.assertAlmostEqual(t["target"], 100.0, places=2)
        self.assertEqual(t["exit_reason"], "target")
        self.assertEqual(t["gap_pct"], -3.0)

    def test_sin_hueco_no_hay_trade(self):
        t = estrategias.GapReclaim().simular_dia(
            "X", DAY, self._dia(), prev_close=97.0)
        self.assertIsNone(t)

    def test_sin_recuperacion_no_hay_trade(self):
        bars = [bar(9, 30, 97.0, 99.0, 96.8, 97.2),
                bar(9, 35, 97.2, 97.5, 97.0, 97.1),
                bar(9, 40, 97.1, 97.4, 96.9, 97.0)]
        t = estrategias.GapReclaim().simular_dia("X", DAY, bars, prev_close=100.0)
        self.assertIsNone(t)

    def test_sin_prev_close_no_hay_trade(self):
        self.assertIsNone(estrategias.GapReclaim().simular_dia("X", DAY, self._dia()))

    def test_registro_incluye_la_estrategia(self):
        self.assertIn("gap_reclaim", estrategias.nombres())
        self.assertTrue(getattr(estrategias.get("gap_reclaim"), "necesita_prev_close", False))


class SwingRSI2(unittest.TestCase):
    def test_rsi_de_serie_siempre_alcista(self):
        closes = [float(i) for i in range(1, 20)]
        r = swing.rsi(closes, 2)
        self.assertIsNone(r[0])
        self.assertEqual(r[-1], 100.0)

    def test_rsi_de_serie_siempre_bajista(self):
        closes = [float(20 - i) for i in range(1, 20)]
        r = swing.rsi(closes, 2)
        self.assertEqual(r[-1], 0.0)

    def test_sma(self):
        self.assertEqual(swing.sma([1, 2, 3, 4], 2), [None, 1.5, 2.5, 3.5])

    def _barras(self, dias=260):
        """Tendencia suave al alza con una caida fuerte al final."""
        bars = []
        px = 100.0
        for i in range(dias):
            d = DAY - dt.timedelta(days=dias - i)
            if i < dias - 3:
                px *= 1.001
            else:
                px *= 0.96
            bars.append({"t": int(dt.datetime(d.year, d.month, d.day, 16, 0, tzinfo=NY).timestamp()),
                         "o": px, "h": px * 1.01, "l": px * 0.99, "c": px, "v": 1e6})
        return bars

    def test_detecta_sobreventa_tras_caida(self):
        bars = self._barras()
        self.assertTrue(swing.senales(bars))

    def test_simular_genera_trades_con_costes(self):
        trades = swing.simular("X", self._barras())
        self.assertTrue(trades)
        t = trades[0]
        self.assertIn("net_pct", t)
        self.assertLess(t["net_pct"], t["gross_pct"])

    def test_resumen_y_split(self):
        trades = [{"entry_date": "2026-01-0%d" % (i % 9 + 1), "net_pct": 1.0 if i % 2 else -1.0,
                   "gross_pct": 1.5 if i % 2 else -0.5, "days": 2} for i in range(10)]
        r = swing.resumen(trades)
        self.assertEqual(r["n"], 10)
        self.assertAlmostEqual(r["expectancy"], 0.0)
        is_t, oos = swing.partir(trades, 0.7)
        self.assertTrue(is_t)
        self.assertTrue(oos)


class NivelesManuales(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = Path(tempfile.mkdtemp()) / "niveles.json"
        self.p = mock.patch.object(niveles, "PATH", self.tmp)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_poner_y_comprobar_stop(self):
        niveles.poner("TLK", stop=11.20, target=12.38)
        self.assertEqual(niveles.comprobar({"TLK": 11.10})[0][1], "stop")

    def test_no_repite_el_mismo_dia(self):
        niveles.poner("TLK", stop=11.20)
        self.assertTrue(niveles.comprobar({"TLK": 11.0}))
        self.assertEqual(niveles.comprobar({"TLK": 11.0}), [])

    def test_target(self):
        niveles.poner("SIRI", stop=31.80, target=33.76)
        hits = niveles.comprobar({"SIRI": 34.0})
        self.assertEqual(hits[0][1], "target")

    def test_stop_por_encima_del_objetivo_falla(self):
        with self.assertRaises(ValueError):
            niveles.poner("X", stop=10.0, target=9.0)

    def test_quitar(self):
        niveles.poner("X", stop=9.0)
        self.assertTrue(niveles.quitar("X"))
        self.assertFalse(niveles.quitar("X"))


class BotNivel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tgbot_nivel", ROOT / "trader-ops" / "run" / "telegram_bot.py")
        cls.bot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bot)

    def test_guarda_nivel(self):
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp()) / "niveles.json"
        with mock.patch.object(self.bot.niveles, "PATH", tmp):
            r = self.bot.c_nivel(None, ["TLK", "11.20", "12.38"])
            self.assertIn("Nivel guardado", r)
            self.assertIn("11.20", r[:80] + r)

    def test_uso_sin_datos(self):
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp()) / "niveles.json"
        with mock.patch.object(self.bot.niveles, "PATH", tmp):
            self.assertIn("Uso:", self.bot.c_nivel(None, ["TLK"]))


if __name__ == "__main__":
    unittest.main()
