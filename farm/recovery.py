# -*- coding: utf-8 -*-
"""
recovery.py — Limbo, server restart, server change detection
"""

import re
import threading
import time

from system.lib import minescript as ms
from farm.utils import cecho, SUCCESS, WARN, ERROR, DETAIL, GOLD, AQUA, strip_color_codes
from farm.movement import fly, stop_fly, release_all_keys, warp_to_garden_and_land
import farm.state as state
from farm.config import PEST_COOLDOWN_TRIGGER_SECONDS


# ============================================================
# LIMBO
# ============================================================

def handle_limbo():
    cecho("[Script] Limbo detected! Recovering...", ERROR)
    was_running = state.is_running
    prev_mode = state.mode
    state.mode = state.Mode.RECOVERY
    state.is_running = False
    release_all_keys()
    time.sleep(5)
    ms.execute("/lobby")
    time.sleep(5)
    ms.execute("/skyblock")
    time.sleep(5)
    ms.execute("/warp garden")
    time.sleep(5)
    fly()
    stop_fly()
    ms.player_press_attack(True)
    time.sleep(0.5)
    state.limbo_detected = False
    state.mode = prev_mode
    if was_running:
        state.is_running = True
        cecho("[Script] Limbo recovery complete, resuming farm...", SUCCESS)


def check_for_limbo_message(message: str) -> bool:
    clean = strip_color_codes(message).lower()
    if "you were spawned in limbo" in clean or "/limbo for more information" in clean:
        if state.is_running and not state.limbo_detected:
            state.limbo_detected = True
            threading.Thread(target=handle_limbo, daemon=True).start()
            return True
    return False


# ============================================================
# SERVER RESTART
# ============================================================

def handle_restart():
    cecho("[Script] Server restart detected! Waiting 20s...", ERROR)
    was_running = state.is_running
    prev_mode = state.mode
    state.mode = state.Mode.RECOVERY
    state.is_running = False
    release_all_keys()
    ms.execute("/hub")
    time.sleep(25)          # ← เพิ่มจาก 20 เป็น 25
    ms.execute("/skyblock")
    time.sleep(10)          # ← เพิ่มจาก 5 เป็น 10 ให้โหลดเสร็จก่อน
    ms.execute("/warp garden")
    time.sleep(5)
    # เผื่อโดน evacuate ออกไป hub ให้กลับมาอีกรอบ
    ms.execute("/skyblock")
    time.sleep(10)
    ms.execute("/warp garden")
    time.sleep(5)
    state.restart_detected = False
    state.mode = prev_mode
    if was_running:
        state.is_running = True
        cecho("[Script] Restart recovery complete, resuming farm...", SUCCESS)


def check_for_restart_message(message: str) -> bool:
    clean = strip_color_codes(message).lower()
    if re.search(r"\[important\].*this server will.*reboot", clean):
        if state.is_running and not state.restart_detected:
            state.restart_detected = True
            threading.Thread(target=handle_restart, daemon=True).start()
            return True
    return False


# ============================================================
# SERVER CHANGE
# ============================================================

_last_known_position = None


def check_server_change() -> bool:
    global _last_known_position
    try:
        new_pos = ms.player().position
    except:
        return False

    if _last_known_position is None:
        _last_known_position = new_pos
        return False

    if new_pos and _last_known_position:
        if sum(abs(a - b) for a, b in zip(new_pos, _last_known_position)) > 1000:
            return True
    return False


# ============================================================
# PEST MESSAGES (SkyHanni)
# ============================================================

# ตัวอย่างข้อความ: "YUCK! 6 ൠ Pest have spawned in Plot - 4! CLICK HERE to teleport to the plot!"
# (1 ตัวจะเป็น "1 ൠ Pest has spawned in Plot - 4!") — มีสัญลักษณ์คั่นระหว่างตัวเลขกับคำว่า Pest
_PEST_SPAWN_RE = re.compile(r"(\d+)\D{0,8}?pests?\s+(?:have|has)\s+spawned\s+in\s+plot\s*-?\s*(\d+)")


def parse_pest_spawn(message: str):
    """คืน (จำนวน, plot) ถ้าเป็นข้อความ pest เกิด ไม่งั้น None"""
    m = _PEST_SPAWN_RE.search(strip_color_codes(message).lower())
    return (int(m.group(1)), int(m.group(2))) if m else None


def check_for_pest_spawn_message(message: str) -> bool:
    info = parse_pest_spawn(message)
    clean = strip_color_codes(message).lower()
    # รูปแบบหลัก = ข้อความจากเกม; รูปแบบสำรอง = ข้อความของ SkyHanni ที่มี "pest" + "spawned in"
    if info is None and not ("pest" in clean and "spawned in" in clean):
        return False
    if not state.is_running:
        return False
    # ไม่ทิ้งข้อความเพราะกำลังสลับชุดแล้ว (เคยทำให้พลาดตอนเพิ่งกดเริ่ม) — ส่งเข้าคิวเสมอ
    if state.cycling_pests:
        return False
    if info:
        state.pest_alive_hint += info[0]
        state.pending_pest_plots.add(str(info[1]))
    if time.time() - state.last_pest_spawn_time < 5:
        return False   # ข้อความซ้ำ/ติดกัน: ข้อมูลเก็บไว้แล้ว แต่ไม่ต้องส่ง event ซ้ำ
    state.last_pest_spawn_time = time.time()
    state.last_spawn_info = info
    detail = f" ({info[0]} pests in plot {info[1]})" if info else ""
    cecho(f"[Pest] Pests spawned{detail}! Queued: Farm loadout", WARN)
    state.post_event("PEST_SPAWNED")
    return True


_COOLDOWN_RE = re.compile(r"pest spawn cooldown expires in\s*(\d+)\s*s")


def parse_pest_cooldown(message: str):
    """คืนจำนวนวินาทีที่เหลือจากข้อความ SkyHanni \"Pest spawn cooldown expires in Ns\" ไม่งั้น None"""
    m = _COOLDOWN_RE.search(strip_color_codes(message).lower())
    return int(m.group(1)) if m else None


def check_for_pest_cooldown_message(message: str) -> bool:
    secs = parse_pest_cooldown(message)
    if secs is not None and secs <= PEST_COOLDOWN_TRIGGER_SECONDS and state.is_running:
        if state.cycling_pests or state.spraying_plots or state.flying_to_start:
            return False
        if time.time() - state.last_cooldown_event_time < 10:
            return False   # SkyHanni ส่งซ้ำได้ ไม่ต้องสลับซ้ำ
        state.last_cooldown_event_time = time.time()
        cecho("[SkyHanni] Pest cooldown ending! Queued: Pest loadout", WARN)
        state.post_event("PEST_COOLDOWN")
        return True
    return False