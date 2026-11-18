"""Operativa manual: alertas de posicion, cierres parciales, limites y frases nuevas."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "trader-ops"))

from lib import alertas, cfg, datos, posiciones, referencias  # noqa: E402
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


class NoticiasPremarket(unittest.TestCase):
    """El aviso debe nombrar el valor del titular, no toda la watchlist."""

    def _doc(self):
        ahora = zt.now_utc().isoformat()
        return {"items": [
            {"ticker": "NVDA", "title": "Nvidia Q3 earnings beat estimates",
             "time": ahora, "source": "Yahoo Finance", "tags": ["earnings"]},
            {"ticker": "MNSO", "title": "MNSO opens a new store in Lima",
             "time": ahora, "source": "Yahoo Finance", "tags": []},
        ]}

    def test_resultados_solo_del_ticker_del_titular(self):
        from lib import proceso
        self.assertEqual(proceso.simbolos_afectados(self._doc(), "earnings"), ["NVDA"])

    def test_adversas_solo_del_ticker_del_titular(self):
        from lib import proceso
        doc = {"items": [
            {"ticker": "MNSO", "title": "MNSO faces a lawsuit over a lease",
             "time": zt.now_utc().isoformat()},
        ]}
        self.assertEqual(proceso.simbolos_afectados(doc, "adverse"), ["MNSO"])

    def test_clasificar_sigue_devolviendo_textos(self):
        from lib import proceso
        adverse, earnings = proceso.clasificar_noticias(self._doc(), "NVDA")
        self.assertEqual(adverse, [])
        self.assertEqual(len(earnings), 1)
        self.assertIn("Nvidia", earnings[0])

    def test_titular_viejo_no_cuenta_como_resultado(self):
        from lib import proceso
        doc = {"items": [
            {"ticker": "NVDA", "title": "Nvidia earnings from last month",
             "time": "2026-10-01T12:00:00+00:00", "tags": []},
        ]}
        self.assertEqual(proceso.simbolos_afectados(doc, "earnings"), [])


class ListaOrb(unittest.TestCase):
    """La lista del ORB debe colocar ganadores primero y respetar el techo de 150."""

    @classmethod
    def setUpClass(cls):
        cls.orch = _cargar("orq_orb_test", ROOT / "trader-ops" / "run" / "orquestador.py")

    def test_ganadores_primero_y_sin_duplicados(self):
        filas = [{"symbol": "AAA"}, {"symbol": "BBB"}]
        hits = [{"symbol": "CCC"}, {"symbol": "AAA"}]
        self.assertEqual(self.orch._simbolos_orb(filas, hits), ["AAA", "BBB", "CCC"])

    def test_techo_de_150(self):
        hits = [{"symbol": "S%03d" % i} for i in range(200)]
        self.assertEqual(len(self.orch._simbolos_orb([], hits)), 150)

    def test_el_modulo_importa_ganadores(self):
        # Regresion: sin este import, el premarket fallaba con NameError y la lista
        # se quedaba sin los ganadores de ayer.
        self.assertTrue(hasattr(self.orch, "ganadores"))


class VentanaOrb(unittest.TestCase):
    """El vigilante no debe quejarse antes de la primera pasada del ORB."""

    @classmethod
    def setUpClass(cls):
        cls.wd = _cargar("wd_orb_test", ROOT / "trader-ops" / "run" / "watchdog.py")

    def _dt(self, h, m):
        import datetime as dt
        return dt.datetime(2026, 11, 18, h, m, tzinfo=zt.MADRID)

    def test_antes_de_las_15_50_no_avisa(self):
        self.assertFalse(self.wd._ventana_orb(self._dt(15, 34), self._dt(15, 30),
                                              self._dt(22, 0), self._dt(21, 30)))

    def test_durante_el_orb_si_avisa(self):
        self.assertTrue(self.wd._ventana_orb(self._dt(16, 10), self._dt(15, 30),
                                             self._dt(22, 0), self._dt(21, 30)))

    def test_despues_del_corte_no_avisa(self):
        self.assertFalse(self.wd._ventana_orb(self._dt(21, 40), self._dt(15, 30),
                                              self._dt(22, 0), self._dt(21, 30)))

    def test_cierre_anticipado_manda_el_cierre(self):
        self.assertFalse(self.wd._ventana_orb(self._dt(18, 30), self._dt(15, 30),
                                              self._dt(18, 0), self._dt(21, 30)))


class FuenteCnbc(unittest.TestCase):
    """Segundo testigo: parseo y umbral de discrepancia."""

    DOC = {"FormattedQuoteResult": {"FormattedQuote": [{
        "last": "154.96", "last_time": "2026-11-18T10:09:24.143-0500", "exchange": "NYSE"}]}}

    def test_parsea_la_respuesta(self):
        from unittest import mock
        with mock.patch.object(datos, "http_json_url", return_value=self.DOC), \
                mock.patch.object(datos, "_cache_get", return_value=None), \
                mock.patch.object(datos, "_cache_put"):
            q = datos.quote_cnbc("NVDA")
        self.assertAlmostEqual(q["price"], 154.96)
        self.assertEqual(q["source"], "CNBC")
        self.assertEqual(q["currency"], "USD")
        self.assertIsNotNone(q["data_time"])

    def test_no_intenta_xetra(self):
        with self.assertRaises(datos.DataError):
            datos.quote_cnbc("NVD.DE")

    def test_cross_check_ok(self):
        from unittest import mock
        with mock.patch.object(datos, "quote_cnbc", return_value={"price": 100.0}), \
                mock.patch.object(datos, "quote_finnhub", side_effect=datos.DataError("sin clave")):
            ok, detalle, alt = datos.cross_check("NVDA", 100.2)
        self.assertTrue(ok)
        self.assertIn("0.20%", detalle)
        self.assertEqual(alt["price"], 100.0)

    def test_cross_check_bloquea_si_difieren(self):
        from unittest import mock
        with mock.patch.object(datos, "quote_cnbc", return_value={"price": 100.0}), \
                mock.patch.object(datos, "quote_finnhub", side_effect=datos.DataError("sin clave")):
            ok, detalle, _ = datos.cross_check("NVDA", 101.0)
        self.assertFalse(ok)
        self.assertIn("1.00%", detalle)

    def test_cross_check_no_bloquea_si_los_testigos_caen(self):
        from unittest import mock
        with mock.patch.object(datos, "quote_cnbc", side_effect=datos.DataError("caido")), \
                mock.patch.object(datos, "quote_finnhub", side_effect=datos.DataError("sin clave")):
            ok, detalle, alt = datos.cross_check("NVDA", 100.0)
        self.assertTrue(ok)
        self.assertIsNone(alt)
        self.assertIn("sin segundo testigo", detalle)

    def test_finnhub_parsea(self):
        from unittest import mock
        doc = {"c": 154.9, "t": 1763480000}
        with mock.patch.object(datos, "_finnhub_key", return_value="clave"), \
                mock.patch.object(datos, "http_json_url", return_value=doc), \
                mock.patch.object(datos, "_cache_get", return_value=None), \
                mock.patch.object(datos, "_cache_put"):
            q = datos.quote_finnhub("NVDA")
        self.assertAlmostEqual(q["price"], 154.9)
        self.assertEqual(q["source"], "Finnhub")
        self.assertIsNotNone(q["data_time"])

    def test_finnhub_sin_clave(self):
        from unittest import mock
        with mock.patch.object(datos, "_finnhub_key", return_value=None):
            with self.assertRaises(datos.DataError):
                datos.quote_finnhub("NVDA")


class Guia(unittest.TestCase):
    """El comando /guia debe decir la accion exacta, no solo el estado."""

    POS = {"id": "p1", "symbol": "CRCL", "qty": 7.0, "entrada": 52.96,
           "stop": 52.4, "target": 55.34}

    def setUp(self):
        from unittest import mock
        self.bot = _cargar("tgbot_guia", ROOT / "trader-ops" / "run" / "telegram_bot.py")
        self.mock = mock
        self._fase = self.bot.ahora.fase
        self._sig = self.bot.ahora.siguiente_evento
        self.bot.ahora.fase = lambda now=None: ("ventana", "Ventana de entrada", "", "", "")
        self.bot.ahora.siguiente_evento = lambda now=None: (None, None)

    def tearDown(self):
        self.bot.ahora.fase = self._fase
        self.bot.ahora.siguiente_evento = self._sig

    def test_sin_posicion(self):
        with self.mock.patch.object(self.bot.posiciones, "abiertas", return_value=[]):
            txt = self.bot.c_guia(None, [])
        self.assertIn("Sin posiciones abiertas", txt)
        self.assertIn("Si llega SEÑAL A", txt)

    def test_con_posicion_da_las_ordenes(self):
        with self.mock.patch.object(self.bot.posiciones, "abiertas", return_value=[self.POS]), \
                self.mock.patch.object(self.bot.datos, "quote",
                                       return_value={"price": 53.9, "age_seconds": 4, "exchange": "NYQ"}), \
                self.mock.patch.object(self.bot.datos, "coste_ida_vuelta_usd",
                                       return_value={"total_usd": 8.81}):
            txt = self.bot.c_guia(None, [])
        self.assertIn("CRCL", txt)
        self.assertIn("Si toca 52.4", txt)
        self.assertIn("limitada 55.34", txt)
        self.assertIn("/sali CRCL", txt)
        self.assertIn("Neto si salta el stop", txt)
        # Telegram parse_mode=HTML: <fill> y & rompen el envio con HTTP 400.
        self.assertNotIn("<fill>", txt)
        self.assertNotIn("&", txt)


if __name__ == "__main__":
    unittest.main()
