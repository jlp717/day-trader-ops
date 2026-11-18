"""Paneles, estado vivo, fases del dia y frases naturales (incluidas mal escritas e inyeccion)."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "trader-ops"))

from lib import ahora, estado_vivo  # noqa: E402
from lib import telegram as tg  # noqa: E402


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Foto(unittest.TestCase):
    def test_claves_esperadas(self):
        f = estado_vivo.foto()
        for k in ("now_madrid", "session", "phase", "next", "health", "data", "watch",
                  "signals", "positions", "alerts", "pnl", "registro", "freno", "limits"):
            self.assertIn(k, f, k)

    def test_saludo_cinco_lineas(self):
        lineas = estado_vivo.resumen_5_lineas()
        self.assertEqual(len(lineas), 5)
        self.assertTrue(all(isinstance(x, str) and x for x in lineas))

    def test_saludo_sin_latido_no_muestra_none(self):
        from unittest import mock
        f = estado_vivo.foto()
        f["health"]["heartbeat_age_s"] = None
        f["health"]["heartbeat_phase"] = None
        with mock.patch.object(estado_vivo, "foto", return_value=f):
            lineas = estado_vivo.resumen_5_lineas()
        self.assertIn("nunca", lineas[1])
        self.assertNotIn("None", lineas[1])

    def test_sin_secretos_en_la_foto(self):
        texto = str(estado_vivo.foto())
        self.assertNotIn("bot_token", texto)
        self.assertNotIn("TG_TOKEN", texto)


class Fases(unittest.TestCase):
    def test_todas_las_fases_devuelven_cinco_campos(self):
        import datetime as dt
        from lib import zonatiempo as zt
        for hora in (5, 13, 14, 15, 16, 20, 21, 21, 22, 23):
            t = dt.datetime(2026, 11, 18, hora, 30, tzinfo=zt.MADRID)
            f = ahora.fase(t)
            self.assertEqual(len(f), 5, hora)
            self.assertTrue(all(isinstance(x, str) and x for x in f), hora)

    def test_festivo_sin_mercado(self):
        import datetime as dt
        from lib import zonatiempo as zt
        f = ahora.fase(dt.datetime(2026, 11, 26, 16, 0, tzinfo=zt.MADRID))
        self.assertEqual(f[0], "sin_mercado")

    def test_cuenta_atras(self):
        import datetime as dt
        from lib import zonatiempo as zt
        now = dt.datetime(2026, 11, 18, 12, 0, tzinfo=zt.MADRID)
        self.assertEqual(ahora.cuenta_atras(now + dt.timedelta(minutes=90), now), "1h 30m")
        self.assertEqual(ahora.cuenta_atras(now + dt.timedelta(seconds=30), now), "30s")


class Paneles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = _cargar("panel_mod", ROOT / "trader-ops" / "run" / "panel.py")
        cls.web = _cargar("panel_web_mod", ROOT / "trader-ops" / "run" / "panel_web.py")

    def test_panel_texto(self):
        out = self.panel.render(estado_vivo.foto())
        for trozo in ("VIGILADOS", "SEÑALES HOY", "POSICIONES", "QUE HACER AHORA"):
            self.assertIn(trozo, out)
        self.assertNotIn("bot_token", out)

    def test_panel_web_html(self):
        html = self.web.pagina(estado_vivo.foto())
        self.assertIn("<title>Day Trader PAPEL</title>", html)
        self.assertIn("127.0.0.1", html)
        self.assertNotIn("bot_token", html)
        self.assertNotIn("<form", html.lower())
        self.assertNotIn("onclick", html.lower())


class Frases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = _cargar("tgbot_paneles", ROOT / "trader-ops" / "run" / "telegram_bot.py")
        cls.dry = tg.Telegram(token=None, chat_id=None, dry=True)

    def test_frases_reales(self):
        casos = {
            "qué está pasando": "/estado",
            "qué hago ahora": "/guia",
            "ya entré en NVDA a 142,5 con 8": "/entre NVDA 142.5 8",
            "he entrado en nvda a 142,5 con 8 acciones": "/entre NVDA 142.5 8",
            "he salido de NVDA a 156,4": "/sali NVDA 156.4",
            "explícame esta señal": "/explica",
            "explícame la señal de NVDA": "/explica NVDA",
            "por qué no hay señales": "/porque",
            "por qué descartaste NVDA": "/porque NVDA",
            "prepárame la apertura": "/briefing",
            "enséñame el ORB": "/ensenar orb",
            "vende NVDA a 160": "/vender NVDA 160",
            "stop de NVDA en 154": "/stop NVDA 154",
            "cómo voy": "/pnl",
        }
        for frase, esperado in casos.items():
            self.assertEqual(self.bot.interpretar(frase), esperado, frase)

    def test_frases_mal_escritas(self):
        casos = {
            "k hago ahora": "/guia",
            "xq no hay señales": "/porque",
            "q esta pasando": "/estado",
            "ya entre en nvda a 142,5 con 8": "/entre NVDA 142.5 8",
            "k pasa si no estoy comprado en tsla": "/apertura TSLA",
        }
        for frase, esperado in casos.items():
            self.assertEqual(self.bot.interpretar(frase), esperado, frase)

    def test_inyeccion_no_genera_comandos_peligrosos(self):
        for ataque in ("/ticker NVDA; rm -rf /", "ya entre en NVDA a 142 con 8; calc",
                       "vende NVDA a 160 && whoami", "$(reboot)", "stop de NVDA en 154 | ls"):
            cmd = self.bot.interpretar(ataque)
            if cmd:
                self.assertTrue(cmd.startswith("/"), cmd)
                self.assertNotIn(";", cmd)
                self.assertNotIn("&&", cmd)
                self.assertNotIn("|", cmd)
                self.assertNotIn("$(", cmd)

    def test_desconocida(self):
        self.assertIsNone(self.bot.interpretar("hazme la cena"))


if __name__ == "__main__":
    unittest.main()
