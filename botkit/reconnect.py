# -*- coding: utf-8 -*-
"""
reconnect.py — ต่อเซิร์ฟเวอร์ใหม่อัตโนมัติเมื่อหลุด

ทำงานฝั่ง Python ล้วน โดยเรียก ConnectScreen.startConnecting(...) ของเกมผ่าน JavaClass
(ลายเซ็นตรวจจากไฟล์เกม 26.2 แล้ว: startConnecting(Screen, Minecraft, ServerAddress, ServerData, boolean, TransferState))

ขั้นตอน (ทุกขั้นมีตัวกัน):
  1) สคริปต์ต้องมี world listener (farm/mining มี) — Minescript ถึงจะไม่ปิดสคริปต์ตอนหลุดเซิร์ฟเวอร์
  2) เกมต้องขึ้นหน้าจอ Disconnected (หลุด/ถูกเตะ) — ถ้าคุณกด Disconnect เอง (ไปหน้า Title) ไม่ต่อ
  3) เหตุผลที่หลุดตรง RECONNECT_DENY_REGEX (ถูกแบน/ผิดกฎ) → ไม่ต่อ ส่ง Discord แจ้ง
  4) ลองตาม RECONNECT_DELAYS (รอเพิ่มทุกครั้ง) ระหว่างรอถ้าคุณขยับเกมเอง (ออกจากหน้าจอ Disconnected) ก็เลิกต่อ
  5) หลุด→ต่อได้→หลุดอีกถี่เกิน RECONNECT_MAX_PER_HOUR → เลิกต่อเอง
เชื่อมกลับแล้วเรียก after_connected() ให้สคริปต์ทำต่อ (เช่น /skyblock → /warp garden → เริ่มฟาร์ม)
"""

import re
import threading
import time
from collections import deque

from botkit import settings

DISCONNECT_SCREEN = "DisconnectedScreen"
CONNECTING_SCREEN = "ConnectScreen"


# ---------- ส่วนที่แตะ Java (แยกไว้ให้ทดสอบด้วยของปลอมได้) ----------

def _java_class(name: str):
    from system.lib.java import JavaClass
    return JavaClass(name)


def _minecraft():
    return _java_class("net.minecraft.client.Minecraft").getInstance()


def current_server():
    """(ชื่อ, ip) ของเซิร์ฟเวอร์ที่เชื่อมอยู่ หรือ None (เล่นเดี่ยว/ไม่ได้เชื่อมต่อ)"""
    server = _minecraft().getCurrentServer()
    if server is None:
        return None
    return str(server.name), str(server.ip)


def screen_info():
    """(ชื่อคลาสหน้าจอที่เปิดอยู่ | None, ข้อความบนหน้าจอ) ข้อความของ DisconnectedScreen = หัวข้อ + เหตุผลที่หลุด"""
    screen = _minecraft().gui.screen()
    if screen is None:
        return None, ""
    cls = str(screen.getClass().getSimpleName())
    try:
        text = str(screen.getNarrationMessage().getString())
    except Exception:
        text = ""
    return cls, text


def start_connecting(ip: str, name: str) -> None:
    mc = _minecraft()
    connect_screen = _java_class("net.minecraft.client.gui.screens.ConnectScreen")
    server_address = _java_class("net.minecraft.client.multiplayer.resolver.ServerAddress")
    server_data = _java_class("net.minecraft.client.multiplayer.ServerData")
    server_type = _java_class("net.minecraft.client.multiplayer.ServerData$Type")
    title_screen = _java_class("net.minecraft.client.gui.screens.TitleScreen")
    data = server_data(name, ip, server_type.OTHER)
    # parent = หน้าจอที่จะกลับไปถ้าต่อไม่สำเร็จ (ใช้หน้า Title เหมือนปุ่ม Back to Title ของเกม)
    connect_screen.startConnecting(title_screen(), mc, server_address.parseString(ip), data, False, None)


# ---------- ตัวควบคุม ----------

class Reconnector:
    """notify(title, description, level, screenshot=False) = ตัวแจ้งเตือนของสคริปต์ (ส่ง Discord/แชท)
    after_connected() = เรียกหลังเชื่อมกลับสำเร็จ (ใน thread ของตัวต่อใหม่เอง)"""

    def __init__(self, notify, after_connected=None):
        self.notify = notify
        self.after_connected = after_connected
        self._server = None          # (name, ip)
        self._connected = True       # สคริปต์เริ่มตอนอยู่ในเกมแล้ว
        self._evt = threading.Event()
        self._cancel = threading.Event()
        self._thread = None
        self._history = deque()      # เวลาที่เริ่มกระบวนการต่อใหม่ (ไว้นับต่อชั่วโมง)
        self._deny = re.compile(settings.RECONNECT_DENY_REGEX, re.I)

    # ----- สถานะ -----
    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def server(self):
        return self._server

    def remember_server(self) -> None:
        """จำเซิร์ฟเวอร์ที่เชื่อมอยู่ (เรียกตอนเริ่มและทุกครั้งที่เชื่อมสำเร็จ) ไม่ทำอะไรถ้ากำลังต่อใหม่อยู่"""
        if settings.RECONNECT_SERVER:
            self._server = ("Minecraft Server", settings.RECONNECT_SERVER)
            return
        if self.active or not self._connected:
            return
        try:
            found = current_server()
        except Exception:
            found = None
        if found:
            self._server = found

    def world_event(self, connected: bool) -> None:
        self._connected = bool(connected)
        self._evt.set()

    def cancel(self) -> None:
        self._cancel.set()
        self._evt.set()

    # ----- เริ่มกระบวนการต่อใหม่ -----
    def begin(self, reason: str = "") -> bool:
        """เรียกตอนได้ event "หลุดจากโลก" คืน True ถ้าเริ่มกระบวนการต่อใหม่ (False = ปิดอยู่/กำลังทำอยู่/ไม่รู้เซิร์ฟเวอร์)"""
        if not settings.RECONNECT_ENABLED or self.active:
            return False
        if self._server is None:
            self.notify("🔌 หลุดจากเซิร์ฟเวอร์", "ไม่ทราบที่อยู่เซิร์ฟเวอร์ (เริ่มสคริปต์ตอนยังไม่ได้เชื่อมต่อ) — "
                        "ตั้ง RECONNECT_SERVER ใน botkit/settings.py เพื่อให้ต่อเองได้", "error", True)
            return False
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(reason,), daemon=True)
        self._thread.start()
        return True

    # ----- ภายใน -----
    def _sleep(self, seconds: float) -> bool:
        """รอ seconds วินาที คืน False ถ้าถูกยกเลิก"""
        return not self._cancel.wait(seconds)

    def _wait_connected(self, timeout: float) -> bool:
        end = time.time() + timeout
        while time.time() < end and not self._cancel.is_set():
            if self._connected:
                return True
            self._evt.clear()
            self._evt.wait(min(1.0, max(0.0, end - time.time())))
        return self._connected

    def _too_frequent(self) -> bool:
        now = time.time()
        while self._history and now - self._history[0] > 3600:
            self._history.popleft()
        self._history.append(now)
        return len(self._history) > settings.RECONNECT_MAX_PER_HOUR

    def _read_screen(self):
        try:
            return screen_info()
        except Exception:
            return None, ""

    def _run(self, reason: str) -> None:
        if not self._sleep(2.0):                      # ให้เกมขึ้นหน้าจอหลังหลุดก่อนค่อยอ่าน
            return
        cls, text = self._read_screen()
        if settings.RECONNECT_REQUIRE_DISCONNECT_SCREEN and cls not in (DISCONNECT_SCREEN, CONNECTING_SCREEN):
            return                                    # ไม่ใช่หลุดจากเซิร์ฟเวอร์ (เช่นคุณกดออกเอง) → ไม่ยุ่ง เงียบ ๆ
        if self._too_frequent():
            self.notify("🔌 หลุดถี่เกินไป — เลิกต่อใหม่เอง",
                        f"หลุดเกิน {settings.RECONNECT_MAX_PER_HOUR} ครั้งใน 1 ชั่วโมง ตรวจเน็ต/เซิร์ฟเวอร์ด้วยตัวเอง", "error", True)
            return
        shown = (text or reason or "ไม่ทราบสาเหตุ").replace("\n", " ")[:300]
        if text and self._deny.search(text):
            self.notify("⛔ ไม่ต่อใหม่: เหตุผลที่หลุดเข้าข่ายผิดกฎ/ถูกแบน", shown, "error", True)
            return
        if not text and not settings.RECONNECT_IF_REASON_UNKNOWN:
            self.notify("⛔ ไม่ต่อใหม่: อ่านเหตุผลที่หลุดไม่ได้", shown, "error", True)
            return
        delays = tuple(settings.RECONNECT_DELAYS)
        self.notify("🔌 หลุดจากเซิร์ฟเวอร์", f"{shown}\nจะลองต่อใหม่ {len(delays)} ครั้ง ครั้งแรกใน {delays[0]} วินาที", "warn", True)

        name, ip = self._server
        for attempt, delay in enumerate(delays, 1):
            if not self._sleep(delay):
                return
            if self._connected:
                break
            cls, text = self._read_screen()
            if settings.RECONNECT_REQUIRE_DISCONNECT_SCREEN and cls not in (DISCONNECT_SCREEN, CONNECTING_SCREEN):
                self.notify("🔌 เลิกต่อใหม่: คุณขยับเกมเอง", f"หน้าจอตอนนี้: {cls}", "info")
                return
            if cls == CONNECTING_SCREEN:
                continue                              # ยังกำลังต่ออยู่ ไม่ซ้อน
            if text and self._deny.search(text):
                self.notify("⛔ ไม่ต่อใหม่: เหตุผลที่หลุดเข้าข่ายผิดกฎ/ถูกแบน", text[:300], "error", True)
                return
            self.notify(f"🔁 ต่อใหม่ครั้งที่ {attempt}/{len(delays)}", f"{name} ({ip})", "info")
            self._evt.clear()
            try:
                start_connecting(ip, name)
            except Exception as e:
                self.notify("⚠️ สั่งต่อเซิร์ฟเวอร์ไม่สำเร็จ", f"{type(e).__name__}: {e}", "warn")
                continue
            if self._wait_connected(settings.RECONNECT_CONNECT_TIMEOUT):
                break
        if self._cancel.is_set():
            return
        if not self._connected:
            self.notify("❌ ต่อเซิร์ฟเวอร์ไม่สำเร็จ — เลิกลอง", f"ลองครบ {len(delays)} ครั้งแล้ว ต้องเข้าเกมมาดูเอง", "error", True)
            return
        self.notify("✅ ต่อเซิร์ฟเวอร์สำเร็จ", f"{name} ({ip})", "ok")
        if self.after_connected:
            try:
                self.after_connected()
            except Exception as e:
                self.notify("⚠️ ขั้นตอนหลังต่อใหม่ล้มเหลว", f"{type(e).__name__}: {e}", "error", True)
