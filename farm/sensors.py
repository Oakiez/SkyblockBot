# -*- coding: utf-8 -*-
"""
sensors.py — Poller กลาง อ่านตำแหน่ง/pest ครั้งเดียวแล้วเก็บ cache
ส่วนอื่นอ่านจาก cache ไม่ต้องเรียก API เอง (ถ้า cache เก่าเกินจะอ่านตรงให้)
"""

import threading
import time

from system.lib import minescript as ms
from farm.config import SENSOR_POLL_INTERVAL, SENSOR_MAX_AGE, PEST_CHECK_INTERVAL
import farm.state as state

_pos = None
_pos_t = 0.0
_pest = (0, [])
_pest_t = 0.0
_started = False


def _read_pests():
    from farm.pest import get_pest_info  # import ตอนใช้ ป้องกัน circular import
    return get_pest_info()


def _pos_loop():
    global _pos, _pos_t
    while True:
        try:
            _pos = tuple(ms.player_position())
            _pos_t = time.time()
        except Exception:
            pass
        time.sleep(SENSOR_POLL_INTERVAL)


def _pest_loop():
    """อ่าน tablist เป็น thread แยก (ช้า/อาจ error ได้) ไม่ให้กระทบการอ่านตำแหน่ง"""
    global _pest, _pest_t
    while True:
        try:
            if state.is_running and state.mode in (state.Mode.IDLE, state.Mode.FARMING):
                _pest = _read_pests()
                _pest_t = time.time()
        except Exception:
            pass
        time.sleep(PEST_CHECK_INTERVAL)


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    from farm import tab_bridge
    tab_bridge.start()   # อ่าน tablist ด้วย Pyjinn ในเกม (เร็วกว่า JavaClass จาก Python หลายสิบเท่า)
    threading.Thread(target=_pos_loop, daemon=True).start()
    threading.Thread(target=_pest_loop, daemon=True).start()


def position():
    """ตำแหน่งผู้เล่นล่าสุด (cache ถ้าสด ไม่งั้นอ่านตรง)"""
    if _pos is not None and time.time() - _pos_t <= SENSOR_MAX_AGE:
        return _pos
    return tuple(ms.player_position())


def pest_info(max_age: float = None):
    """(count, plots) จาก cache ถ้าสด ไม่งั้นอ่านตรง"""
    global _pest, _pest_t
    max_age = PEST_CHECK_INTERVAL * 1.5 if max_age is None else max_age
    if time.time() - _pest_t <= max_age:
        return _pest
    _pest = _read_pests()
    _pest_t = time.time()
    return _pest


def pest_info_wait(timeout: float = 2.0):
    """รออ่านค่า pest ใหม่จาก poller ไม่เกิน timeout (ไม่เรียก tablist ซ้อนในนี้เอง)
    คืน (count, plots) หรือ (0, []) ถ้าไม่ทัน เพื่อไม่ให้ตอนกดเริ่มค้างรอ"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _pest_t >= t0:
            return _pest
        time.sleep(0.05)
    return (0, [])


def cached_pests():
    """(count, plots) ล่าสุดที่ poller อ่านได้ + เวลา (epoch) ที่อ่าน — ไม่เรียก tablist เอง ไม่บล็อก"""
    return _pest, _pest_t

