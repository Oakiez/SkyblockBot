# -*- coding: utf-8 -*-
"""
notify.py — จุดแจ้งเตือน Discord ของ farm (ตัวส่งจริงอยู่ที่ botkit)

farm_loop ตั้ง notify.link = BotLink(...) ตอนเริ่ม ถ้ายังไม่มี link ก็ส่งแบบไม่มีฟิลด์สถานะ
ส่งใน thread แยกเสมอ: เน็ตช้า/Discord ล่มต้องไม่หน่วงการหยุดบอท
"""

from botkit import discord_io as dio
from botkit import settings
from farm.utils import cecho, WARN

link = None   # ตั้งโดย farm_loop.auto_farm


def event(title: str, description: str = "", level: str = "info", screenshot: bool = False,
          wait: bool = False) -> None:
    """แจ้งเตือนเหตุการณ์ของ farm พร้อมสถานะปัจจุบัน (รอบ, เวลา, pest, ตำแหน่ง ฯลฯ)"""
    if link is not None:
        link.alert(title, description, level, screenshot, wait=wait)
    else:
        dio.alert(title, description, level, None, screenshot, footer="farm", wait=wait)


def failsafe(reason: str) -> None:
    """failsafe หยุดบอท → แจ้ง Discord (ระดับ error: แท็ก + แนบภาพหน้าจอ)"""
    if not settings.DISCORD_NOTIFY:
        return
    if not settings.DISCORD_WEBHOOK_URL:
        cecho("[Discord] DISCORD_WEBHOOK_URL not set — failsafe alert not sent", WARN)
        return
    event("🛑 Failsafe — farm stopped", reason, "error", screenshot=True)
