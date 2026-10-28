# -*- coding: utf-8 -*-
"""
link.py — จุดเชื่อมเดียวระหว่างสคริปต์ (farm / mining) กับ Discord

    link = BotLink("farm", status_fn, commands={"stop": do_stop, "pause": do_pause, "resume": do_resume})
    link.start()                       # แจ้งว่าเริ่ม + heartbeat + เริ่มรับคำสั่งจาก Discord
    link.alert("🛑 หยุด", "เหตุผล", "error", screenshot=True)   # แจ้งเตือน (แนบสถานะปัจจุบันให้เอง)
    link.stop()

status_fn() -> [(ชื่อ, ค่า), ...]   เรียกจาก thread อื่น ต้องอ่านอย่างเดียวและไม่บล็อก
commands:  ชื่อคำสั่ง -> ฟังก์ชันไม่รับอาร์กิวเมนต์ คืนข้อความสั้น ๆ บอกผล (เรียกจาก thread ของ remote)
"""

import threading
import time

from botkit import discord_io as dio
from botkit import settings
from botkit.remote import RemoteControl


class BotLink:
    def __init__(self, name: str, status_fn, commands: dict = None):
        self.name = name
        self.status_fn = status_fn
        self.commands = commands or {}
        self.started_at = time.time()
        self._stop = threading.Event()
        self.remote = RemoteControl(self.handle, name)

    # ---------- สถานะ ----------
    def fields(self) -> list:
        try:
            return list(self.status_fn())
        except Exception as e:
            return [("status error", str(e))]

    # ---------- แจ้งเตือน ----------
    def alert(self, title: str, description: str = "", level: str = "info", screenshot: bool = False,
              with_status: bool = True, mention: bool = None, wait: bool = False) -> bool:
        fields = self.fields() if with_status else None
        return dio.alert(f"{title}", description, level, fields, screenshot, mention, footer=self.name, wait=wait)

    # ---------- คำสั่งจาก Discord ----------
    def handle(self, cmd: str):
        if cmd == "status":
            return {"title": f"📊 {self.name} status", "fields": self.fields(), "screenshot": True}
        if cmd == "screenshot":
            return {"title": f"📷 {self.name}", "screenshot": True}
        fn = self.commands.get(cmd)
        if fn is None:
            return None
        dio.log(f"[Remote] {cmd} (จาก Discord)")
        text = fn()
        return {"title": f"✅ {self.name}: {cmd}", "description": text, "level": "ok",
                "fields": self.fields(), "screenshot": cmd == "stop"}

    # ---------- heartbeat ----------
    def _heartbeat_loop(self) -> None:
        interval = settings.HEARTBEAT_MINUTES * 60
        while not self._stop.wait(interval):
            self.alert(f"💓 {self.name} heartbeat", "ยังทำงานอยู่", "info", screenshot=settings.HEARTBEAT_SCREENSHOT)

    # ---------- เริ่ม/หยุด ----------
    def start(self) -> None:
        remote_on = self.remote.start()
        if settings.DISCORD_NOTIFY and settings.DISCORD_WEBHOOK_URL:
            note = ("สั่งการจาก Discord: เปิด (DM `help` ให้ bot)" if remote_on
                    else "สั่งการจาก Discord: ปิด (ยังไม่ตั้ง DISCORD_BOT_TOKEN / DISCORD_ALLOWED_USER_IDS)")
            self.alert(f"▶️ {self.name} started", note, "info")
        if settings.HEARTBEAT_MINUTES > 0:
            threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self.remote.stop()
