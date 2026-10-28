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
from collections import deque

from system.lib import minescript as ms
from farm.config import (
    FAILSAFE_ENABLED, FAILSAFE_JUMP_BLOCKS, FAILSAFE_SCREEN_POLLS,
    FAILSAFE_BEDROCK_CHECK_SECONDS, FAILSAFE_BEDROCK_MIN_BLOCKS,
    FAILSAFE_ROTATION_DEGREES, FAILSAFE_GRACE_SECONDS, FAILSAFE_MAX_GAP_SECONDS,
    FAILSAFE_GUI_ENABLED, FAILSAFE_RUBBERBAND_ENABLED, FAILSAFE_HISTORY_SECONDS,
    FAILSAFE_RUBBERBAND_TOLERANCE, FAILSAFE_RUBBERBAND_MAX_BLOCKS, FAILSAFE_RUBBERBAND_GRACE,
    FAILSAFE_RUBBERBAND_LIMIT,
)
from farm.utils import cecho, ERROR, WARN
from farm.movement import release_all_keys, stop_all_movement
from farm import sensors, tab_bridge, notify
import farm.state as state

_started = False


# ---------- ตัวตรวจแบบ pure (ทดสอบออฟไลน์ได้) ----------

def teleport_detected(prev, cur, threshold: float) -> bool:
    """ตำแหน่งระหว่างสองการอ่านติดกันต่างกันเกิน threshold บล็อก (เดินปกติไม่มีทางเกิน)"""
    return prev is not None and math.dist(prev, cur) > threshold


def is_rubber_band(prev, cur, history, tolerance: float, max_blocks: float) -> bool:
    """ตำแหน่งที่กระโดดนี้เป็นการถูกดึงกลับเพราะเน็ตกระตุก (ไม่ใช่วาร์ปจริง) หรือไม่
    rubber-band = เซิร์ฟเวอร์ดึงกลับไปจุดที่เพิ่งเดินผ่าน → ตำแหน่งใหม่อยู่ใกล้จุดใดจุดหนึ่งใน history
    วาร์ปจริง (ถูกย้ายไปที่ใหม่) จะไม่ตรงกับเส้นทางที่เพิ่งเดินและมักไกลกว่ามาก
    history = ตำแหน่งที่เคยอ่านได้ย้อนหลัง (ไม่ต้องกรองจุด prev ออก มันอยู่ไกลจาก cur เสมอเมื่อกระโดด)"""
    if prev is None or math.dist(prev, cur) > max_blocks:
        return False
    return any(math.dist(p, cur) <= tolerance for p in history)


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
    notify.failsafe(reason)   # Discord (thread แยก ไม่หน่วงการหยุด)
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
    history = deque()        # (เวลา, ตำแหน่ง) ที่เดินผ่านล่าสุด ไว้แยกเน็ตกระตุกออกจากวาร์ปจริง
    rubber_times = deque()   # เวลาที่ถูกดึงกลับล่าสุด (นับความถี่)
    rubber_until = 0.0       # ก่อนเวลานี้ข้ามการตรวจมุมกล้อง
    while True:
        time.sleep(0.1)
        try:
            if not _active():
                prev_pos, prev_ori, screen_polls, active_since = None, None, 0, None
                history.clear()
                rubber_times.clear()
                continue
            if active_since is None:
                active_since = time.time()
                base_frames = tab_bridge.screen_frames()
            if state.failsafe_reason:
                state.failsafe_reason = ""   # เริ่มรอบใหม่หลังผู้เล่นกดเริ่มเอง

            now = time.time()
            if prev_pos is not None and now - prev_t > FAILSAFE_MAX_GAP_SECONDS:
                prev_pos, prev_ori = None, None    # loop สะดุด (เช่นรอ API) ตำแหน่งเก่าเกินไปจะเทียบไม่ได้ เริ่มวัดใหม่
                history.clear()
            prev_t = now

            pos = sensors.position()
            if teleport_detected(prev_pos, pos, FAILSAFE_JUMP_BLOCKS):
                jump = math.dist(prev_pos, pos)
                if FAILSAFE_RUBBERBAND_ENABLED and is_rubber_band(
                    prev_pos, pos, [p for _, p in history],
                    FAILSAFE_RUBBERBAND_TOLERANCE, FAILSAFE_RUBBERBAND_MAX_BLOCKS,
                ):
                    # เน็ตกระตุก: ถูกดึงกลับไปจุดที่เพิ่งผ่าน ไม่ใช่วาร์ปจริง → เตือนเฉย ๆ แล้วเดินต่อ
                    rubber_times.append(now)
                    limit, window = FAILSAFE_RUBBERBAND_LIMIT
                    while rubber_times and now - rubber_times[0] > window:
                        rubber_times.popleft()
                    cecho(f"[Failsafe] ถูกดึงกลับ {jump:.1f} บล็อก (เน็ตกระตุก?) ข้ามไป "
                          f"[{len(rubber_times)} ครั้งใน {window:.0f}s]", WARN)
                    rubber_until = now + FAILSAFE_RUBBERBAND_GRACE
                    prev_ori = None
                    if limit > 0 and len(rubber_times) >= limit:
                        trigger(f"ถูกดึงกลับ {len(rubber_times)} ครั้งใน {window:.0f} วินาที (เน็ตไม่เสถียรเกินไป)")
                        continue
                else:
                    trigger(f"ถูกวาร์ป/ดึงตำแหน่งผิดปกติ ({jump:.1f} บล็อก)")
                    continue
            prev_pos = pos
            history.append((now, pos))
            while history and now - history[0][0] > FAILSAFE_HISTORY_SECONDS:
                history.popleft()

            ori = tuple(ms.player_orientation())
            if now < rubber_until:
                prev_ori = ori        # เพิ่งถูกดึงกลับ: มุมกล้องอาจถูกรีเซ็ตพร้อมกัน ยังไม่ตรวจรอบนี้
            elif rotation_jumped(prev_ori, ori, FAILSAFE_ROTATION_DEGREES):
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
