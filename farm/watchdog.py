# -*- coding: utf-8 -*-
"""
watchdog.py — ตรวจว่าบอทค้าง: ขณะฟาร์มแต่ตำแหน่งไม่ขยับนานเกินกำหนด
กู้คืนด้วย: ปล่อยปุ่ม → /warp garden → สั่งให้เริ่มรอบใหม่ (state.watchdog_triggered)
"""

import math
import threading
import time

from system.lib import minescript as ms
from farm.config import WATCHDOG_ENABLED, WATCHDOG_STUCK_SECONDS
from farm.utils import cecho, WARN
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


def _loop():
    last_pos = None
    last_move = time.time()
    while True:
        time.sleep(1.0)
        try:
            now = time.time()
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
