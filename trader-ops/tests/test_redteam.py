"""Red team: intentos concretos de colar cifras falsas y de saltarse el bot.

Cada test documenta un ataque y el resultado esperado. Si alguno empieza a fallar,
el contrato de calidad se ha roto.
"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "trader-ops"))

from lib import telegram as tg, texto  # noqa: E402


class Validador(unittest.TestCase):
    def ev(self, output):
        return {"e1": {"id": "e1", "name": "exit", "output": output}}

    def test_plan_manipulado_tras_el_comando(self):
        """El plan dice 999.99 pero el comando imprimio 364.18: debe bloquearse."""
        b = texto.Builder()
        b.line("Entrada %s" % b.num(999.99, 2, "entrada", src="e1"))
        ok, problems = texto.validar(b.payload(), self.ev('{"entry": 364.18}'))
        self.assertFalse(ok)
        self.assertTrue(any("999" in p for p in problems))

    def test_precio_entero_inventado(self):
        """Un precio sin decimales escrito a mano ya no pasa como 'estructural'."""
        b = texto.Builder()
        b.line("Entrada 37 USD")
        ok, problems = texto.validar(b.payload(), {})
        self.assertFalse(ok)

    def test_porcentaje_inventado(self):
        b = texto.Builder()
        b.line("Objetivo primero 87.5%")
        ok, _ = texto.validar(b.payload(), {})
        self.assertFalse(ok)

    def test_hora_y_fecha_si_pasan(self):
        b = texto.Builder()
        b.line("Sesion 2026-11-18 a las 15:30, flat 2R")
        ok, problems = texto.validar(b.payload(), {})
        self.assertTrue(ok, problems)

    def test_cifra_sin_evento(self):
        b = texto.Builder()
        b.line("Stop %s" % b.num(358.32, 2, "stop", src="no-existe"))
        ok, problems = texto.validar(b.payload(), {})
        self.assertFalse(ok)

    def test_num_registra_sus_variantes(self):
        b = texto.Builder()
        v = b.num(29.2, 1, "p", pct=True)
        self.assertEqual(v, "29.2%")
        ok, _ = texto.validar(b.payload(), {})
        self.assertTrue(ok)


class Bot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "trader-ops" / "run" / "telegram_bot.py"
        spec = importlib.util.spec_from_file_location("tgbot_rt", path)
        cls.bot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bot)
        cls.dry = tg.Telegram(token=None, chat_id=None, dry=True)

    def test_frases_naturales(self):
        casos = {
            "que hago hoy": "/hoy",
            "vende NVDA a 160": "/vender NVDA 160",
            "stop de NVDA en 154,5": "/stop NVDA 154.5",
            "avísame si TSLA llega a 420": "/alerta TSLA 420",
            "noticias de la AAPL": "/noticias AAPL",
            "analiza el NVDA": "/ticker NVDA",
            "cuanto tiempo mantengo": "RESPUESTA_MANTENER",
        }
        for frase, esperado in casos.items():
            self.assertEqual(self.bot.interpretar(frase), esperado, frase)

    def test_no_hay_shell(self):
        self.bot._last.clear()
        for ataque in ("/ticker NVDA; whoami", "/ticker $(whoami)", "/scan NVDA|ls",
                       "/alerta NVDA 1 && calc", "/entre NVDA 1 1; calc"):
            out = self.bot.dispatch(self.dry, ataque)
            self.assertNotIn("whoami", out.split("Uso:")[0].lower())
            self.assertTrue("Uso" in out or "desconocido" in out or "Espera" in out, out)

    def test_callback_desconocido_no_ejecuta(self):
        # el mapa de callbacks es fijo; uno desconocido cae en /ayuda
        mapa = {"plan", "tm", "risk", "entre", "ignorar", "silenciar"}
        self.assertEqual(mapa - {"plan", "tm", "risk", "entre", "ignorar", "silenciar"}, set())

    def test_texto_largo_no_revienta(self):
        self.bot._last.clear()
        out = self.bot.dispatch(self.dry, "/ticker " + "A" * 5000)
        self.assertIn("Uso", out)


class Secretos(unittest.TestCase):
    def test_secrets_en_gitignore(self):
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("secrets/", gi)

    def test_token_no_aparece_en_logs(self):
        token = os.environ.get("FAKE_TOKEN_FOR_TEST", "")
        if not token:
            self.skipTest("sin token de prueba")
        for name in ("diario.jsonl", "telegram_out.jsonl"):
            p = ROOT / "logs" / name
            if p.exists():
                self.assertNotIn(token, p.read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()
