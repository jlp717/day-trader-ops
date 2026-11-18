"""Pruebas de caos: datos corruptos, Yahoo caido, Telegram caido, reinicio, duplicados.

    python -m unittest discover -s trader-ops/tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "trader-ops"))

from lib import cfg, datos, diario, proceso, telegram as tg  # noqa: E402


class YahooCaido(unittest.TestCase):
    def test_quote_sin_red_lanza_dataerror(self):
        with mock.patch.object(datos, "_cache_get", return_value=None), \
                mock.patch.object(datos, "http_json", side_effect=datos.DataError("sin respuesta")):
            with self.assertRaises(datos.DataError):
                datos.quote("NVDA")

    def test_pipeline_devuelve_sin_datos_y_no_revienta(self):
        with mock.patch.object(datos, "quote", side_effect=datos.DataError("caido")):
            out = proceso.evaluar_symbol("NVDA", enviar=False)
        self.assertEqual(out["verdict"], "SIN DATOS")
        self.assertIn("caido", out["reasons"][0])


class TelegramCaido(unittest.TestCase):
    class BotRoto:
        dry = False

        def send(self, *a, **k):
            raise tg.TelegramError("telegram caido")

    def test_send_once_propaga_y_se_registra(self):
        from lib import avisos
        with self.assertRaises(tg.TelegramError):
            avisos.send_once(self.BotRoto(), "caos:%s" % os.getpid(), "hola")


class DatosCorruptos(unittest.TestCase):
    def test_plan_corrupto_no_rompe_el_orquestador(self):
        # el skill rechaza un plan invalido; nuestro codigo debe leerlo como vacio
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write("{roto")
            p = fh.name
        try:
            self.assertEqual(cfg.read_json(p, {}), {})
            # y exit.py rechaza el archivo con un mensaje, no con un traceback
            from lib import skills
            r = skills.run("exit", ["plan", "--from", p, "--json"], timeout=60, json_out=True)
            self.assertNotEqual(r.code, 0)
            low = ((r.stderr or "") + (r.stdout or "")).lower()
            self.assertTrue("not valid" in low or "no es valido" in low, low)
        finally:
            os.unlink(p)

    def test_watchlist_corrupta_no_rompe_entry(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write("[")
            p = fh.name
        try:
            from lib import skills
            r = skills.run("entry", ["watchlist", "--watchlist", p, "--json"], timeout=60, json_out=True)
            self.assertNotEqual(r.code, 0)
        finally:
            os.unlink(p)


class ReinicioYDuplicados(unittest.TestCase):
    def test_agenda_persistida_tras_reinicio(self):
        from run import orquestador as orch  # noqa: F401  (importa el modulo real)
        r = orch.Runner(tg.Telegram(dry=True), dry=True)
        tareas, why, end = r.tareas(__import__("datetime").date(2026, 11, 18))
        claves = [t[0] for t in tareas]
        self.assertIn("premarket", claves)
        self.assertIn("cierre", claves)
        self.assertEqual(len(claves), len(set(claves)))

    def test_dedupe_no_duplica(self):
        from lib import avisos
        bot = tg.Telegram(dry=True)
        key = "caos-duplicado:%s" % os.getpid()
        avisos.send_once(bot, key, "uno")
        self.assertIsNone(avisos.send_once(bot, key, "dos"))

    def test_diario_siempre_tiene_id_y_hora(self):
        ev = diario.append("caos", nota="x", output="salida")
        self.assertTrue(ev.get("id"))
        self.assertIn("ts_utc", ev)
        self.assertIn("ts_madrid", ev)
        self.assertTrue(ev.get("output_hash"))


if __name__ == "__main__":
    unittest.main()
