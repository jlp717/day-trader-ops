"""Telegram por HTTP con la libreria estandar. Sin librerias, sin tokens en logs.

- Long polling de getUpdates.
- Solo atiende al chat_id configurado (cualquier otro se ignora y se registra).
- Limite de ritmo propio: 1 mensaje/s y 20/minuto.
- Modo `dry` (sin token): escribe en logs/telegram_out.jsonl. Asi el ensayo general
  produce mensajes reales sin bot y el sistema no se cae si falta el secreto.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import cfg
from . import diario
from . import zonatiempo as zt

API = "https://api.telegram.org/bot%s/%s"
MAX_LEN = 4096
MIN_GAP = 1.0
MAX_PER_MIN = 20


class TelegramError(Exception):
    pass


class Telegram:
    def __init__(self, token=None, chat_id=None, dry=None):
        secret = cfg.telegram_secret()
        self.token = token or secret.get("bot_token")
        self.chat_id = str(chat_id or secret.get("chat_id") or "") or None
        self.dry = bool(dry) if dry is not None else not bool(self.token and self.chat_id)
        self._sent = []
        self._last = 0.0

    # ---------------------------------------------------------------- estado
    @property
    def enabled(self):
        return not self.dry

    def _limit(self):
        now = time.time()
        self._sent = [t for t in self._sent if now - t < 60]
        if len(self._sent) >= MAX_PER_MIN:
            time.sleep(max(0.0, 60 - (now - self._sent[0]) + 0.1))
        gap = time.time() - self._last
        if gap < MIN_GAP:
            time.sleep(MIN_GAP - gap)
        self._last = time.time()
        self._sent.append(self._last)

    # ---------------------------------------------------------------- HTTP
    def _call(self, method, params, timeout=30):
        if self.dry:
            raise TelegramError("modo dry")
        url = API % (self.token, method)
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                doc = json.loads(resp.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise TelegramError("Telegram no responde: %s" % exc)
        if not doc.get("ok"):
            raise TelegramError("Telegram: %s" % (doc.get("description") or doc))
        return doc.get("result")

    # ---------------------------------------------------------------- envio
    def send(self, text, buttons=None, silent=False, chat_id=None):
        """Envia y devuelve message_id (o None en dry). `buttons` = [[(label, data)]]."""
        chat = str(chat_id or self.chat_id or "")
        text = text if len(text) <= MAX_LEN else text[:MAX_LEN - 30] + "\n...[recortado]"
        payload = {"chat_id": chat, "text": text, "parse_mode": "HTML",
                   "disable_notification": bool(silent),
                   "disable_web_page_preview": True}
        if buttons:
            payload["reply_markup"] = json.dumps(
                {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]},
                ensure_ascii=False)
        if self.dry or not chat:
            self._log("send", text=text, buttons=buttons, chat=chat)
            return None
        self._limit()
        try:
            res = self._call("sendMessage", payload)
        except TelegramError as exc:
            self._log("send_error", text=text, error=str(exc))
            raise
        mid = (res or {}).get("message_id")
        self._log("sent", text=text, message_id=mid, chat=chat)
        return mid

    def edit(self, message_id, text, buttons=None):
        if self.dry or not message_id:
            self._log("edit", text=text, message_id=message_id)
            return None
        payload = {"chat_id": str(self.chat_id), "message_id": message_id, "text": text,
                   "parse_mode": "HTML", "disable_web_page_preview": True}
        if buttons:
            payload["reply_markup"] = json.dumps(
                {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]},
                ensure_ascii=False)
        self._limit()
        return self._call("editMessageText", payload)

    def answer_callback(self, callback_id, text=""):
        if self.dry:
            return None
        try:
            return self._call("answerCallbackQuery",
                              {"callback_query_id": callback_id, "text": text[:200]})
        except TelegramError:
            return None

    # ---------------------------------------------------------------- recepcion
    def get_updates(self, offset=None, timeout=25):
        if self.dry:
            return []
        params = {"timeout": timeout, "allowed_updates": json.dumps(["message", "callback_query"])}
        if offset:
            params["offset"] = offset
        try:
            return self._call("getUpdates", params, timeout=timeout + 15) or []
        except TelegramError as exc:
            diario.append("telegram_error", where="getUpdates", error=str(exc))
            time.sleep(5)
            return []

    def whoami(self):
        if self.dry:
            return None
        return self._call("getMe", {})

    # ---------------------------------------------------------------- log
    def _log(self, kind, **fields):
        row = {"kind": kind, "ts_madrid": zt.iso_madrid()}
        row.update(fields)
        path = cfg.LOGS / "telegram_out.jsonl"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        if kind != "sent":
            diario.append("telegram", **row)
