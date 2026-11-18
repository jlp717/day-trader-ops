"""Configura los secretos en la terminal, nunca por el chat.

1. Token del bot (getpass: no se ecoa, no queda en el historial). Hasta 3 intentos.
2. chat_id: se detecta esperando tu /start al bot (hasta 10 minutos).
3. User-Agent de la SEC (nombre y email reales).

Guardas en <proyecto>/secrets/*.json con permisos restringidos (icacls en Windows).
La carpeta esta en .gitignore. El token nunca se imprime ni se registra.

Uso:
    python trader-ops/run/configurar_secretos.py               # todo
    python trader-ops/run/configurar_secretos.py --detectar    # solo esperar /start
    python trader-ops/run/configurar_secretos.py --solo-sec
    python trader-ops/run/configurar_secretos.py --estado
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from getpass import getpass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECRETS = os.path.join(ROOT, "secrets")
LOG = os.path.join(SECRETS, "setup.log")
TOKEN_RX = re.compile(r"^\d{8,12}:[A-Za-z0-9_-]{30,}$")
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _log(msg):
    """Diagnostico sin secretos: solo longitudes y estados."""
    try:
        os.makedirs(SECRETS, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), msg))
    except Exception:
        pass


def endurecer(path):
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME") or ""
            subprocess.run(["icacls", path, "/inheritance:r"], capture_output=True, timeout=30)
            r = subprocess.run(["icacls", path, "/grant:r", "%s:F" % user],
                               capture_output=True, timeout=30)
            return r.returncode == 0
        os.chmod(path, 0o600)
        return True
    except Exception:
        return False


def guardar(nombre, doc):
    os.makedirs(SECRETS, exist_ok=True)
    path = os.path.join(SECRETS, nombre)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
    ok = endurecer(path)
    print("Guardado %s%s" % (path, "" if ok else " (AVISO: no se pudieron restringir permisos)"))
    return path


def api(token, method, params=None, timeout=30):
    url = "https://api.telegram.org/bot%s/%s" % (token, method)
    data = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _token_guardado():
    try:
        with open(os.path.join(SECRETS, "telegram.json"), encoding="utf-8") as fh:
            return json.load(fh).get("bot_token")
    except Exception:
        return None


def esperar_chat(token, minutos=10):
    """Espera tu /start y guarda el chat_id. Sin leer nada mas del bot."""
    print("\nAbre Telegram, busca tu bot y enviale /start. Esperando hasta %d minutos..." % minutos)
    print("(Si ya lo enviaste antes, escribe /start otra vez: los updates no leidos se consumen.)")
    deadline = time.time() + minutos * 60
    offset = None
    intentos = 0
    while time.time() < deadline:
        intentos += 1
        try:
            r = api(token, "getUpdates", {"timeout": 20, "offset": offset or "",
                                          "allowed_updates": json.dumps(["message"])}, timeout=40)
        except Exception as exc:
            print("  Telegram no responde (%s). Reintento en 5 s." % str(exc)[:80])
            time.sleep(5)
            continue
        for up in r.get("result") or []:
            offset = up.get("update_id", 0) + 1
            msg = up.get("message") or {}
            chat = msg.get("chat") or {}
            if chat.get("id"):
                cid = str(chat["id"])
                nombre = chat.get("username") or chat.get("first_name") or "?"
                doc = {"bot_token": token, "chat_id": cid, "username": nombre,
                       "configurado": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
                guardar("telegram.json", doc)
                _log("chat detectado: %s" % cid)
                print("chat_id detectado: %s (%s). Solo atendere a ese chat." % (cid, nombre))
                try:
                    api(token, "sendMessage", {"chat_id": cid,
                                               "text": "Configurado. Ya puedo escribirte.\n"
                                                       "Prueba: /estado  /hoy  /ayuda",
                                               "disable_notification": True})
                    print("Mensaje de prueba enviado a Telegram.")
                except Exception as exc:
                    print("No pude enviar el mensaje de prueba: %s" % str(exc)[:120])
                return cid
        if intentos % 3 == 0:
            restante = int((deadline - time.time()) / 60)
            print("  ...seguimos esperando el /start (%d min)" % max(0, restante))
        time.sleep(1)
    print("No llego el /start. El token queda guardado; ejecuta:")
    print("  python trader-ops/run/configurar_secretos.py --detectar")
    _log("timeout esperando chat")
    return None


def _portapapeles():
    """Lee el portapapeles de Windows sin imprimirlo. Plan B si pegar falla."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                             capture_output=True, text=True, timeout=30)
        return (out.stdout or "").strip()
    except Exception:
        return ""


def paso_bot():
    print("\n=== PASO 1: BOT DE TELEGRAM ===")
    print("Si no tienes bot: Telegram -> @BotFather -> /newbot -> nombre y usuario -> copia el token.")
    print("Para pegar en esta ventana: clic derecho con el raton (o Ctrl+V). No se vera al pegar.")
    for intento in (1, 2, 3):
        token = getpass("Token del bot (intento %d/3, Enter para salir): " % intento).strip()
        if not token:
            print("  No has pegado nada.")
            _log("token vacio en intento %d" % intento)
            continue
        if not TOKEN_RX.match(token):
            print("  Eso no tiene forma de token (debe ser 123456789:AAH...). Longitud recibida: %d." % len(token))
            _log("token con formato invalido, longitud %d" % len(token))
            continue
        try:
            me = api(token, "getMe").get("result") or {}
        except Exception as exc:
            print("  Telegram rechaza el token: %s" % str(exc)[:120])
            _log("getMe fallo: %s" % str(exc)[:120])
            continue
        print("  Bot valido: @%s (%s)" % (me.get("username"), me.get("first_name")))
        _log("token valido para @%s" % me.get("username"))
        guardar("telegram.json", {"bot_token": token, "chat_id": None})
        esperar_chat(token)
        return token
    print("Sin token valido. Puedes volver a ejecutar este script cuando quieras.")
    return None


def paso_sec():
    print("\n=== PASO 2: SEC (obligatorio para 8-K y XBRL) ===")
    print("La SEC exige identificarte: nombre y email reales en el User-Agent.")
    nombre = input("Nombre y apellidos: ").strip()
    email = input("Email: ").strip()
    if not nombre or not EMAIL_RX.match(email):
        print("Nombre o email no validos. No se guarda nada.")
        _log("sec invalido")
        return None
    ua = "%s %s" % (nombre, email)
    guardar("sec.json", {"user_agent": ua})
    _log("sec guardado")
    return ua


def estado():
    for name in ("telegram.json", "sec.json"):
        p = os.path.join(SECRETS, name)
        if not os.path.exists(p):
            print("%s: no existe" % name)
            continue
        doc = json.load(open(p, encoding="utf-8"))
        if name == "telegram.json":
            print("telegram.json: token %s, chat_id %s, usuario %s" % (
                "presente" if doc.get("bot_token") else "falta",
                doc.get("chat_id") or "sin detectar", doc.get("username") or "-"))
        else:
            print("sec.json: user_agent %s" % ("presente" if doc.get("user_agent") else "falta"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Configura secretos en local")
    ap.add_argument("--solo-bot", action="store_true")
    ap.add_argument("--solo-sec", action="store_true")
    ap.add_argument("--detectar", action="store_true", help="usar el token guardado y esperar /start")
    ap.add_argument("--portapapeles", action="store_true",
                    help="leer el token del portapapeles (plan B si pegar en la consola falla)")
    ap.add_argument("--solo-guardar", action="store_true",
                    help="leer TG_TOKEN del entorno, validar y guardar sin esperar /start")
    ap.add_argument("--minutos", type=int, default=10)
    ap.add_argument("--estado", action="store_true")
    a = ap.parse_args(argv)

    os.makedirs(SECRETS, exist_ok=True)
    if a.estado:
        estado()
        return 0

    if a.solo_guardar:
        token = (os.environ.get("TG_TOKEN") or "").strip()
        if not TOKEN_RX.match(token):
            print("TOKEN_INVALIDO longitud=%d" % len(token))
            _log("solo-guardar: formato invalido, longitud %d" % len(token))
            return 2
        try:
            me = api(token, "getMe").get("result") or {}
        except Exception as exc:
            print("TOKEN_RECHAZADO %s" % str(exc)[:120])
            _log("solo-guardar: getMe fallo")
            return 3
        guardar("telegram.json", {"bot_token": token, "chat_id": None})
        print("TOKEN_OK @%s" % me.get("username"))
        _log("solo-guardar: token valido para @%s" % me.get("username"))
        return 0

    if a.detectar:
        token = _token_guardado()
        if not token:
            print("No hay token guardado. Ejecuta el script sin argumentos.")
            return 1
        esperar_chat(token, a.minutos)
        estado()
        return 0

    if a.portapapeles:
        token = _portapapeles()
        if not TOKEN_RX.match(token or ""):
            print("El portapapeles no tiene un token valido (longitud %d)." % len(token or ""))
            _log("portapapeles invalido, longitud %d" % len(token or ""))
            return 1
        try:
            me = api(token, "getMe").get("result") or {}
        except Exception as exc:
            print("Telegram rechaza el token: %s" % str(exc)[:120])
            _log("getMe fallo desde portapapeles")
            return 1
        print("Bot valido: @%s" % me.get("username"))
        _log("token valido desde portapapeles para @%s" % me.get("username"))
        guardar("telegram.json", {"bot_token": token, "chat_id": None})
        esperar_chat(token, a.minutos)
        estado()
        return 0

    if not a.solo_sec:
        paso_bot()
    if not a.solo_bot:
        paso_sec()
    print("")
    estado()
    print("\nListo. Si el chat_id sigue sin detectar: python trader-ops/run/configurar_secretos.py --detectar")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelado. No se ha guardado nada a medias.")
        sys.exit(1)
    except EOFError:
        print("\nEntrada cerrada. Vuelve a ejecutar el script.")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        _log("error: %s" % exc)
        print("\nERROR: %s" % exc)
        print("Nada se ha guardado. Copia este mensaje y pasalo a OpenCode.")
        sys.exit(1)
