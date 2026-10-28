# -*- coding: utf-8 -*-
"""
movement.py — การเคลื่อนที่ กล้อง และการบิน
"""

import math
import time

from system.lib import minescript as ms
from farm.utils import cecho, SUCCESS, WARN, ERROR, DETAIL, GOLD, AQUA
import farm.state as state
from farm.config import FLY_BACKOFF_SECONDS


# ============================================================
# MATH HELPERS
# ============================================================


def _sqrt(x):
    return math.sqrt(x)


def _degrees(r):
    return math.degrees(r)


def _atan2(y, x):
    return math.atan2(y, x)


# ============================================================
# BASIC MOVEMENT
# ============================================================


def stop_all_movement():
    """หยุดทุกอย่างรวมถึง attack"""
    ms.player_press_left(False)
    ms.player_press_right(False)
    ms.player_press_forward(False)
    ms.player_press_backward(False)
    ms.player_press_attack(False)


def stop_movement_only():
    """หยุดเดิน แต่ยังค้าง attack"""
    ms.player_press_left(False)
    ms.player_press_right(False)
    ms.player_press_forward(False)
    ms.player_press_backward(False)


def release_all_keys():
    """ปล่อยทุกปุ่ม"""
    for fn in [
        ms.player_press_forward,
        ms.player_press_left,
        ms.player_press_right,
        ms.player_press_use,
        ms.player_press_attack,
        ms.player_press_jump,
        ms.player_press_sneak,
        ms.player_press_backward,
    ]:
        fn(False)


def hold_movement(direction: str, hold_forward: bool = False):
    """กดปุ่มเดินของทิศนี้ซ้ำ (ไม่ปล่อยก่อน) ใช้ยืนยันสถานะปุ่มระหว่างเดิน"""
    if hold_forward:
        ms.player_press_forward(True)
    key_map = {
        "left": ms.player_press_left,
        "right": ms.player_press_right,
        "forward": ms.player_press_forward,
        "backward": ms.player_press_backward,
    }
    if direction in key_map:
        key_map[direction](True)


def start_movement(direction: str, hold_forward: bool = False):
    """เริ่มเดินไปทิศทางที่กำหนด"""
    stop_movement_only()
    if hold_forward:
        ms.player_press_forward(True)
    key_map = {
        "left": ms.player_press_left,
        "right": ms.player_press_right,
        "forward": ms.player_press_forward,
        "backward": ms.player_press_backward,
    }
    if direction in key_map:
        key_map[direction](True)


# ============================================================
# CAMERA
# ============================================================


EYE_HEIGHT = 1.62   # player_position() คือตำแหน่งเท้า ตาอยู่สูงกว่านี้


def _wrap_degrees(angle: float) -> float:
    """ทำให้มุมอยู่ในช่วง [-180, 180)"""
    return (angle + 180.0) % 360.0 - 180.0


def yaw_pitch_to(x: float, y: float, z: float) -> tuple:
    """yaw/pitch ที่ต้องหันเพื่อมองจากตาผู้เล่นไปยังจุด (x, y, z)"""
    p = ms.player_position()
    dx, dy, dz = x - p[0], y - (p[1] + EYE_HEIGHT), z - p[2]
    yaw = -_degrees(_atan2(dx, dz))
    pitch = -_degrees(_atan2(dy, _sqrt(dx * dx + dz * dz)))
    return yaw, pitch


def smooth_look_at(
    target_yaw: float, target_pitch: float, steps: int = 10, delay: float = 0.05
):
    """หมุนกล้องไปยัง yaw/pitch เป้าหมายแบบ smooth"""
    state.expect_teleport(steps * delay + 1.0)   # ไม่ให้ failsafe เข้าใจว่าถูกหันหัวบังคับ
    current_yaw, current_pitch = ms.player_orientation()

    # หมุนทางที่สั้นกว่าเสมอ: yaw ของเกมสะสมเกิน ±180 ได้ (เช่น 520) จึงต้อง wrap ที่ "ส่วนต่าง"
    # ไม่ใช่แค่ wrap เป้าหมาย ไม่งั้น 170 → -170 จะหมุนกลับ 340 องศาแทน 20
    yaw_delta = _wrap_degrees(target_yaw - current_yaw)
    target_pitch = max(-90.0, min(90.0, target_pitch))
    steps = max(1, steps)

    for i in range(steps + 1):
        t = i / steps
        smooth_t = t * t * (3.0 - 2.0 * t)
        ms.player_set_orientation(
            current_yaw + yaw_delta * smooth_t,
            current_pitch + (target_pitch - current_pitch) * smooth_t,
        )
        if i < steps:
            time.sleep(delay)


def smooth_look_at_pos(x: float, y: float, z: float, steps: int = 10, delay: float = 0.05):
    """หันไปมองจุด (x, y, z) แบบ smooth (บล็อกจนหันเสร็จ)"""
    yaw, pitch = yaw_pitch_to(x, y, z)
    smooth_look_at(yaw, pitch, steps=steps, delay=delay)


def step_look_at_pos(x: float, y: float, z: float, max_degrees: float) -> float:
    """หันเข้าหาจุด (x, y, z) ได้ไม่เกิน max_degrees ต่อครั้ง ไม่บล็อก (เรียกทุก tick ใน loop)
    คืนมุมที่ยังเหลือก่อนหันครั้งนี้ (องศา) ไว้เช็คว่าเล็งตรงหรือยัง"""
    target_yaw, target_pitch = yaw_pitch_to(x, y, z)
    yaw, pitch = ms.player_orientation()
    d_yaw = _wrap_degrees(target_yaw - yaw)
    d_pitch = target_pitch - pitch
    remaining = _sqrt(d_yaw * d_yaw + d_pitch * d_pitch)
    if remaining > max_degrees > 0:
        scale = max_degrees / remaining   # ย่อทั้งสองแกนเท่ากัน ให้กล้องไหลเป็นเส้นตรงไปหาเป้า
        d_yaw, d_pitch = d_yaw * scale, d_pitch * scale
    ms.player_set_orientation(yaw + d_yaw, max(-90.0, min(90.0, pitch + d_pitch)))
    return remaining


# ============================================================
# FLY
# ============================================================


def fly():
    """กระโดดสองครั้งเพื่อเข้า fly mode"""
    for _ in range(2):
        ms.player_press_jump(True)
        time.sleep(0.1)
        ms.player_press_jump(False)
        time.sleep(0.1)


def stop_fly():
    """กด sneak เพื่อลงจอด"""
    ms.player_press_sneak(True)
    time.sleep(3)
    ms.player_press_sneak(False)
    time.sleep(0.05)


def land_if_flying(timeout: float = 6.0):
    """กด sneak ค้างจนกว่า Y จะนิ่ง (ลงพื้นแล้ว) ถ้าอยู่บนพื้นอยู่แล้วจะออกเร็ว"""
    try:
        ms.player_press_sneak(True)
        deadline = time.time() + timeout
        last_y = ms.player_position()[1]
        stable_since = time.time()
        while time.time() < deadline:
            time.sleep(0.1)
            y = ms.player_position()[1]
            if abs(y - last_y) > 0.02:
                last_y = y
                stable_since = time.time()
            elif time.time() - stable_since >= 0.6:
                break
    finally:
        ms.player_press_sneak(False)
        time.sleep(0.1)


def fly_to_height(
    target_height: float,
    tolerance: float = 0.5,
    check_interval: float = 0.05,
    max_attempts: int = 3,
) -> bool:
    """บินขึ้นไปถึงความสูงที่กำหนด คืน True ถ้าสำเร็จ"""
    cecho(f"⬆️ Flying to height {target_height}...", AQUA)
    ms.player_press_attack(False)
    time.sleep(0.1)

    if ms.player_position()[1] >= target_height - tolerance:
        cecho("✅ Already at target height", SUCCESS)
        return True

    for attempt in range(1, max_attempts + 1):
        cecho(f"🚁 Fly attempt #{attempt}...", AQUA)

        ms.player_press_backward(True)
        time.sleep(FLY_BACKOFF_SECONDS)
        ms.player_press_backward(False)
        time.sleep(0.2)

        fly()
        time.sleep(0.3)

        y_before = ms.player_position()[1]
        ms.player_press_jump(True)
        time.sleep(0.5)

        if ms.player_position()[1] - y_before < 0.1:
            cecho("  ⚠️ Fly mode not working, retrying...", WARN)
            ms.player_press_jump(False)
            time.sleep(0.5)
            continue

        cecho("  ✅ Fly mode active! Ascending...", SUCCESS)
        deadline = time.time() + 10.0

        while state.is_running and time.time() < deadline:
            if ms.player_position()[1] >= target_height - tolerance:
                ms.player_press_jump(False)
                cecho("✅ Reached target height!", SUCCESS)
                return True
            ms.player_press_jump(True)
            time.sleep(check_interval)

        ms.player_press_jump(False)
        if ms.player_position()[1] >= target_height - tolerance:
            return True
        cecho(f"  ⚠️ Attempt #{attempt} failed", WARN)
        time.sleep(0.5)

    cecho(f"❌ Failed to reach target height after {max_attempts} attempts", ERROR)
    ms.player_press_jump(False)
    return False


def move_to_plot_center(
    target_x: float, target_z: float, tolerance: float = 1.5
) -> bool:
    """เดินไปยัง (target_x, target_z) คืน True เมื่อถึง"""
    while state.is_running:
        pos = ms.player_position()
        dx, dz = target_x - pos[0], target_z - pos[2]
        if _sqrt(dx**2 + dz**2) <= tolerance:
            ms.player_press_forward(False)
            return True
        ms.player_set_orientation(-_degrees(_atan2(dx, dz)), 0)
        ms.player_press_forward(True)
        time.sleep(0.02)
    return False


def warp_to_garden_and_land():
    """Teleport ไป garden แล้วลงจอด"""
    state.expect_teleport(6.0)
    ms.execute("/warp garden")
    time.sleep(1)
    ms.player_press_sneak(True)
    time.sleep(0.5)
    ms.player_press_sneak(False)


def fly_to_start_position(profile: dict):
    """บินกลับไปจุดเริ่มต้นที่กำหนดใน profile"""
    sp = profile["start_pos"]
    TARGET_X, TARGET_Z = sp["x"], sp["z"]
    TARGET_YAW, TARGET_PITCH = sp["yaw"], sp["pitch"]
    TOLERANCE = 2.0
    FLY_TIMEOUT = 15.0

    cecho("🚁 Flying to starting position...", AQUA)
    state.flying_to_start = True

    try:
        smooth_look_at(TARGET_YAW, TARGET_PITCH, steps=10, delay=0.03)
        time.sleep(0.3)

        fly_success = False
        for attempt in range(1, 4):
            cecho(f"🚁 Fly attempt #{attempt}...", AQUA)
            ms.player_press_backward(True)
            time.sleep(0.3)
            ms.player_press_backward(False)
            time.sleep(0.2)
            fly()
            time.sleep(0.3)

            y_before = ms.player_position()[1]
            ms.player_press_jump(True)
            time.sleep(0.5)

            if ms.player_position()[1] - y_before > 0.1:
                cecho("  ✅ Fly mode active!", SUCCESS)
                fly_success = True
                break

            cecho("  ⚠️ Fly mode failed, retrying...", WARN)
            ms.player_press_jump(False)
            time.sleep(0.5)

        if not fly_success:
            cecho("❌ Cannot enter fly mode! Forcing teleport...", ERROR)
            warp_to_garden_and_land()
            return

        cecho(f"➡️ Flying to ({TARGET_X}, {TARGET_Z})...", AQUA)
        ms.player_press_forward(True)
        deadline = time.time() + FLY_TIMEOUT
        last_dist = 999999.0
        stuck_timer = 0.0

        while state.is_running and time.time() < deadline:
            pos = ms.player_position()
            dx, dz = TARGET_X - pos[0], TARGET_Z - pos[2]
            dist = _sqrt(dx**2 + dz**2)
            ms.player_set_orientation(-_degrees(_atan2(dx, dz)), TARGET_PITCH)

            if dist <= TOLERANCE:
                cecho("✅ Reached starting position!", SUCCESS)
                break

            if abs(dist - last_dist) < 0.1:
                stuck_timer += 0.1
                if stuck_timer > 3.0:
                    cecho("⚠️ Stuck! Attempting to unstuck...", WARN)
                    ms.player_press_forward(False)
                    time.sleep(0.2)
                    ms.player_press_backward(True)
                    time.sleep(0.5)
                    ms.player_press_backward(False)
                    ms.player_press_jump(True)
                    time.sleep(0.5)
                    ms.player_press_jump(False)
                    time.sleep(0.2)
                    ms.player_press_forward(True)
                    stuck_timer = 0.0
            else:
                stuck_timer = 0.0

            last_dist = dist
            time.sleep(0.1)
        else:
            if time.time() >= deadline:
                cecho("⏱️ Flying timeout! Forcing teleport...", ERROR)
                warp_to_garden_and_land()
                return

        ms.player_press_forward(False)
        ms.player_press_jump(False)
        time.sleep(0.2)
        cecho("⬇️ Descending to ground...", AQUA)
        stop_fly()
        time.sleep(0.5)
        cecho("✅ Ready to start new round!", SUCCESS)

    except Exception as e:
        cecho(f"❌ Error in fly_to_start: {e}", ERROR)
        warp_to_garden_and_land()

    finally:
        release_all_keys()
        state.flying_to_start = False
