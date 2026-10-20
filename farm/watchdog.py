# -*- coding: utf-8 -*-
"""
watchdog.py — ตรวจว่าบอทค้าง: ขณะฟาร์มแต่ตำแหน่งไม่ขยับนานเกินกำหนด
กู้คืนด้วย: ปล่อยปุ่ม → /warp garden → สั่งให้เริ่มรอบใหม่ (state.watchdog_triggered)
"""

import math
import threading
import time

from system.lib import minescript as ms
from farm.config import WATCHDOG_ENABLED, WATCHDOG_STUCK_SECONDS, INPUT_MONITOR_ENABLED
from farm.utils import cecho, WARN, ERROR
from farm import tab_bridge
from farm.movement import release_all_keys
from farm import sensors
import farm.state as state

_started = False


def _active() -> bool:
    return (
        state.is_running
        and not state.paused
        and not state.changing_outfit
        and state.mode == state.Mode.FARMING
    )


def _check_input(last):
    """บันทึก/เตือนเมื่อสถานะเมาส์หรือหน้าต่างเกมเปลี่ยนระหว่างฟาร์ม (สาเหตุที่คลิกซ้ายไม่ทำงาน)"""
    cur = tab_bridge.input_state()
    if cur != last:
        grab, active = cur
        if grab is False or active is False:
            cecho(f"[Input] mouse_grabbed={grab} window_active={active} — คลิกซ้ายอาจไม่ทำงาน คลิกที่หน้าต่างเกมเพื่อคืนการควบคุม", ERROR)
        elif last is not None and (last[0] is False or last[1] is False):
            cecho(f"[Input] back to normal (mouse_grabbed={grab} window_active={active})", WARN)
    return cur


def _loop():
    last_pos = None
    last_move = time.time()
    last_input = None
    while True:
        time.sleep(1.0)
        try:
            now = time.time()
            if INPUT_MONITOR_ENABLED and state.is_running and state.mode == state.Mode.FARMING:
                last_input = _check_input(last_input)
            if not _active():
                last_pos, last_move = None, now
                continue
            pos = sensors.position()
            if last_pos is None or math.dist(pos, last_pos) > 0.05:
                last_pos, last_move = pos, now
                continue
            if now - last_move >= WATCHDOG_STUCK_SECONDS:
                cecho(
                    f"[Watchdog] No movement for {int(now - last_move)}s! Recovering...", WARN
                )
                release_all_keys()
                state.expect_teleport(6.0)
                ms.execute("/warp garden")
                state.watchdog_triggered = True
                last_pos, last_move = None, time.time()
        except Exception:
            pass


def start() -> None:
    global _started
    if _started or not WATCHDOG_ENABLED:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True).start()
