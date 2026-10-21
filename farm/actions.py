# -*- coding: utf-8 -*-
"""
actions.py — ขั้นตอนมาตรฐานที่ "ปิดงาน" หลัง action สำคัญ ๆ (กำจัด pest, รับบัฟ/สเปรย์, ขายของ, กู้คืน)

ปัญหาที่แก้: action พวกนั้นทิ้งสถานะค้างไว้ เช่น ยังถือ Vacuum/AOTV (คลิกซ้ายตอนถือไอเทมนั้นไม่ได้เก็บเกี่ยว),
ปุ่มบางปุ่มยังกดค้าง, GUI ยังไม่ปิด, หรือกล้องไม่ได้หันกลับตามค่าของฟาร์ม
จึงรวมเป็นฟังก์ชันเดียว เรียกหลังจบ action ทุกครั้ง ก่อนกลับไปฟาร์ม
"""

import time

from system.lib import minescript as ms
from system.lib import lib_inv
from farm.config import FARM_TOOL_SLOT, RESTORE_LOOK_STEPS, RESTORE_SETTLE
from farm.inventory import wait_for_no_screen
from farm.movement import release_all_keys, smooth_look_at
from farm.utils import cecho, DETAIL
import farm.state as state


def restore_farm_state(profile: dict, reason: str = "") -> None:
    """เคลียร์ทุกอย่างให้อยู่ในสถานะพร้อมฟาร์ม:
    ปล่อยทุกปุ่ม → ปิด GUI ที่ค้าง → ถือเครื่องมือฟาร์ม → หันกล้องตาม profile → กดคลิกซ้ายค้าง
    ต้องเรียกในขณะที่ไม่มีงานอื่นแย่งควบคุม (main loop เท่านั้น)"""
    release_all_keys()

    if ms.screen_name() is not None:
        lib_inv.close()
        wait_for_no_screen(timeout=2.0)
        time.sleep(RESTORE_SETTLE)   # ให้เกมรีเซ็ตสถานะปุ่มหลังปิด GUI เสร็จก่อน

    ms.player_inventory_select_slot(FARM_TOOL_SLOT)
    time.sleep(RESTORE_SETTLE)

    smooth_look_at(profile["yaw"], profile["pitch"], steps=RESTORE_LOOK_STEPS, delay=0.02)
    time.sleep(RESTORE_SETTLE)

    ms.player_press_attack(True)    # ขั้นสุดท้ายเสมอ หลังทุกอย่างนิ่งแล้ว
    if reason:
        cecho(f"🧹 Farm state restored ({reason})", DETAIL)
