"""Operativa manual: alertas de posicion, cierres parciales, limites y frases nuevas."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "trader-ops"))

from lib import alertas, cfg, posiciones, referencias  # noqa: E402
from lib import zonatiempo as zt  # noqa: E402


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self._paths = (posiciones.PATH, alertas.REGLAS, alertas.ESTADO, alertas.XETRA, referencias.PATH)
        posiciones.PATH = d / "posiciones.json"
        alertas.REGLAS = d / "alerts.json"
        alertas.ESTADO = d / "state" / "alerts.json"
        alertas.XETRA = d / "alertas_xetra.json"
        referencias.PATH = d / "referencias.json"

    def tearDown(self):
        (posiciones.PATH, alertas.REGLAS, alertas.ESTADO, alertas.XETRA,
         referencias.PATH) = self._paths
        self.tmp.cleanup()


class AlertasDePosicion(Base):
    def test_abrir_arma_stop_y_objetivo(self):
        p = posiciones.abrir("NVDA", 100.0, 8, stop=98.0, target=104.0)
        self.assertEqual(len(p["alert_ids"]), 2)
        reglas = alertas.reglas()
        self.assertEqual(len(reglas), 2)
        tipos = {r["type"]: r["price"] for r in reglas}
        self.assertEqual(tipos, {"stop": 98.0, "target": 104.0})
        self.assertTrue(all(r["date"] == zt.ny().date().isoformat() for r in reglas))

    def test_cerrar_total_desarma(self):
        posiciones.abrir("NVDA", 100.0, 8, stop=98.0, target=104.0)
        c = posiciones.cerrar("NVDA", 104.0, motivo="objetivo")
        self.assertAlmostEqual(c["pnl_usd"], 32.0)
        self.assertAlmostEqual(c["R"], 2.0)
        self.assertFalse(c["parcial"])
        self.assertEqual(alertas.reglas(), [])

    def test_cierre_parcial_mantiene_alertas_y_posicion(self):
        posiciones.abrir("NVDA", 100.0, 8, stop=98.0, target=104.0)
        c = posiciones.cerrar("NVDA", 102.0, qty=3)
        self.assertTrue(c["parcial"])
        self.assertAlmostEqual(c["pnl_usd"], 6.0)
        self.assertAlmostEqual(c["restante"], 5.0)
        abiertas = posiciones.abiertas()
        self.assertEqual(len(abiertas), 1)
        self.assertAlmostEqual(abiertas[0]["qty"], 5.0)
        self.assertEqual(len(alertas.reglas()), 2)

    def test_cierre_parcial_y_final_suma_pnl(self):
        posiciones.abrir("NVDA", 100.0, 10, stop=98.0, target=104.0)
        posiciones.cerrar("NVDA", 102.0, qty=4)
        posiciones.cerrar("NVDA", 103.0, qty=6)
        p = posiciones.pnl()
        self.assertAlmostEqual(p["pnl_usd"], 26.0)
        self.assertEqual(p["operaciones"], 2)
        self.assertFalse(posiciones.abiertas())
        self.assertEqual(alertas.reglas(), [])

    def test_xetra_arma_en_su_motor(self):
        p = posiciones.abrir("NVD.DE", 100.0, 5, stop=98.0, target=104.0)
        self.assertIsNone(p["alert_error"])
        self.assertEqual(len(p["alert_ids"]), 2)
        self.assertEqual(alertas.reglas_skill(), [])
        self.assertEqual(len(alertas.reglas_xetra()), 2)
        c = posiciones.cerrar("NVD.DE", 104.0)
        self.assertAlmostEqual(c["R"], 2.0)
        self.assertEqual(alertas.reglas_xetra(), [])

    def test_mover_stop_rearma(self):
        posiciones.abrir("NVDA", 100.0, 8, stop=98.0, target=104.0)
        r = posiciones.cambiar("NVDA", stop=99.5)
        self.assertTrue(r["cambios"][0]["aviso"])
        stops = [x for x in alertas.reglas() if x["type"] == "stop"]
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["price"], 99.5)
        self.assertEqual(posiciones.abierta_de("NVDA")["stop"], 99.5)

    def test_no_duplica_regla(self):
        self.assertTrue(alertas.armar("NVDA", "stop", 98.0, "x-1")[0])
        ok, motivo = alertas.armar("NVDA", "stop", 97.0, "x-1")
        self.assertTrue(ok)
        self.assertEqual(motivo, "ya existia")
        self.assertEqual(len(alertas.reglas()), 1)

    def test_comprobar_xetra_dispara_una_vez(self):
        from unittest import mock
        alertas.armar("NVD.DE", "stop", 98.0, "x-stop")
        with mock.patch.object(alertas.datos, "quote",
                               lambda s: {"price": 97.5, "currency": "EUR"}):
            primera = alertas.comprobar_xetra()
            segunda = alertas.comprobar_xetra()
        self.assertEqual(len(primera), 1)
        self.assertIn("NVD.DE", primera[0][0]["message"])
        self.assertEqual(segunda, [])


class EntradaManual(Base):
    @classmethod
    def setUpClass(cls):
        cls.bot = _cargar("tgbot_ops", ROOT / "trader-ops" / "run" / "telegram_bot.py")

    def setUp(self):
        super().setUp()
        self._trader = cfg.TRADER
        self._tmp_trader = tempfile.TemporaryDirectory()
        cfg.TRADER = Path(self._tmp_trader.name)
        (cfg.TRADER / "state").mkdir(parents=True, exist_ok=True)
        self._veredicto = self.bot._veredicto_hoy
        self.bot._veredicto_hoy = lambda sym: (None, None)

    def tearDown(self):
        self.bot._veredicto_hoy = self._veredicto
        cfg.TRADER = self._trader
        self._tmp_trader.cleanup()
        super().tearDown()

    def test_entre_registra_y_avisa_fuera_de_senal(self):
        txt = self.bot.c_entre(None, ["NVDA", "100", "8", "98", "104"])
        self.assertIn("Registrada", txt)
        self.assertIn("Avisos armados", txt)
        self.assertIn("FUERA DE SEÑAL A", txt)
        self.assertEqual(len(posiciones.abiertas()), 1)
        self.assertEqual(len(alertas.reglas()), 2)

    def test_entre_rechaza_stop_por_encima(self):
        txt = self.bot.c_entre(None, ["NVDA", "100", "8", "101", "104"])
        self.assertIn("por debajo de la entrada", txt)
        self.assertEqual(posiciones.abiertas(), [])

    def test_entre_rechaza_duplicado(self):
        self.bot.c_entre(None, ["NVDA", "100", "8", "98", "104"])
        txt = self.bot.c_entre(None, ["NVDA", "101", "2", "99", "105"])
        self.assertIn("Ya hay una posicion abierta", txt)
        self.assertEqual(len(posiciones.abiertas()), 1)

    def test_sali_parcial(self):
        self.bot.c_entre(None, ["NVDA", "100", "8", "98", "104"])
        txt = self.bot.c_sali(None, ["NVDA", "102", "3"])
        self.assertIn("Cierre parcial", txt)
        self.assertIn("Quedan 5", txt)

    def test_posiciones_marca_overnight(self):
        p = posiciones.abrir("SLS", 20.12, 87, stop=19.55, target=21.26)
        doc = cfg.read_json(posiciones.PATH, {}) or {}
        for x in doc["posiciones"]:
            if x["id"] == p["id"]:
                x["abierta_madrid"] = "2026-11-17T16:00:00+01:00"
        cfg.write_json(posiciones.PATH, doc)
        txt = self.bot.c_posiciones(None, [])
        self.assertIn("overnight", txt)
        self.assertIn("fuera del plan intradía", txt)

    def test_ref_y_precios(self):
        from unittest import mock
        q = {"price": 20.12, "currency": "USD", "data_time": "2026-12-01T15:05:00Z",
             "age_seconds": 10, "exchange": "NMS"}
        with mock.patch.object(self.bot.datos, "quote", lambda s: q):
            txt = self.bot.c_ref(None, ["SLS", "20.13", "tv"])
            self.assertIn("TradingView", txt)
            txt = self.bot.c_precios(None, ["SLS"])
        self.assertIn("Yahoo: 20.12", txt)
        self.assertIn("TradingView: 20.13", txt)
        self.assertIn("Diferencia entre fuentes", txt)
        self.assertIn("no hay plan", txt)

    def test_ref_fuente_invalida(self):
        txt = self.bot.c_ref(None, ["SLS", "20.13", "foo"])
        self.assertIn("fuente no valida", txt)

    def test_entre_incluye_referencia(self):
        from unittest import mock
        with mock.patch.object(self.bot.datos, "quote", lambda s: {
                "price": 20.12, "currency": "USD", "data_time": "2026-12-01T15:05:00Z",
                "age_seconds": 10, "exchange": "NMS"}):
            self.bot.c_ref(None, ["SLS", "20.13", "tv"])
        txt = self.bot.c_entre(None, ["SLS", "20.12", "87", "19.55", "21.26"])
        self.assertIn("Referencias: TradingView 20.13", txt)

    def test_alertas_lista_los_dos_motores(self):
        alertas.armar("NVDA", "stop", 98.0, "a-1")
        alertas.armar("NVD.DE", "target", 150.0, "a-2")
        txt = self.bot.c_alertas(None, [])
        self.assertIn("NVDA", txt)
        self.assertIn("NVD.DE", txt)
        self.assertIn("Xetra", txt)

    def test_resultados_lee_la_lista_del_skill(self):
        from types import SimpleNamespace
        from unittest import mock
        data = [{"ticker": "NVDA", "result": {"entity": "NVIDIA CORP", "rows": [
            {"fiscal": "Q2 2027", "form": "10-Q", "filed": "2026-08-26",
             "revenue": 96221000000, "revenue_yoy": 105.9, "eps_diluted": 2.46,
             "gross_margin": 75.0}]}}]
        with mock.patch.object(self.bot.skills, "analyst",
                               lambda syms: SimpleNamespace(data=data, stderr="")):
            txt = self.bot.c_resultados(None, ["NVDA"])
        self.assertIn("Q2 2027", txt)
        self.assertIn("96221000000", txt)


class AlertasOrquestador(Base):
    @classmethod
    def setUpClass(cls):
        cls.orq = _cargar("orq_ops", ROOT / "trader-ops" / "run" / "orquestador.py")

    def test_ring_de_stop_se_envia_y_avisa_proximidad(self):
        from types import SimpleNamespace
        from unittest import mock
        from lib import avisos

        alertas.armar("NVDA", "stop", 98.0, "pos-x-stop")
        enviados = []

        class Bot:
            def send(self, text, **kw):
                enviados.append(text)
                return 1

        with mock.patch.object(self.orq.posiciones, "abiertas", lambda: [
                {"id": "x", "symbol": "NVDA", "stop": 98.0, "target": 104.0}]), \
                mock.patch.object(self.orq.datos, "quote", lambda sym: {"price": 98.1}), \
                mock.patch.object(self.orq.skills, "alerts_check", lambda: SimpleNamespace(
                    data={"rings": [{"id": "pos-x-stop", "symbol": "NVDA",
                                     "message": "NVDA is at or below $98.00: your stop $98."}]})), \
                mock.patch.object(self.orq.registro, "marcar_resultados", lambda p: None), \
                mock.patch.object(avisos, "send_once",
                                  lambda bot, key, text, **kw: enviados.append(text) or 1):
            self.orq.Runner(Bot()).t_alertas(zt.madrid())
        texto = "\n".join(enviados)
        self.assertIn("STOP del plan", texto)
        self.assertIn("de tu stop", texto)

    def test_xetra_solo_usa_su_motor(self):
        from unittest import mock
        alertas.armar("NVD.DE", "stop", 98.0, "x-stop")
        enviados = []

        class Bot:
            def send(self, text, **kw):
                enviados.append(text)
                return 1

        with mock.patch.object(self.orq.skills, "alerts_check",
                               side_effect=AssertionError("no debe llamarse")), \
                mock.patch.object(alertas.datos, "quote",
                                  lambda s: {"price": 97.5, "currency": "EUR"}), \
                mock.patch.object(self.orq.posiciones, "abiertas", lambda: []), \
                mock.patch.object(self.orq.registro, "marcar_resultados", lambda p: None):
            self.orq.Runner(Bot()).t_alertas(zt.madrid())
        texto = "\n".join(enviados)
        self.assertIn("NVD.DE", texto)
        self.assertIn("97.50", texto)


class SeguirGanadores(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = _cargar("tgbot_seguir", ROOT / "trader-ops" / "run" / "telegram_bot.py")

    def test_incluye_ticker_manual(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            (state / "orb_candidates.json").write_text('{"hits": [{"symbol": "NVDA"}]}', encoding="utf-8")
            with mock.patch.object(self.bot.cfg, "STATE", state):
                txt = self.bot.c_incluir(None, ["MNSO"])
            self.assertIn("Añadido", txt)
            doc = __import__("json").loads((state / "orb_candidates.json").read_text(encoding="utf-8"))
            self.assertEqual([h["symbol"] for h in doc["hits"]], ["NVDA", "MNSO"])

    def test_anade_sin_duplicar(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            (state / "orb_candidates.json").write_text(
                '{"hits": [{"symbol": "NVDA"}]}', encoding="utf-8")
            fake = {"filas": [{"symbol": "NVDA"}, {"symbol": "SLS"}, {"symbol": "SLN"}]}
            with mock.patch.object(self.bot.cfg, "STATE", state), \
                    mock.patch.object(self.bot.ganadores, "premarket", lambda top: fake), \
                    mock.patch.object(self.bot.ganadores, "intradia", lambda top: fake), \
                    mock.patch.object(self.bot.calendario, "session_madrid",
                                      lambda d: (None, None, "test")):
                txt = self.bot.c_seguir(None, ["5"])
            self.assertIn("SLS", txt)
            self.assertIn("SLN", txt)
            doc = __import__("json").loads((state / "orb_candidates.json").read_text(encoding="utf-8"))
            syms = [h["symbol"] for h in doc["hits"]]
            self.assertEqual(syms, ["NVDA", "SLS", "SLN"])


class AnalisisCompleto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = _cargar("tgbot_analisis", ROOT / "trader-ops" / "run" / "telegram_bot.py")

    def test_cadena_disparada_muestra_plan_y_criterios(self):
        from unittest import mock
        cadena = {
            "entry": {"status": "triggered", "time": "10:05"},
            "plan": {"entry": 100.0, "stop": 98.0, "target": 104.0, "target_r": 2.0,
                     "flat_by": "15:55", "risk_per_share": 2.0},
            "tm": {"mc": {"p_target": 0.41, "p_stop": 0.30, "replays": 10000, "seed": 7},
                   "history": {"triggered": 33, "target": 13, "stop": 14}},
            "budget": {"orders": [{"qty": 25, "max_loss": 50.0}]},
            "risk": {"results": [{"verdict": "PASS", "reasons": []}]},
        }
        ev = {"verdict": "DESCARTADA", "reasons": ["historico: Wilson por debajo del break-even"],
              "numbers": {"ev": -0.12, "cost_r": 0.15, "hist_n": 33, "wilson_low": 0.25,
                          "wilson_high": 0.56, "break_even": 0.333, "p_target_mc": 0.41}}
        ctx = {"analyst": {"filed": "2026-08-26", "fiscal": "Q2 2027", "form": "10-Q"}}
        with mock.patch.object(self.bot, "_cadena", lambda s: cadena), \
                mock.patch.object(self.bot.proceso, "contexto_desde_cadena", lambda s, c: (ctx, ev)), \
                mock.patch.object(self.bot.proceso, "analyst_info", lambda s: ctx["analyst"]), \
                mock.patch.object(self.bot, "_veredicto_hoy", lambda s: (None, None)), \
                mock.patch.object(self.bot.datos, "quote", lambda s: {"price": 100.5, "age_seconds": 5}), \
                mock.patch.object(self.bot.skills, "news",
                                  lambda syms, hours=24: type("R", (), {"data": {}})()):
            txt = self.bot._analisis_natural("NVDA")
        self.assertIn("Plan: entrada 100.00", txt)
        self.assertIn("Criterios: <b>DESCARTADA</b>", txt)
        self.assertIn("fuera de SEÑAL A", txt)
        self.assertIn("Wilson 25.0-56.0%", txt)

    def test_sin_ruptura_no_inventa_plan(self):
        from unittest import mock
        cadena = {"entry": {"status": "waiting", "reason": "rango no formado"}}
        with mock.patch.object(self.bot, "_cadena", lambda s: cadena), \
                mock.patch.object(self.bot.proceso, "analyst_info", lambda s: {}), \
                mock.patch.object(self.bot, "_veredicto_hoy", lambda s: (None, None)), \
                mock.patch.object(self.bot.datos, "quote", lambda s: {"price": 100.0, "age_seconds": 5}), \
                mock.patch.object(self.bot.skills, "news",
                                  lambda syms, hours=24: type("R", (), {"data": {}})()):
            txt = self.bot._analisis_natural("NVDA")
        self.assertIn("SIN SEÑAL", txt)
        self.assertNotIn("Plan:", txt)


class FrasesNuevas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = _cargar("tgbot_frases", ROOT / "trader-ops" / "run" / "telegram_bot.py")

    def test_ganadores_y_evaluacion(self):
        casos = {
            "analiza los ganadores": "/evaluar",
            "evalua los 5 ganadores": "/evaluar 5",
            "cuales tienen mas probabilidad": "/evaluar",
            "que ganadores hay": "/ganadores",
            "vigila los ganadores": "/seguir",
            "sigue a los 5 ganadores": "/seguir 5",
            "precio de NVDA": "/precios NVDA",
            "incluye MNSO en el escaneo": "/incluir MNSO",
            "mete MNSO en la lista": "/incluir MNSO",
            "precios de NVD.DE": "/precios NVD.DE",
            "compara precios de SLS": "/precios SLS",
            "apunta 139,40 de NVD.DE en borse": "/ref NVD.DE 139.40 borse",
            "referencia de SLS 20,13 tv": "/ref SLS 20.13 tv",
            "analiza NVDA": "/ticker NVDA",
            "evalua NVDA": "/elegir NVDA",
            "analisis completo de TSLA": "/elegir TSLA",
        }
        for frase, esperado in casos.items():
            self.assertEqual(self.bot.interpretar(frase), esperado, frase)

    def test_palabra_comun_no_es_ticker(self):
        self.assertIsNone(self.bot._ticker("NADA"))
        self.assertIsNone(self.bot._ticker("TODO"))
        self.assertEqual(self.bot._ticker("NVDA"), "NVDA")


if __name__ == "__main__":
    unittest.main()
