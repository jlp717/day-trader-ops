"""Tests de las hipotesis nuevas: hueco a la baja (gap reclaim) y swing RSI-2."""
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "trader-ops"))

from lib import brokers, estrategias, ibkr, niveles, raw, swing, tesis  # noqa: E402

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


class Salidas(unittest.TestCase):
    def _b(self, m, o, h, l, c):
        t = int(dt.datetime(2026, 11, 19, 10, m, tzinfo=NY).timestamp())
        return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": 100}

    def test_fixed_no_toca_nada(self):
        bars = [self._b(0, 100, 100, 100, 100),
                self._b(5, 100, 101.2, 100.1, 100.5),
                self._b(10, 100.5, 100.8, 100.0, 100.2)]
        px, motivo, _ = estrategias.ORB()._salida(
            bars, 0, 99.0, 102.0, dt.time(15, 50), entry=100.0, mode="fixed")
        self.assertEqual(motivo, "eod")
        self.assertEqual(px, 100.2)

    def test_be_trail_saca_breakeven_mas(self):
        bars = [self._b(0, 100, 100, 100, 100),
                self._b(5, 100, 101.2, 100.1, 100.5),
                self._b(10, 100.5, 100.8, 100.0, 100.2)]
        px, motivo, _ = estrategias.ORB()._salida(
            bars, 0, 99.0, 102.0, dt.time(15, 50), entry=100.0,
            mode="be_trail", be_at_r=1.0, trail_r=1.0)
        self.assertEqual(motivo, "stop")
        self.assertGreater(px, 100.0)
        self.assertLess(px, 101.2)

    def test_trailing_no_dispara_antes_de_activarse(self):
        bars = [self._b(0, 100, 100, 100, 100),
                self._b(5, 100, 100.4, 99.6, 99.8),
                self._b(10, 99.8, 99.9, 99.1, 99.2)]
        px, motivo, _ = estrategias.ORB()._salida(
            bars, 0, 99.0, 102.0, dt.time(15, 50), entry=100.0,
            mode="be_trail", be_at_r=1.0, trail_r=1.0)
        self.assertEqual(motivo, "eod")

    def test_backtest_pasa_el_modo(self):
        import inspect
        from lib import backtest
        self.assertIn("exit_mode", inspect.signature(backtest.correr).parameters)


class TesisAguante(unittest.TestCase):
    def _serie(self, n=260, inicio=100.0, paso=0.4):
        bars = []
        px = inicio
        for _ in range(n):
            px += paso
            bars.append({"c": px, "h": px * 1.01, "l": px * 0.99, "o": px, "v": 1e6})
        return bars

    def test_intacta(self):
        with mock.patch.object(tesis.datos, "chart",
                               return_value={"bars": self._serie()}), \
                mock.patch.object(tesis, "fundamentos", return_value={}):
            r = tesis.evaluar("X")
        self.assertEqual(r["veredicto"], "intacta")

    def test_zona_venta_en_maximos(self):
        with mock.patch.object(tesis.datos, "chart",
                               return_value={"bars": self._serie()}), \
                mock.patch.object(tesis, "fundamentos", return_value={}):
            r = tesis.evaluar("X")
        self.assertTrue(r["zona_venta"])

    def test_rota_por_debajo_de_sma200(self):
        bars = self._serie()
        bars[-1]["c"] = bars[-1]["c"] * 0.5
        with mock.patch.object(tesis.datos, "chart", return_value={"bars": bars}), \
                mock.patch.object(tesis, "fundamentos", return_value={}):
            r = tesis.evaluar("X")
        self.assertEqual(r["veredicto"], "rota")

    def test_observacion_por_caida(self):
        bars = self._serie()
        alto = max(b["h"] for b in bars)
        bars[-1]["c"] = alto * 0.80
        with mock.patch.object(tesis.datos, "chart", return_value={"bars": bars}), \
                mock.patch.object(tesis, "fundamentos", return_value={}):
            r = tesis.evaluar("X")
        self.assertIn(r["veredicto"], ("observacion", "rota"))

    def test_fundamentos_malos_bajan_el_largo(self):
        with mock.patch.object(tesis.datos, "chart", return_value={"bars": self._serie()}), \
                mock.patch.object(tesis, "fundamentos",
                                  return_value={"revenueGrowthTTMYoy": -5.0}):
            r = tesis.evaluar("X")
        self.assertEqual(r["corto"]["veredicto"], "a favor")
        self.assertIn(r["largo"]["veredicto"], ("en riesgo", "rota"))

    def test_etiquetas_de_noticias(self):
        self.assertIn("upgrade", tesis._etiquetas("Morgan Stanley raises price target on X"))
        self.assertIn("riesgo", tesis._etiquetas("Company faces SEC investigation"))
        self.assertEqual(tesis._etiquetas("Weather is nice today"), [])

    def test_marcar_y_liberar(self):
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp()) / "tesis.json"
        with mock.patch.object(tesis, "ESTADO", tmp):
            tesis.marcar("nvda", True)
            self.assertTrue(tesis.en_aguante("NVDA"))
            tesis.marcar("NVDA", False)
            self.assertFalse(tesis.en_aguante("NVDA"))


class IBKR(unittest.TestCase):
    def test_papel_exige_du(self):
        ibkr.es_papel("DU1234567")
        with self.assertRaises(ibkr.IBKRError):
            ibkr.es_papel("U1234567")
        with self.assertRaises(ibkr.IBKRError):
            ibkr.es_papel("")

    def test_orden_construye_cuerpo(self):
        with mock.patch.object(ibkr, "conid", return_value=265598), \
                mock.patch.object(ibkr, "_req", return_value={"order_id": "1"}) as m:
            ibkr.orden("DU1", "AAPL", "buy", 10, limit=165.5)
        cuerpo = m.call_args.args[2][0]
        self.assertEqual(cuerpo["conid"], 265598)
        self.assertEqual(cuerpo["side"], "BUY")
        self.assertEqual(cuerpo["orderType"], "LMT")
        self.assertEqual(cuerpo["price"], 165.5)

    def test_orden_rechaza_cuenta_real(self):
        with mock.patch.object(ibkr, "_req", return_value={}) as m:
            with self.assertRaises(ibkr.IBKRError):
                ibkr.orden("U1", "AAPL", "BUY", 1)
        m.assert_not_called()

    def test_broker_sin_cuenta_falla(self):
        b = brokers.IBKRPaperBroker(account="")
        with self.assertRaises(brokers.BrokerError):
            b.comprar("AAPL", 1, limit=100)

    def test_broker_papel_delega(self):
        b = brokers.IBKRPaperBroker(account="DU1")
        with mock.patch.object(ibkr, "orden", return_value={"ok": True}) as m:
            self.assertEqual(b.comprar("AAPL", 2, limit=100), {"ok": True})
        self.assertEqual(m.call_args.args[1], "AAPL")


class RawXetra(unittest.TestCase):
    def _bars(self):
        out = []
        for dia in (dt.date(2026, 11, 18), dt.date(2026, 11, 19)):
            for h, m, px in ((9, 0, 100.0), (9, 5, 100.4), (9, 10, 100.2), (9, 30, 100.6)):
                t = int(dt.datetime(dia.year, dia.month, dia.day, h, m,
                                    tzinfo=ZoneInfo("Europe/Berlin")).timestamp())
                out.append({"t": t, "o": px, "h": px + 0.2, "l": px - 0.2, "c": px, "v": 100})
        return out

    def test_encuentra_la_vela_de_las_0900(self):
        filas = raw.senales(self._bars(), "eu")
        self.assertEqual(len(filas), 2)
        self.assertEqual(filas[0]["mercado"], "eu")
        self.assertIsNotNone(filas[0]["pct"])

    def test_el_mercado_cambia_la_hora(self):
        self.assertEqual(raw.senales(self._bars(), "us"), [])

    def test_texto_menciona_cet(self):
        fila = raw.senales(self._bars(), "eu")[-1]
        self.assertIn("09:00 CET", raw.texto_senal(fila, "SAP.DE", "eu"))


if __name__ == "__main__":
    unittest.main()
