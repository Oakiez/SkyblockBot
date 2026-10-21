# -*- coding: utf-8 -*-
"""
failsafe.py — ตรวจว่ามีเหตุผิดปกติที่ "เหมือนการตรวจ macro" แล้ว **หยุดบอททันที** ให้คนมาดูเอง

ขอบเขตของโมดูลนี้ (ตั้งใจจำกัดไว้):
  ✔ ตรวจ: ถูกวาร์ปผิดปกติ/ดึงถอยหลัง, มีหน้าจอ GUI โผล่ที่สคริปต์ไม่ได้เปิด, โดนล้อมด้วย bedrock
  ✔ ตอบสนอง: ปล่อยปุ่ม + หยุดบอท + แจ้งเตือนดัง ๆ แล้วรอให้ผู้เล่นตัดสินใจเอง
  ✘ ไม่ตอบ/ผ่านการตรวจแทนผู้เล่น ไม่สุ่มมุมกล้อง/เวลาให้ดูเหมือนคน ไม่ซ่อนว่าเป็นบอท
"""

import math
import threading
import time

from system.lib import minescript as ms
from farm.config import (
    FAILSAFE_ENABLED, FAILSAFE_JUMP_BLOCKS, FAILSAFE_SCREEN_POLLS,
    FAILSAFE_BEDROCK_CHECK_SECONDS, FAILSAFE_BEDROCK_MIN_BLOCKS,
    FAILSAFE_ROTATION_DEGREES, FAILSAFE_GRACE_SECONDS, FAILSAFE_MAX_GAP_SECONDS,
    FAILSAFE_GUI_ENABLED,
)
from farm.utils import cecho, ERROR, WARN
from farm.movement import release_all_keys, stop_all_movement
from farm import sensors, tab_bridge
import farm.state as state

_started = False


# ---------- ตัวตรวจแบบ pure (ทดสอบออฟไลน์ได้) ----------

def teleport_detected(prev, cur, threshold: float) -> bool:
    """ตำแหน่งระหว่างสองการอ่านติดกันต่างกันเกิน threshold บล็อก (เดินปกติไม่มีทางเกิน)"""
    return prev is not None and math.dist(prev, cur) > threshold


def rotation_jumped(prev, cur, threshold: float) -> bool:
    """มุมกล้อง (yaw, pitch) เปลี่ยนเกิน threshold องศาในรอบเดียว (คิด yaw แบบวนรอบ ±180)"""
    if prev is None:
        return False
    dyaw = abs((cur[0] - prev[0] + 180.0) % 360.0 - 180.0)
    dpitch = abs(cur[1] - prev[1])
    return max(dyaw, dpitch) > threshold


def count_bedrock(block_names) -> int:
    return sum(1 for n in block_names if n and "bedrock" in n.lower())


def enclosure_positions(pos):
    """9 จุดที่ใช้ตัดสินว่าถูกขังกล่อง: 4 ทิศ (เหนือ/ใต้/ออก/ตก) ที่ระดับเท้าและหัว + เหนือหัว
    ฟาร์มที่อยู่ติดขอบ bedrock จะเจอ bedrock แค่ 1-3 จุด ไม่ใช่เกือบทุกจุดเหมือนถูกขัง"""
    x, y, z = (math.floor(v) for v in pos)
    around = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    pts = [[x + dx, y + dy, z + dz] for dx, dz in around for dy in (0, 1)]
    pts.append([x, y + 2, z])
    return pts


# ---------- ตัวหยุดบอท ----------

def trigger(reason: str) -> None:
    """หยุดบอททันที ไม่ทำอะไรต่อ ให้ผู้เล่นตรวจสอบเอง"""
    if state.failsafe_reason:
        return
    state.failsafe_reason = reason
    state.is_running = False
    try:
        release_all_keys()
        stop_all_movement()
    except Exception:
        pass
    for _ in range(3):
        cecho(f"🛑 FAILSAFE: {reason} — บอทหยุดแล้ว ตรวจสอบด้วยตัวเอง (กด ] เมื่อพร้อมเริ่มใหม่)", ERROR)


def _active() -> bool:
    return (
        FAILSAFE_ENABLED
        and state.is_running
        and not state.paused
        and not state.changing_outfit
        and state.mode == state.Mode.FARMING
        and time.time() >= state.teleport_expected_until
    )


def _loop():
    prev_pos = None
    prev_ori = None
    prev_t = 0.0
    screen_polls = 0
    active_since = None
    base_frames = 0
    while True:
        time.sleep(0.1)
        try:
            if not _active():
                prev_pos, prev_ori, screen_polls, active_since = None, None, 0, None
                continue
            if active_since is None:
                active_since = time.time()
                base_frames = tab_bridge.screen_frames()
            if state.failsafe_reason:
                state.failsafe_reason = ""   # เริ่มรอบใหม่หลังผู้เล่นกดเริ่มเอง

            now = time.time()
            if prev_pos is not None and now - prev_t > FAILSAFE_MAX_GAP_SECONDS:
                prev_pos, prev_ori = None, None    # loop สะดุด (เช่นรอ API) ตำแหน่งเก่าเกินไปจะเทียบไม่ได้ เริ่มวัดใหม่
            prev_t = now

            pos = sensors.position()
            if teleport_detected(prev_pos, pos, FAILSAFE_JUMP_BLOCKS):
                trigger(f"ถูกวาร์ป/ดึงตำแหน่งผิดปกติ ({math.dist(prev_pos, pos):.1f} บล็อก)")
                continue
            prev_pos = pos

            ori = tuple(ms.player_orientation())
            if rotation_jumped(prev_ori, ori, FAILSAFE_ROTATION_DEGREES):
                trigger("ถูกหันหัว/เปลี่ยนมุมกล้องโดยไม่ได้สั่ง")
                continue
            prev_ori = ori

            # GUI ที่แว็บสั้น ๆ (อาจสั้นกว่ารอบตรวจ 0.1 วินาที): นับจากเฟรมในเกมผ่าน bridge
            if not FAILSAFE_GUI_ENABLED:
                continue
            frames = tab_bridge.screen_frames()
            if time.time() - active_since < FAILSAFE_GRACE_SECONDS:
                base_frames = frames          # ช่วงเพิ่งกลับเข้าโหมดฟาร์ม: ยังไม่นับ (GUI ของสคริปต์เองอาจเพิ่งปิด)
            elif frames > base_frames:
                trigger(f"GUI แว็บขึ้นมาโดยไม่ได้สั่ง ({frames - base_frames} เฟรม)")
                continue

            name = ms.screen_name()
            screen_polls = screen_polls + 1 if name else 0
            if screen_polls >= FAILSAFE_SCREEN_POLLS:
                trigger(f"มีหน้าจอ GUI เปิดโดยไม่ได้สั่ง ({name})")
                continue

        except Exception:
            pass


def _bedrock_loop():
    """แยก thread: getblocklist ช้ากว่ารอบตรวจอื่น ไม่ควรไปดึงรอบตรวจตำแหน่งให้สะดุด"""
    while True:
        time.sleep(FAILSAFE_BEDROCK_CHECK_SECONDS)
        try:
            if not _active():
                continue
            names = ms.getblocklist(enclosure_positions(sensors.position()))
            if count_bedrock(names) >= FAILSAFE_BEDROCK_MIN_BLOCKS:
                trigger("ถูกล้อมด้วย bedrock")
        except Exception:
            pass


def start() -> None:
    global _started
    if _started or not FAILSAFE_ENABLED:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True).start()
    threading.Thread(target=_bedrock_loop, daemon=True).start()
