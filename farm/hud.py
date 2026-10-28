# -*- coding: utf-8 -*-
"""
hud.py — แผงสถานะบนจอ (profile, mode, รอบ, เวลา, pest, บัฟ/สเปรย์ที่เหลือ)

วาดผ่าน system/lib/lib_ren.py (Lib Ren-v2) ซึ่งตอน import จะรอ socket จากสคริปต์ในเกม
จึง import ใน thread ของ HUD เท่านั้น ถ้า lib พังหรือค้าง บอทยังฟาร์มต่อได้ปกติ
"""

import threading
import time

from farm.config import (
    HUD_ENABLED, HUD_ANCHOR, HUD_X, HUD_Y, HUD_UPDATE_INTERVAL,
    AMOUNT_OF_PESTS, BUFF_EVERY_SECONDS, SPRAY_EVERY_SECONDS,
)
from farm.utils import cecho, WARN
from farm import sensors
import farm.state as state

_started = False
_stop = threading.Event()
_draw_lock = threading.Lock()   # กันไม่ให้วาดเฟรมใหม่ทับหลัง stop() ลบแผงแล้ว
_renderer = None

_CHAR_W = 6      # ความกว้างตัวอักษรของ font เกมโดยประมาณ (GUI pixel)
_LINE_H = 10
_PAD = 4

# (alpha, red, green, blue)
_BG = (140, 0, 0, 0)
_WHITE = (255, 255, 255, 255)
_GRAY = (255, 170, 170, 170)
_GOLD = (255, 255, 170, 0)
_GREEN = (255, 85, 255, 85)
_YELLOW = (255, 255, 255, 85)
_RED = (255, 255, 85, 85)

_MODE_COLORS = {
    state.Mode.FARMING: _GREEN,
    state.Mode.PEST: _RED,
    state.Mode.SPRAY: _YELLOW,
    state.Mode.RECOVERY: _RED,
    state.Mode.SWITCHING: _YELLOW,
}


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _countdown(last_time: float, every: float) -> str:
    if every <= 0:
        return "off"
    left = every - (time.time() - last_time)
    return "due" if left <= 0 else _fmt_duration(left)


def _lines(profile: dict) -> list:
    """แต่ละบรรทัด = (ข้อความ, สี)"""
    if not state.is_running:
        status, status_color = "STOPPED", _GRAY
    elif state.paused:
        status, status_color = "PAUSED", _YELLOW
    else:
        status, status_color = "RUNNING", _GREEN

    lines = [
        (f"Farm: {profile['name']}", _GOLD),
        (f"Status: {status}", status_color),
        (f"Mode: {state.mode}", _MODE_COLORS.get(state.mode, _WHITE)),
    ]

    if state.start_time:
        elapsed = time.time() - state.start_time
        rph = state.round_count / (elapsed / 3600) if elapsed > 60 else 0
        lines.append((f"Round: {state.round_count}  ({rph:.1f}/hr)", _WHITE))
        lines.append((f"Time: {_fmt_duration(elapsed)}", _WHITE))

    (count, plots), _t = sensors.cached_pests()
    alive = max(state.pest_alive_hint, count)
    pest_color = _RED if alive >= AMOUNT_OF_PESTS else (_YELLOW if alive else _WHITE)
    pest_line = f"Pests: {alive}/{AMOUNT_OF_PESTS}"
    if plots:
        pest_line += f"  [{', '.join(plots)}]"
    lines.append((pest_line, pest_color))

    lines.append((f"Buff in: {_countdown(state.last_buff_time, BUFF_EVERY_SECONDS)}", _WHITE))
    if profile.get("spray_plots"):
        lines.append((f"Spray in: {_countdown(state.last_spray_time, SPRAY_EVERY_SECONDS)}", _WHITE))

    if state.failsafe_reason:
        lines.append((f"Failsafe: {state.failsafe_reason}", _RED))
    return lines


def _draw(gui, lines: list, screen_w: int) -> None:
    width = max(len(text) for text, _ in lines) * _CHAR_W + _PAD * 2
    height = len(lines) * _LINE_H + _PAD * 2 - 2
    # ยังไม่รู้ความกว้างจอ (0) ก็วางชิดซ้ายไปก่อน
    x = screen_w - HUD_X - width if HUD_ANCHOR == "right" and screen_w > 0 else HUD_X
    gui.fill(x, HUD_Y, x + width, HUD_Y + height, _BG)
    for i, (text, color) in enumerate(lines):
        gui.text(text, x + _PAD, HUD_Y + _PAD + i * _LINE_H, color)


def _loop(profile: dict) -> None:
    global _renderer
    try:
        from system.lib.lib_ren import Renderer   # บล็อกจนสคริปต์ในเกมต่อ socket เสร็จ
        _renderer = Renderer("farm-hud")
    except Exception as e:
        cecho(f"[HUD] lib_ren failed to load, HUD off: {e}", WARN)
        return

    while not _stop.is_set():
        try:
            lines = _lines(profile)
            with _draw_lock:
                if _stop.is_set():
                    break
                with _renderer.GuiGraphics as gui:   # รอเฟรมก่อน ขนาดจอจึงเป็นค่าล่าสุด
                    _draw(gui, lines, _renderer._screen_size[0])
        except Exception as e:
            cecho(f"[HUD] draw error: {e}", WARN)
        _stop.wait(HUD_UPDATE_INTERVAL)


def start(profile: dict) -> None:
    global _started
    if _started or not HUD_ENABLED:
        return
    _started = True
    threading.Thread(target=_loop, args=(profile,), daemon=True).start()


def stop() -> None:
    """หยุดอัปเดตและล้างแผงออกจากจอ"""
    _stop.set()
    if _renderer is None:
        return
    if not _draw_lock.acquire(timeout=1.0):   # เฟรมค้าง (เกมไม่วาด) ก็ไม่รอนานกว่านี้
        return
    try:
        _renderer.clear()
        _renderer.push_stack()   # ส่งชุดคำสั่งว่าง = ลบแผง
    except Exception:
        pass
    finally:
        _draw_lock.release()
