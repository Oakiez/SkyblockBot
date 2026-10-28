# -*- coding: utf-8 -*-
"""
settings.py — ค่าตั้งต้นของ botkit (แก้ที่นี่ที่เดียว)

ค่าลับ (webhook / bot token / user id) อยู่ใน farm/secrets_local.py ไม่ใช่ไฟล์นี้:

    DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."   # แจ้งเตือน (มีอยู่แล้ว)
    DISCORD_BOT_TOKEN = ""                # สั่งการจากมือถือ: token ของ Discord bot (ดูวิธีสร้างท้ายไฟล์นี้)
    DISCORD_ALLOWED_USER_IDS = []         # user ID ของคุณ (ตัวเลข) ใส่หลายคนได้ — คนอื่นสั่งอะไรไม่ได้เลย
    DISCORD_COMMAND_CHANNEL_ID = ""       # ว่าง = สั่งผ่าน DM กับ bot, ใส่ = สั่งในช่องนั้น (ต้อง @mention bot)

วิธีสร้าง bot (ทำครั้งเดียว):
  1) discord.com/developers/applications → New Application → แท็บ Bot → Reset Token → คัดลอก
  2) OAuth2 → URL Generator → scope `bot` + สิทธิ์ View Channels / Send Messages / Attach Files /
     Read Message History → เปิดลิงก์ที่ได้เพื่อเชิญ bot เข้าเซิร์ฟเวอร์ที่คุณอยู่
  3) เปิดโหมดนักพัฒนาใน Discord → คลิกขวาที่ชื่อตัวเอง → Copy User ID
  4) ใส่ token กับ user ID ใน farm/secrets_local.py  (token = รหัสผ่านของ bot ห้ามแชร์/ห้าม commit)
  5) ส่ง DM ให้ bot ว่า `help`  (ต้องเปิดรับ DM จากสมาชิกเซิร์ฟเวอร์ และอยู่เซิร์ฟเวอร์เดียวกับ bot)
"""

import importlib.util
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_secrets() -> dict:
    """โหลด farm/secrets_local.py ด้วย path ตรง ๆ (ไม่ import แพ็กเกจ farm: มันหนักและดึง module อื่นตามมา)"""
    path = os.path.join(_HERE, "..", "farm", "secrets_local.py")
    try:
        spec = importlib.util.spec_from_file_location("_botkit_secrets", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return {k: getattr(mod, k) for k in dir(mod) if k.isupper()}
    except Exception:
        return {}


_secrets = _load_secrets()

DISCORD_WEBHOOK_URL = str(_secrets.get("DISCORD_WEBHOOK_URL", "") or "")
DISCORD_BOT_TOKEN = str(_secrets.get("DISCORD_BOT_TOKEN", "") or "")
DISCORD_ALLOWED_USER_IDS = tuple(str(x).strip() for x in (_secrets.get("DISCORD_ALLOWED_USER_IDS", ()) or ()) if str(x).strip())
DISCORD_COMMAND_CHANNEL_ID = str(_secrets.get("DISCORD_COMMAND_CHANNEL_ID", "") or "").strip()

# ============================================================
# แจ้งเตือน
# ============================================================
DISCORD_NOTIFY = True              # เปิด/ปิดการแจ้งเตือนทั้งหมด
DISCORD_SCREENSHOT = True          # แนบภาพหน้าจอกับเหตุการณ์สำคัญ (failsafe, หลุด, crash, ตอบ status)
DISCORD_MENTION = ""               # เช่น "<@123456789012345678>" ให้ Discord เด้งเตือน เฉพาะเหตุการณ์ระดับ error
ALERT_MIN_INTERVAL = 3.0           # หัวข้อเดียวกันซ้ำภายในกี่วินาที ไม่ส่งซ้ำ (กันสแปม)

SCREENSHOT_KEEP_LATEST_ONLY = True # ถ่ายภาพใหม่แล้วลบภาพเก่าของบอทใน screenshots/ (เฉพาะไฟล์ชื่อ botkit_*.png / failsafe_*.png เท่านั้น
                                   # ภาพที่คุณแคปเอง (F2) ไม่ถูกแตะ) False = เก็บทุกภาพ (ใช้พื้นที่ ~1.4 MB ต่อภาพ)

HEARTBEAT_MINUTES = 30             # ส่งสรุปสถานะเป็นระยะทุกกี่นาที (0 = ปิด) ถ้าเงียบนานผิดปกติ = บอทค้าง/เกมเด้ง
HEARTBEAT_SCREENSHOT = True

# ============================================================
# สั่งการจาก Discord (ต้องมี DISCORD_BOT_TOKEN + DISCORD_ALLOWED_USER_IDS)
# ============================================================
REMOTE_ENABLED = True
REMOTE_POLL_SECONDS = 3.0
REMOTE_MAX_AGE_SECONDS = 120       # ข้ามคำสั่งที่เก่ากว่านี้ (กันคำสั่งเก่าค้างคิวแล้วถูกรันตอนเปิดสคริปต์)

# ============================================================
# ต่อเซิร์ฟเวอร์ใหม่อัตโนมัติ
# ============================================================
RECONNECT_ENABLED = True
RECONNECT_SERVER = ""              # ว่าง = ใช้เซิร์ฟเวอร์ที่เชื่อมอยู่ตอนเริ่มสคริปต์ ใส่เช่น "mc.hypixel.net" เพื่อบังคับ
RECONNECT_DELAYS = (15, 30, 60, 120, 180, 300)   # วินาทีที่รอก่อนลองครั้งที่ 1,2,3... (จำนวนตัว = จำนวนครั้งสูงสุด)
RECONNECT_CONNECT_TIMEOUT = 45     # รอเข้าเซิร์ฟเวอร์สำเร็จได้ไม่เกินกี่วินาทีต่อครั้ง
# เหตุผลที่หลุดตรงกับ regex นี้ = ถูกแบน/ไล่ออกเพราะผิดกฎ → ไม่ต่อเอง ส่ง Discord แจ้งแล้วหยุด
RECONNECT_DENY_REGEX = r"\bban(ned)?\b|permanent|suspicious|cheat|hack|unfair|appeal|blacklist|compromised|security"
RECONNECT_IF_REASON_UNKNOWN = True # อ่านเหตุผลที่หลุดไม่ได้ → ต่อต่อไปหรือไม่
RECONNECT_MAX_PER_HOUR = 8         # หลุด→ต่อสำเร็จ→หลุดอีก วนเกินกี่รอบใน 1 ชั่วโมงถือว่าเน็ต/เซิร์ฟเวอร์มีปัญหา หยุดต่อเอง
RECONNECT_REQUIRE_DISCONNECT_SCREEN = True   # ต่อเฉพาะตอนเกมขึ้นหน้าจอ Disconnected (หลุด/ถูกเตะ) ไม่ต่อถ้าคุณกดออกเอง
