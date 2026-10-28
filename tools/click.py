# -*- coding: utf-8 -*-
import queue
import time

import system.lib.minescript as ms
from system.lib.lib_inv import pickup

TOGGLE_KEY = 93  # ] key: start / pause / resume
CLICK_SLOT = 0   # ช่องที่ต้องการคลิก
CLICK_DELAY = 0.3

event_queue = ms.EventQueue()
event_queue.register_key_listener()


def _toggle_pressed():
    """Return True if the toggle key was pressed since the last check."""
    try:
        event = event_queue.get(block=False)
    except queue.Empty:
        return False
    return (
        event.type == ms.EventType.KEY
        and event.key == TOGGLE_KEY
        and event.action == 1
    )


def wait_for_toggle():
    """Block until the toggle key is pressed."""
    while True:
        if _toggle_pressed():
            return
        time.sleep(0.02)


def wait_for_screen(timeout=3.0):
    """Wait until any screen is open. Returns True if it opened in time."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ms.screen_name() is not None:
            return True
        time.sleep(0.05)
    return False


def ensure_stash_open():
    """Open the material stash if no screen is open. Returns True when ready."""
    if ms.screen_name() is not None:
        return True
    ms.execute("/viewstash material")
    if not wait_for_screen(timeout=3.0):
        ms.echo("Stash screen did not open, retrying...")
        return False
    time.sleep(0.3)  # รอให้ไอเทมโหลดในหน้าจอ
    return True


ms.echo("Press ] to start.")
wait_for_toggle()
ms.echo("Started! Press ] to pause.")

while True:
    if _toggle_pressed():
        ms.echo("Paused. Press ] to resume.")
        wait_for_toggle()
        ms.echo("Resumed!")

    # เปลี่ยนตรงที่คลิก
    if ensure_stash_open():
        pickup(CLICK_SLOT)
        time.sleep(CLICK_DELAY)