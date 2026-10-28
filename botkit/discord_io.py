# -*- coding: utf-8 -*-
"""
discord_io.py — ส่งข้อความเข้า Discord

  • webhook  = แจ้งเตือน (ขาออกอย่างเดียว)         → alert(), webhook_send()
  • bot API  = ตอบคำสั่ง/อ่านข้อความสั่งการ          → bot_request(), bot_send()

ทุกการส่งผ่าน alert() อยู่ใน thread แยก: เน็ตช้า/Discord ล่มต้องไม่หน่วงการหยุดบอท
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid

from botkit import settings

_TIMEOUT = 10
_SCREENSHOT_WAIT = 3.0   # เกมเขียนไฟล์ screenshot แบบ async รอไม่เกินนี้
# Discord (Cloudflare) ปฏิเสธ User-Agent เริ่มต้นของ urllib ด้วย 403 จึงต้องตั้งเอง
_UA = "DiscordBot (minescript-botkit, 1.0)"
_API = "https://discord.com/api/v10"

COLORS = {"info": 0x3498DB, "ok": 0x2ECC71, "warn": 0xF1C40F, "error": 0xE74C3C}

_last_sent: dict = {}
_shot_lock = threading.Lock()   # ถ่าย→อ่าน→ลบของเก่า ทีละครั้ง กัน thread หนึ่งลบไฟล์ที่อีก thread กำลังอ่าน
_BOT_SHOT_RE = re.compile(r"^(botkit|failsafe)_\d{8}_\d{6}\.png$")   # เฉพาะชื่อที่บอทตั้งเอง
_last_sent_lock = threading.Lock()


def log(msg: str) -> None:
    """พิมพ์ลงแชทเกม (ถ้าอยู่ในเกม) ไม่งั้นลง stdout — ใช้รายงานปัญหาของตัวส่ง Discord เอง"""
    try:
        from system.lib import minescript as ms
        ms.echo(msg)
    except Exception:
        print(msg)


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"


# ------------------------------------------------------------
# payload / multipart
# ------------------------------------------------------------

def build_embed_payload(title: str, description: str = "", level: str = "info", fields: list = None,
                        footer: str = "", image_name: str = None, mention: bool = False) -> dict:
    """payload ของ webhook/bot (pure function ทดสอบออฟไลน์ได้) fields = [(ชื่อ, ค่า), ...]"""
    embed = {
        "title": title[:250],
        "description": (description or "")[:3500],
        "color": COLORS.get(level, COLORS["info"]),
        "fields": [{"name": str(n)[:250], "value": (str(v) or "-")[:1000], "inline": True} for n, v in (fields or [])][:20],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if footer:
        embed["footer"] = {"text": footer[:200]}
    if image_name:
        embed["image"] = {"url": f"attachment://{image_name}"}
    payload = {"username": "Farm Bot", "embeds": [embed]}
    if mention and settings.DISCORD_MENTION:
        payload["content"] = settings.DISCORD_MENTION
        payload["allowed_mentions"] = {"parse": ["users", "roles", "everyone"]}
    return payload


def _multipart(payload: dict, filename: str, data: bytes):
    boundary = uuid.uuid4().hex
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
        f"Content-Type: application/json\r\n\r\n".encode() + json.dumps(payload).encode() + b"\r\n",
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{filename}\"\r\n"
        f"Content-Type: image/png\r\n\r\n".encode() + data + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _request(url: str, method: str, payload=None, image=None, headers=None):
    """คืน (status, json|None) สถานะ 0 = ต่อไม่ได้"""
    headers = {"User-Agent": _UA, **(headers or {})}
    body = None
    if payload is not None:
        if image:
            body, headers["Content-Type"] = _multipart(payload, image[0], image[1])
        else:
            body, headers["Content-Type"] = json.dumps(payload).encode(), "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read() if hasattr(resp, "read") else b""
            try:
                return resp.status, (json.loads(raw) if raw else None)
            except ValueError:
                return resp.status, None
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None
    except Exception as e:
        log(f"[Discord] request failed: {e}")
        return 0, None


# ------------------------------------------------------------
# webhook (แจ้งเตือน)
# ------------------------------------------------------------

def webhook_send(payload: dict, image: tuple = None) -> bool:
    if not settings.DISCORD_WEBHOOK_URL:
        return False
    status, _ = _request(settings.DISCORD_WEBHOOK_URL, "POST", payload, image)
    if status and not 200 <= status < 300:
        log(f"[Discord] webhook rejected: HTTP {status}")
    return 200 <= status < 300


def cleanup_old_screenshots(keep_name: str = "") -> int:
    """ลบภาพเก่าที่บอทถ่ายไว้ใน screenshots/ (ยกเว้น keep_name) คืนจำนวนที่ลบ
    ลบเฉพาะไฟล์ที่ชื่อตรงรูปแบบของบอทเป๊ะ ๆ (botkit_YYYYMMDD_HHMMSS.png / failsafe_...) ไฟล์อื่นไม่แตะเลย"""
    folder = os.path.join(os.getcwd(), "screenshots")
    removed = 0
    try:
        for entry in os.listdir(folder):
            if entry != keep_name and _BOT_SHOT_RE.match(entry):
                try:
                    os.remove(os.path.join(folder, entry))
                    removed += 1
                except OSError:
                    pass   # กำลังถูกใช้อยู่/ลบไม่ได้ ข้ามไป รอบหน้าค่อยลบ
    except OSError:
        pass
    return removed


def take_screenshot() -> tuple:
    """ถ่ายภาพหน้าจอเกม คืน (filename, bytes) หรือ None
    ถ้า SCREENSHOT_KEEP_LATEST_ONLY: ถ่ายสำเร็จแล้วลบภาพเก่าของบอท เหลือแค่ภาพล่าสุด"""
    with _shot_lock:
        name = f"botkit_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(os.getcwd(), "screenshots", name)
        try:
            from system.lib import minescript as ms
            ms.screenshot(name)
        except Exception:
            return None
        deadline = time.time() + _SCREENSHOT_WAIT
        last_size = -1
        while time.time() < deadline:
            try:
                size = os.path.getsize(path)
                if size > 0 and size == last_size:   # ขนาดไม่เปลี่ยนแล้ว = เขียนเสร็จ
                    with open(path, "rb") as f:
                        data = f.read()
                    if settings.SCREENSHOT_KEEP_LATEST_ONLY:
                        cleanup_old_screenshots(keep_name=name)
                    return name, data
                last_size = size
            except OSError:
                pass
            time.sleep(0.2)
        return None


def _alert_worker(title, description, level, fields, screenshot, mention, footer):
    image = take_screenshot() if (screenshot and settings.DISCORD_SCREENSHOT) else None
    payload = build_embed_payload(title, description, level, fields, footer,
                                  image[0] if image else None, mention)
    webhook_send(payload, image)


def alert(title: str, description: str = "", level: str = "info", fields: list = None,
          screenshot: bool = False, mention: bool = None, footer: str = "", wait: bool = False) -> bool:
    """แจ้งเตือนทาง webhook แบบไม่บล็อก คืน True ถ้าสั่งส่งแล้ว (False = ปิดอยู่/ยังไม่ตั้ง webhook/ซ้ำถี่)
    mention=None → แท็กเฉพาะ level "error"   wait=True → รอส่งเสร็จก่อนคืน (ใช้ตอน crash/จบสคริปต์ กันโปรเซสปิดก่อนส่ง)"""
    if not settings.DISCORD_NOTIFY or not settings.DISCORD_WEBHOOK_URL:
        return False
    now = time.time()
    with _last_sent_lock:
        if now - _last_sent.get(title, 0.0) < settings.ALERT_MIN_INTERVAL:
            return False
        _last_sent[title] = now
    if mention is None:
        mention = level == "error"
    worker = threading.Thread(
        target=_alert_worker, args=(title, description, level, fields, screenshot, mention, footer), daemon=True
    )
    worker.start()
    if wait:
        worker.join(20)
    return True


# ------------------------------------------------------------
# bot API (สั่งการ)
# ------------------------------------------------------------

def bot_request(method: str, path: str, payload=None, image=None):
    return _request(_API + path, method, payload, image,
                    headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"})


def bot_send(channel_id: str, payload: dict, image: tuple = None) -> bool:
    payload = {k: v for k, v in payload.items() if k != "username"}   # bot ใช้ชื่อของตัวเอง
    status, _ = bot_request("POST", f"/channels/{channel_id}/messages", payload, image)
    return 200 <= status < 300
