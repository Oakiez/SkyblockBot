# -*- coding: utf-8 -*-
"""
utils.py — Utility functions ที่ใช้ร่วมกันทุก module
"""

import re
import time
from system.lib import minescript as ms
from system.lib.minescript import render_loop

# ============================================================
# COLOR REFERENCE
# ============================================================
# "black", "dark_blue", "dark_green", "dark_aqua", "dark_red",
# "dark_purple", "gold", "gray", "dark_gray", "blue",
# "green", "aqua", "red", "light_purple", "yellow", "white"
# หรือ hex เช่น "#FF5500"

# สีที่ใช้บ่อยในโปรเจกต์นี้
INFO = "white"
SUCCESS = "green"
WARN = "yellow"
ERROR = "red"
DETAIL = "gray"
GOLD = "gold"
AQUA = "aqua"


def strip_color_codes(text: str) -> str:
    """ลบ Minecraft color codes ออกจาก string"""
    return re.sub(r"§[0-9a-fk-or]", "", text)


_QUIET_COLORS = ("gray", "aqua")   # DETAIL, AQUA = ข้อความรายละเอียด


def _chat_quiet() -> bool:
    try:
        from farm.config import CHAT_QUIET
        return CHAT_QUIET
    except Exception:
        return False


def cecho(msg: str, color: str = "white"):
    """
    echo ที่เรียกได้จาก background thread พร้อมสีข้อความ

    ตัวอย่าง:
        cecho("✅ Done", "green")
        cecho("⚠ Warning!", "yellow")
        cecho("❌ Error", "red")
        cecho("🚜 Farming...", "gold")
        cecho("│ info", "gray")
    """
    if color in _QUIET_COLORS and _chat_quiet():
        return
    with render_loop:
        ms.echo_json([{"text": msg, "color": color}])


# backward compat
safe_echo = cecho


def wait_until(predicate, timeout: float, interval: float = 0.02) -> bool:
    """รอจน predicate() เป็นจริง คืน True ถ้าทันใน timeout (ใช้แทน sleep ตายตัว)"""
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(interval)
    return False
