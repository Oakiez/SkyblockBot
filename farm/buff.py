# -*- coding: utf-8 -*-
"""
buff.py — เดินไปรับบัฟจาก NPC Phillip (ใช้ร่วมกับ villager.py และ spray_plots)
"""

import math
import time

from system.lib import minescript as ms
from system.lib import lib_inv  # works without mappings

# จุดที่ต้องยืนหน้า NPC "Phillip" และตำแหน่งของ NPC
STAND_X, STAND_Z = -29.5, -8.7
NPC_X, NPC_Y, NPC_Z = -29.5, 72.0, -10.7
ARRIVE_TOLERANCE = 0.35   # ถึงจุดยืนเมื่อห่างไม่เกินนี้ (บล็อก)
WALK_TIMEOUT = 12.0
JUMP_IF_STUCK = 0.5       # ไม่ขยับเกินกี่วินาทีให้กระโดด
BUFF_MENU_SLOT = 11
# True = ถอยหลังชนพุ่มหญ้าก่อนแล้วค่อยเดิน, False = เดินตรงไปหา NPC เลย
USE_BUSH_ANCHOR = False


def _release_keys():
    ms.player_press_forward(False)
    ms.player_press_backward(False)
    ms.player_press_jump(False)
    ms.player_press_sneak(False)


def _look_at(x, y, z):
    """หันกล้องไปที่พิกัดโลก (x, y, z) จากตำแหน่งตา (ตอน sneak ตาสูง ~1.27)"""
    px, py, pz = ms.player_position()
    dx, dy, dz = x - px, y - (py + 1.27), z - pz
    yaw = -math.degrees(math.atan2(dx, dz))
    pitch = -math.degrees(math.atan2(dy, math.hypot(dx, dz)))
    ms.player_set_orientation(yaw, pitch)


def _back_until_blocked(timeout=12.0, stuck_time=0.6) -> bool:
    """ถอยหลังจนชนสิ่งกีดขวาง (พุ่มหญ้าหน้ากระท่อม NPC) ใช้เป็นจุดอ้างอิงตำแหน่ง
    คืน True ถ้าชนจริง False ถ้า timeout"""
    deadline = time.time() + timeout
    last_pos = ms.player_position()
    last_move = time.time()
    ms.player_press_backward(True)
    try:
        while time.time() < deadline:
            time.sleep(0.05)
            pos = ms.player_position()
            if math.hypot(pos[0] - last_pos[0], pos[2] - last_pos[2]) > 0.03:
                last_pos = pos
                last_move = time.time()
            elif time.time() - last_move >= stuck_time:
                return True
        return False
    finally:
        ms.player_press_backward(False)


def _walk_to(x, z) -> bool:
    """เดินหน้าไปยัง (x, z) กระโดดถ้าติด คืน True ถ้าถึงภายใน timeout"""
    deadline = time.time() + WALK_TIMEOUT
    last_pos = ms.player_position()
    last_move = time.time()
    ms.player_press_forward(True)
    try:
        while time.time() < deadline:
            px, py, pz = ms.player_position()
            if math.hypot(x - px, z - pz) <= ARRIVE_TOLERANCE:
                return True
            _look_at(x, py + 1.27, z)

            if math.hypot(px - last_pos[0], pz - last_pos[2]) > 0.05:
                last_pos = (px, py, pz)
                last_move = time.time()
                ms.player_press_jump(False)
            elif time.time() - last_move > JUMP_IF_STUCK:
                ms.player_press_jump(True)  # ติดขอบ/บล็อก → กระโดดข้าม
            time.sleep(0.05)
        return False
    finally:
        ms.player_press_forward(False)
        ms.player_press_jump(False)


def get_buff():
    try:
        ms.echo("📦 Getting Buff...")
        ms.execute("/plottp 2")
        time.sleep(0.5)
        ms.player_press_sneak(True)
        time.sleep(0.5)
        ms.player_press_sneak(False)
        time.sleep(0.5)
        if USE_BUSH_ANCHOR:
            # plottp 2 มาถึงจะหันหลังให้ NPC ถอยไปจนชนพุ่มหญ้า จะได้ตำแหน่งที่แน่นอน
            if not _back_until_blocked():
                ms.echo("⚠️ Backward walk timed out (never hit the bush), continuing anyway.")
            time.sleep(0.5)

        # sneak ค้างไว้จนรับบัฟเสร็จ
        ms.player_press_sneak(True)
        time.sleep(0.2)

        if not _walk_to(STAND_X, STAND_Z):
            ms.echo("⚠️ Could not reach NPC position, aborting buff.")
            return False
        time.sleep(0.3)

        _look_at(NPC_X, NPC_Y + 1.0, NPC_Z)
        time.sleep(0.3)

        ms.player_inventory_select_slot(0)
        time.sleep(0.1)
        ms.player_press_use(True)
        time.sleep(0.1)
        ms.player_press_use(False)
        time.sleep(2)
        lib_inv.pickup(BUFF_MENU_SLOT)
        time.sleep(0.5)
        lib_inv.close()
        return True
    except Exception as e:
        ms.echo(f"❌ Buff error: {e}")
        return False
    finally:
        _release_keys()
