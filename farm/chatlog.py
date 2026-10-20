# -*- coding: utf-8 -*-
"""
chatlog.py — อ่านแชทจากไฟล์ logs/latest.log ของเกม

ทำไม: chat listener ของ Minescript ส่งมาให้สคริปต์เฉพาะข้อความที่สคริปต์ echo เอง ไม่ส่งข้อความระบบ
ที่เซิร์ฟเวอร์ส่ง (ตรวจจาก log จริง: ข้อความ YUCK!/SkyHanni ไม่ถึง event_loop เลย)
แต่ทุกบรรทัดแชทถูกเขียนลง latest.log ทันที จึงอ่านท้ายไฟล์นั้นแทน
"""

import os
import re
import threading
import time

_CHAT_RE = re.compile(r"\[CHAT\]\s?(.*)$")
_active = False
_started = False


def extract_chat(line: str):
    """คืนข้อความแชทจากบรรทัด log ถ้าเป็นบรรทัดแชท ไม่งั้น None"""
    m = _CHAT_RE.search(line)
    return m.group(1) if m else None


def find_log_path():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), "logs", "latest.log"),
        os.path.join(os.getcwd(), "..", "logs", "latest.log"),
        os.path.join(here, "..", "..", "logs", "latest.log"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


def is_active() -> bool:
    return _active


def tail(path: str, handlers, poll: float = 0.1, stop=lambda: False):
    """อ่านบรรทัดใหม่ท้ายไฟล์ แล้วเรียก handlers ทุกตัวด้วยข้อความแชท"""
    global _active
    pos = os.path.getsize(path)   # ข้ามประวัติเก่า เริ่มจากตอนนี้
    pending = b""
    _active = True
    try:
        while not stop():
            try:
                size = os.path.getsize(path)
                if size < pos:        # log ถูก rotate/ตัดใหม่
                    pos, pending = 0, b""
                if size > pos:
                    with open(path, "rb") as f:
                        f.seek(pos)
                        data = f.read(size - pos)
                    pos = size
                    pending += data
                    *lines, pending = pending.split(b"\n")
                    for raw in lines:
                        msg = extract_chat(raw.decode("utf-8", errors="replace").rstrip("\r"))
                        if msg is None:
                            continue
                        for h in handlers:
                            try:
                                h(msg)
                            except Exception:
                                pass
            except OSError:
                pass
            time.sleep(poll)
    finally:
        _active = False


def start(handlers) -> bool:
    """เริ่ม thread อ่าน log คืน True ถ้าหาไฟล์ log เจอ"""
    global _started
    if _started:
        return _active or True
    path = find_log_path()
    if not path:
        return False
    _started = True
    threading.Thread(target=tail, args=(path, handlers), daemon=True).start()
    time.sleep(0.05)
    return True
