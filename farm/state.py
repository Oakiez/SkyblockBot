# -*- coding: utf-8 -*-
"""
state.py — Global state ทั้งหมดของ bot

import แล้วใช้ได้เลย เช่น:
    from farm.state import is_running, set_flag
"""

import queue
import threading
from contextlib import contextmanager

# ============================================================
# RUNTIME FLAGS
# ============================================================

is_running:       bool = False
paused:           bool = False
round_count:      int  = 0
current_profile:  str  = None
start_time:       float = 0

# Outfit
changing_outfit:    bool = False
current_outfit_slot: int = None

# Pest
last_pest_spawn_time: float = 0
last_cooldown_event_time: float = 0
pest_alive_hint: int = 0          # จำนวน pest ที่รู้จากข้อความ spawn (รวมสะสมจนกว่าจะกำจัดเสร็จ)
pending_pest_plots: set = set()   # plot ที่รู้จากข้อความ spawn ว่ามี pest ต้องไปกำจัด
last_spawn_info: tuple = None   # (จำนวน, plot) จากข้อความ "N Pest have spawned in Plot - X"
cycling_pests:        bool  = False

# Misc
last_buff_time: float = 0    # เวลา (epoch) ที่รับบัฟ Phillip ล่าสุด 0 = ยังไม่เคย
last_spray_time: float = 0   # เวลา (epoch) ที่สเปรย์ล่าสุด 0 = ยังไม่เคย
spraying_plots: bool = False
flying_to_start: bool = False

# Recovery
restart_detected: bool = False
limbo_detected:   bool = False

# ============================================================
# THREAD SAFETY
# ============================================================

_lock = threading.Lock()


def set_flag(name: str, value) -> None:
    """Thread-safe setter สำหรับ global flags"""
    with _lock:
        globals()[name] = value


def get_flag(name: str):
    """Thread-safe getter สำหรับ global flags"""
    with _lock:
        return globals()[name]


# ============================================================
# MODE + EVENTS (state machine แบบเบา)
# ============================================================
# mode บอกว่าบอทกำลังทำอะไรอยู่ ใช้ให้ watchdog/ส่วนอื่นตัดสินใจ
# events เป็นคิวที่ chat thread ส่งเข้ามา ให้ main loop เป็นคนจัดการเอง (ไม่แย่งกัน)


class Mode:
    IDLE = "idle"
    FARMING = "farming"
    SWITCHING = "switching"
    PEST = "pest"
    SPRAY = "spray"
    RECOVERY = "recovery"


mode: str = Mode.IDLE
watchdog_triggered: bool = False
events: "queue.Queue[str]" = queue.Queue()


def post_event(name: str) -> None:
    events.put(name)


def poll_event():
    try:
        return events.get_nowait()
    except queue.Empty:
        return None


def clear_events() -> None:
    while poll_event() is not None:
        pass


@contextmanager
def in_mode(new_mode: str):
    """เปลี่ยน mode ชั่วคราว แล้วคืนค่าเดิมเมื่อจบ"""
    global mode
    prev = mode
    mode = new_mode
    try:
        yield
    finally:
        mode = prev

