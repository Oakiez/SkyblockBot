# -*- coding: utf-8 -*-
"""
remote.py — สั่งบอทจาก Discord บนมือถือ

หลักการ: ทุก ~3 วินาทีอ่านข้อความใหม่ของ bot ผ่าน Discord REST API (ไม่ต้องใช้ websocket/ไลบรารีเพิ่ม)
  • รับคำสั่งเฉพาะข้อความที่ผู้ส่งอยู่ใน DISCORD_ALLOWED_USER_IDS เท่านั้น — คนอื่น/ bot อื่น/ webhook ถูกเมินหมด
  • มีแค่คำสั่งสำเร็จรูป (stop / pause / resume / status / screenshot / help) ไม่มีคำสั่งแบบรันข้อความอะไรก็ได้
  • ข้อความเก่าเกิน REMOTE_MAX_AGE_SECONDS และข้อความก่อนเริ่มสคริปต์ถูกข้าม (ไม่ย้อนรันคำสั่งเก่า)

ช่องทางสั่ง: DM หา bot (ค่าเริ่มต้น) หรือช่องเซิร์ฟเวอร์ที่ตั้งใน DISCORD_COMMAND_CHANNEL_ID (ต้อง @mention bot
เพราะ bot ที่ไม่ได้เปิด Message Content Intent จะเห็นเนื้อหาข้อความเฉพาะ DM และข้อความที่ mention มัน)
"""

import re
import threading
import time

from botkit import discord_io as dio
from botkit import settings

DISCORD_EPOCH_MS = 1420070400000

# ชื่อคำสั่ง → ชื่อมาตรฐาน
ALIASES = {
    "stop": "stop", "halt": "stop", "off": "stop",
    "pause": "pause", "hold": "pause",
    "resume": "resume", "continue": "resume", "go": "resume",
    "status": "status", "st": "status", "info": "status",
    "screenshot": "screenshot", "shot": "screenshot", "ss": "screenshot",
    "help": "help", "?": "help",
}

HELP_TEXT = (
    "`stop` หยุดบอท  •  `pause` พัก  •  `resume` ต่อ\n"
    "`status` ดูสถานะ+ภาพหน้าจอ  •  `screenshot` ขอภาพหน้าจอ\n"
    "ในช่องเซิร์ฟเวอร์ต้อง @mention bot ก่อน เช่น `@Bot stop`"
)


# ---------- ตัวช่วยแบบ pure (ทดสอบออฟไลน์ได้) ----------

def _why(body) -> str:
    """ข้อความอธิบาย error จาก Discord (เช่น ': Unknown Channel') ถ้ามี"""
    if isinstance(body, dict) and body.get("message"):
        return f": {str(body['message'])[:80]}"
    return ""


def snowflake_time(snowflake) -> float:
    return ((int(snowflake) >> 22) + DISCORD_EPOCH_MS) / 1000.0


def parse_command(content: str, bot_id: str = "") -> str:
    """ข้อความ → ชื่อคำสั่งมาตรฐาน ("" = ไม่ใช่คำสั่งที่รู้จัก, None = ข้อความว่าง) ตัด @mention ของ bot และ ! / ออกให้"""
    text = re.sub(r"<@!?\d+>", " ", content or "").strip().lower()
    if not text:
        return None
    word = text.split()[0].lstrip("!/.")
    return ALIASES.get(word, "")


def is_authorized(message: dict, allowed: tuple) -> bool:
    author = message.get("author") or {}
    if author.get("bot") or message.get("webhook_id"):
        return False
    return str(author.get("id", "")) in allowed


class RemoteControl:
    """handle(command) -> dict(title, description, level, fields, screenshot) | None  (None = คำสั่งไม่รู้จัก → ตอบ help)"""

    def __init__(self, handle, name: str = "bot"):
        self.handle = handle
        self.name = name
        self._stop = threading.Event()
        self._thread = None
        self._channel = ""
        self._last = None
        self._fail_logged = False

    # ---------- ควบคุมการทำงาน ----------
    def configured(self) -> bool:
        return bool(settings.REMOTE_ENABLED and settings.DISCORD_BOT_TOKEN and settings.DISCORD_ALLOWED_USER_IDS)

    def start(self) -> bool:
        if not self.configured() or self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    # ---------- ภายใน ----------
    def _setup(self) -> bool:
        status, me = dio.bot_request("GET", "/users/@me")
        if status != 200 or not me:
            dio.log(f"[Remote] bot login failed (HTTP {status}) — ตรวจ DISCORD_BOT_TOKEN")
            return False
        self._bot_id = str(me.get("id", ""))
        self._channel = settings.DISCORD_COMMAND_CHANNEL_ID
        if self._channel and not (self._channel.isdigit() and 15 <= len(self._channel) <= 21):
            dio.log(f"[Remote] DISCORD_COMMAND_CHANNEL_ID ไม่ใช่ ID ช่องที่ถูกต้อง (ต้องเป็นตัวเลข 17-20 หลัก แต่ได้ {len(self._channel)} ตัวอักษร) "
                    "— ข้ามค่านี้แล้วใช้โหมด DM แทน (ถ้าไม่ได้ใช้ช่องเซิร์ฟเวอร์ ให้ลบค่านี้ออกจาก secrets_local.py)")
            self._channel = ""
        if not self._channel:   # ไม่ระบุช่อง → DM กับ user คนแรกที่อนุญาต
            status, dm = dio.bot_request("POST", "/users/@me/channels", {"recipient_id": settings.DISCORD_ALLOWED_USER_IDS[0]})
            if status not in (200, 201) or not dm:
                dio.log(f"[Remote] เปิด DM ไม่สำเร็จ (HTTP {status}{_why(dm)}) — เปิดรับ DM จากสมาชิกเซิร์ฟเวอร์ และอยู่เซิร์ฟเวอร์เดียวกับ bot หรือตั้ง DISCORD_COMMAND_CHANNEL_ID")
                return False
            self._channel = str(dm["id"])
        # ข้ามข้อความทั้งหมดที่มีอยู่แล้ว: จะรับเฉพาะคำสั่งที่พิมพ์หลังเริ่มสคริปต์
        status, msgs = dio.bot_request("GET", f"/channels/{self._channel}/messages?limit=1")
        if status != 200:
            dio.log(f"[Remote] อ่านช่องคำสั่งไม่ได้ (HTTP {status}{_why(msgs)}) — ตรวจ ID ช่อง และสิทธิ์ View Channel / Read Message History")
            return False
        self._last = str(msgs[0]["id"]) if msgs else "0"
        return True

    def _reply(self, result: dict) -> None:
        image = dio.take_screenshot() if result.get("screenshot") and settings.DISCORD_SCREENSHOT else None
        payload = dio.build_embed_payload(
            result.get("title", self.name), result.get("description", ""), result.get("level", "info"),
            result.get("fields"), footer=self.name, image_name=image[0] if image else None)
        dio.bot_send(self._channel, payload, image)

    def process(self, messages: list) -> None:
        """messages = ข้อความใหม่ (ลำดับใดก็ได้) เรียงเก่า→ใหม่แล้วรันทีละข้อความ"""
        for msg in sorted(messages, key=lambda m: int(m["id"])):
            self._last = str(max(int(self._last or 0), int(msg["id"])))
            if not is_authorized(msg, settings.DISCORD_ALLOWED_USER_IDS):
                continue
            if time.time() - snowflake_time(msg["id"]) > settings.REMOTE_MAX_AGE_SECONDS:
                continue
            cmd = parse_command(msg.get("content", ""), self._bot_id)
            if cmd is None:
                continue
            if cmd in ("", "help"):
                self._reply({"title": "คำสั่งที่ใช้ได้", "description": HELP_TEXT})
                continue
            try:
                result = self.handle(cmd)
            except Exception as e:
                result = {"title": f"{cmd}: error", "description": str(e), "level": "error"}
            self._reply(result or {"title": cmd, "description": "ไม่รองรับคำสั่งนี้ในสคริปต์ปัจจุบัน", "level": "warn"})

    def _poll_once(self) -> float:
        """อ่านข้อความใหม่หนึ่งรอบ คืนจำนวนวินาทีที่ควรรอก่อนรอบถัดไป"""
        status, data = dio.bot_request("GET", f"/channels/{self._channel}/messages?limit=20&after={self._last}")
        if status == 429:
            return float((data or {}).get("retry_after", 5)) + 0.5
        if status in (401, 403, 404):
            dio.log(f"[Remote] ถูกปฏิเสธ (HTTP {status}) — หยุดรับคำสั่งจาก Discord")
            self._stop.set()
            return 0.0
        if status != 200 or not isinstance(data, list):
            return settings.REMOTE_POLL_SECONDS * 3   # เน็ต/Discord มีปัญหา ถอยรอบยาวขึ้น
        if data:
            self.process(data)
        return settings.REMOTE_POLL_SECONDS

    def _loop(self) -> None:
        try:
            if not self._setup():
                return
            while not self._stop.is_set():
                self._stop.wait(self._poll_once())
        except Exception as e:
            dio.log(f"[Remote] หยุดทำงาน: {e}")
