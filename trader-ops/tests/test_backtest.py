"""Tests del backtest: mecanica ORB con barras sinteticas, sin red."""
import csv
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "trader-ops"))

from lib import backtest, brokers, estrategias, proveedores  # noqa: E402

NY = ZoneInfo("America/New_York")


def bar(h, m, o, hi, lo, c):
    return {"t": int(dt.datetime(2026, 11, 19, h, m, tzinfo=NY).timestamp()),
            "o": o, "h": hi, "l": lo, "c": c, "v": 1000}


def base_dia():
    return [
        bar(9, 30, 100, 102, 100, 101),
        bar(9, 35, 101, 102, 100, 101),
        bar(9, 40, 101, 102, 100, 101.5),
        bar(9, 45, 101.5, 103, 101.5, 102.5),
    ]


class Orb(unittest.TestCase):
    def test_objetivo(self):
        bars = base_dia() + [bar(9, 50, 102.5, 106, 102.5, 105.5)]
        t = estrategias.ORB().simular_dia("NVDA", dt.date(2026, 11, 19), bars)
        self.assertIsNotNone(t)
        self.assertEqual(t["entry"], 102.5)
        self.assertEqual(t["stop"], 101.0)
        self.assertEqual(t["target"], 105.5)
        self.assertEqual(t["qty"], 33)          # 50 / 1.5
        self.assertEqual(t["exit"], 105.5)
        self.assertEqual(t["exit_reason"], "target")
        self.assertAlmostEqual(t["gross_r"], 2.0)

    def test_stop(self):
        bars = base_dia() + [bar(9, 50, 102.5, 103, 100.5, 101)]
        t = estrategias.ORB().simular_dia("NVDA", dt.date(2026, 11, 19), bars)
        self.assertEqual(t["exit_reason"], "stop")
        self.assertEqual(t["exit"], 101.0)
        self.assertAlmostEqual(t["gross_r"], -1.0)

    def test_hueco_bajista(self):
        bars = base_dia() + [bar(9, 50, 100, 101, 99, 100)]
        t = estrategias.ORB().simular_dia("NVDA", dt.date(2026, 11, 19), bars)
        self.assertEqual(t["exit_reason"], "stop_gap")
        self.assertEqual(t["exit"], 100.0)
        self.assertAlmostEqual(t["gross_r"], -1.6667)

    def test_misma_barra_stop_y_objetivo(self):
        bars = base_dia() + [bar(9, 50, 102.5, 106, 100.5, 105)]
        t = estrategias.ORB().simular_dia("NVDA", dt.date(2026, 11, 19), bars)
        self.assertEqual(t["exit_reason"], "stop_mismo_bar")
        self.assertEqual(t["exit"], 101.0)

    def test_flat(self):
        bars = base_dia() + [bar(15, 50, 102.5, 103, 102, 102.8)]
        t = estrategias.ORB().simular_dia("NVDA", dt.date(2026, 11, 19), bars)
        self.assertEqual(t["exit_reason"], "flat")
        self.assertEqual(t["exit"], 102.8)
        self.assertAlmostEqual(t["gross_r"], 0.2)

    def test_sin_ruptura(self):
        bars = base_dia()[:-1] + [bar(9, 45, 101, 101.9, 101, 101.9),
                                  bar(15, 50, 101.9, 102, 101, 101.5)]
        self.assertIsNone(estrategias.ORB().simular_dia(
            "NVDA", dt.date(2026, 11, 19), bars))

    def test_riesgo_demasiado_estrecho(self):
        bars = [bar(9, 30, 101.96, 102, 101.95, 101.97),
                bar(9, 35, 101.97, 102, 101.95, 101.97),
                bar(9, 40, 101.97, 102, 101.95, 101.97),
                bar(9, 45, 101.97, 102.1, 101.97, 102.0)]
        self.assertIsNone(estrategias.ORB().simular_dia(
            "NVDA", dt.date(2026, 11, 19), bars))

    def test_costes(self):
        bars = base_dia() + [bar(9, 50, 102.5, 106, 102.5, 105.5)]
        t = estrategias.ORB().simular_dia(
            "NVDA", dt.date(2026, 11, 19), bars, max_loss=10,
            comision_fn=lambda notional: 3.0)
        self.assertEqual(t["qty"], 6)
        self.assertAlmostEqual(t["cost_usd"], 3.0)
        self.assertAlmostEqual(t["net_r"], 2.0 - 3.0 / (6 * 1.5), places=4)

    def test_orb_low(self):
        bars = base_dia() + [bar(9, 50, 102.5, 108, 102.5, 107.5)]
        t = estrategias.ORBBajo().simular_dia("NVDA", dt.date(2026, 11, 19), bars)
        self.assertEqual(t["stop"], 100.0)
        self.assertEqual(t["target"], 107.5)
        self.assertEqual(t["qty"], 20)          # 50 / 2.5
        self.assertEqual(t["exit_reason"], "target")

    def test_slippage(self):
        bars = base_dia() + [bar(9, 50, 102.5, 106, 102.5, 105.5)]
        t = estrategias.ORB().simular_dia(
            "NVDA", dt.date(2026, 11, 19), bars, slippage_bps=10)
        self.assertGreater(t["entry_fill"], t["entry"])
        self.assertLess(t["exit_fill"], t["exit"])
        self.assertLess(t["gross_r"], 2.0)


class Resumen(unittest.TestCase):
    def test_metricas(self):
        trades = [
            {"date": "2026-11-19", "entry_time": "09:50", "exit_time": "09:55",
             "symbol": "AAA", "net_r": 2.0, "pnl_usd": 100.0},
            {"date": "2026-11-19", "entry_time": "10:50", "exit_time": "11:05",
             "symbol": "AAA", "net_r": -1.0, "pnl_usd": -50.0},
            {"date": "2026-11-20", "entry_time": "09:50", "exit_time": "10:00",
             "symbol": "BBB", "net_r": 0.5, "pnl_usd": 25.0},
        ]
        r = backtest.resumen(trades)
        self.assertEqual(r["n"], 3)
        self.assertEqual(r["wins"], 2)
        self.assertAlmostEqual(r["win_rate"], 2 / 3.0)
        self.assertAlmostEqual(r["total_net_r"], 1.5)
        self.assertAlmostEqual(r["total_pnl"], 75.0)
        self.assertAlmostEqual(r["max_dd_r"], -1.0)
        self.assertAlmostEqual(r["profit_factor"], 125.0 / 50.0)
        self.assertAlmostEqual(r["avg_hold_min"], 10.0, places=3)
        self.assertEqual(r["by_symbol"]["AAA"]["n"], 2)


class Utilidades(unittest.TestCase):
    def test_partir_por_fechas(self):
        trades = [{"date": "2026-11-17", "net_r": 1.0},
                  {"date": "2026-11-18", "net_r": -1.0},
                  {"date": "2026-11-19", "net_r": 2.0}]
        is_t, oos_t = backtest.partir(trades, 0.7)
        self.assertEqual(len(is_t), 2)
        self.assertEqual(len(oos_t), 1)
        self.assertEqual(oos_t[0]["date"], "2026-11-19")

    def test_features_csv(self):
        trades = [{"date": "2026-11-19", "entry_time": "09:50", "symbol": "NVDA",
                   "or_high": 102, "or_low": 100, "or_mid": 101, "entry": 102.5,
                   "entry_fill": 102.5, "stop": 101, "target": 105.5, "qty": 33,
                   "risk": 1.5, "exit_fill": 105.5, "exit_reason": "target",
                   "gross_r": 2.0, "net_r": 2.0, "cost_usd": 0, "pnl_usd": 99}]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "features.csv"
            backtest.guardar_features(p, trades)
            with p.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "NVDA")
        self.assertEqual(rows[0]["net_r"], "2.0")


class Brokers(unittest.TestCase):
    def test_null_no_envia(self):
        with self.assertRaises(brokers.BrokerError):
            brokers.get("null").comprar("NVDA", 1)

    def test_paper_fill_e_idempotencia(self):
        with tempfile.TemporaryDirectory() as td:
            b = brokers.PaperBroker(quote_fn=lambda s: 100.0, path=Path(td) / "o.json")
            o1 = b.comprar("NVDA", 10, limit=101, key="k1")
            o2 = b.comprar("NVDA", 10, limit=101, key="k1")
            self.assertEqual(o1["fill"], 100.0)
            self.assertEqual(o1["id"], o2["id"])
            self.assertFalse(o1["real"])
            v = b.vender("NVDA", 5, limit=99, key="k2")
            self.assertEqual(v["fill"], 100.0)

    def test_paper_rechaza_limite_imposible(self):
        with tempfile.TemporaryDirectory() as td:
            b = brokers.PaperBroker(quote_fn=lambda s: 100.0, path=Path(td) / "o.json")
            with self.assertRaises(brokers.BrokerError):
                b.comprar("NVDA", 1, limit=99)


class Nivel2(unittest.TestCase):
    def test_sin_proveedor_falla(self):
        with self.assertRaises(proveedores.ProveedorError):
            proveedores.get("ninguno").libro("NVDA")

    def test_polygon_sin_clave_falla(self):
        with self.assertRaises(proveedores.ProveedorError):
            proveedores.get("polygon").libro("NVDA")


if __name__ == "__main__":
    unittest.main()
