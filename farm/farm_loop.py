# -*- coding: utf-8 -*-
"""
farm_loop.py — Harvest loop และ main farm loop
"""

import threading
import time

from system.lib import minescript as ms
from system.lib.minescript import EventType
from farm.config import (
    PAUSE_KEY, START_STOP_KEY,
    STUCK_CHECK_INTERVAL, STUCK_CHECK_THRESHOLD, STUCK_CHECK_COUNT, STEP_END_DELAY,
    AUTO_UNPAUSE_SECONDS, AMOUNT_OF_PESTS, SCREENSHOT_INTERVAL,
    PEST_CHECK_INTERVAL, OUTFIT_WAIT_TIMEOUT, DEBUG_TIMING, CHATLOG_ENABLED, ATTACK_REASSERT_INTERVAL, SPRAY_EVERY_SECONDS,
    BUFF_EVERY_SECONDS, BUFF_RETRY_SECONDS,
)
from farm.profiles import load_profile
from farm.buff import get_buff
from farm.utils import cecho, SUCCESS, WARN, ERROR, DETAIL, GOLD, AQUA, wait_until
from farm.movement import (
    stop_all_movement, stop_movement_only, start_movement,
    smooth_look_at, fly_to_start_position, warp_to_garden_and_land, land_if_flying,
    release_all_keys,
)
from farm.inventory import switch_to_farming_outfit, switch_to_pest_outfit, get_inventory_hash, sell_items_to_npc
from farm.pest import get_pest_info, should_stop_for_pests, pest_cycle, spray_plots
from farm.recovery import (
    check_for_limbo_message, check_for_restart_message,
    check_for_pest_spawn_message, check_for_pest_cooldown_message,
    check_server_change,
)
from farm import sensors, watchdog, metrics, chatlog, failsafe
import farm.state as state



# ============================================================
# SESSION SUMMARY
# ============================================================

def _print_session_summary(profile_name: str):
    """แสดงสรุป session เมื่อหยุด farm"""
    if state.start_time == 0:
        return

    elapsed   = int(time.time() - state.start_time)
    minutes   = elapsed // 60
    seconds   = elapsed % 60
    hours     = minutes // 60
    mins_left = minutes % 60

    cecho("", DETAIL)
    cecho("╔══════════ Session Summary ══════════╗", GOLD)
    cecho(f"  Profile  : {profile_name}", AQUA)
    cecho(f"  Rounds   : {state.round_count}", AQUA)
    if hours > 0:
        cecho(f"  Time     : {hours}h {mins_left}m {seconds}s", AQUA)
    else:
        cecho(f"  Time     : {minutes}m {seconds}s", AQUA)
    if elapsed > 0 and state.round_count > 0:
        rph = round(state.round_count / (elapsed / 3600), 1)
        cecho(f"  Speed    : {rph} rounds/hr", AQUA)
    for line in metrics.summary_lines():
        cecho(f"  {line}", AQUA)
    cecho("╚═════════════════════════════════════╝", GOLD)
    cecho("", DETAIL)

# ============================================================
# PAUSE
# ============================================================

def check_pause() -> float:
    """Block จนกว่าจะ unpause คืน วินาทีที่ pause ไป"""
    if not state.paused:
        return 0

    cecho("⏸️ Farm paused. Waiting to resume...", WARN)
    stop_all_movement()
    pause_start = time.time()
    last_log = 0

    while state.paused:
        elapsed = time.time() - pause_start
        if elapsed >= AUTO_UNPAUSE_SECONDS:
            cecho("⏯️ Auto-unpausing farm...", WARN)
            state.paused = False
            break
        if int(elapsed) % 5 == 0 and int(elapsed) != last_log and int(elapsed) > 0:
            remaining = AUTO_UNPAUSE_SECONDS - int(elapsed)
            cecho(f"⏳ Auto-unpause in {remaining}s...", DETAIL)
            last_log = int(elapsed)
        time.sleep(0.1)

    pause_duration = time.time() - pause_start
    cecho("▶️ Resuming farm...", SUCCESS)
    ms.player_inventory_select_slot(0)
    ms.player_press_attack(True)
    time.sleep(0.2)
    cecho("✅ Resume complete.", SUCCESS)
    return pause_duration


# ============================================================
# INITIALIZE
# ============================================================

def initialize_farm(profile: dict):
    cecho("🚀 Initializing farm...", GOLD)
    land_if_flying()
    state.current_outfit_slot = None  # บังคับสลับใหม่เสมอ เผื่อ loadout จริงต่างจากที่จำไว้
    # ถ้า pest เกิดค้างอยู่แล้วตอนกดเริ่ม (Alive > 0) ใช้ชุดฟาร์ม ไม่งั้นใช้ชุด pest (รอ pest เกิด)
    alive, _ = sensors.pest_info_wait(timeout=2.0)
    if alive > 0:
        cecho(f"🐛 {alive} pest(s) already alive → Farm loadout", WARN)
        switch_to_farming_outfit()
    else:
        switch_to_pest_outfit()
    smooth_look_at(profile["yaw"], profile["pitch"], steps=15, delay=0.03)
    time.sleep(0.5)
    cecho("📍 Setting spawn...", DETAIL)
    ms.execute("/setspawnlocation")
    time.sleep(0.1)
    ms.player_inventory_select_slot(0)
    time.sleep(0.1)
    for i in range(3, 0, -1):
        cecho(f"🚜 Starting in {i}...", GOLD)
        time.sleep(1)
    # ปล่อยแล้วกดซ้ายใหม่ ต้องเป็นขั้นสุดท้าย หลังเลือก loadout และปิดหน้าจอครบแล้ว
    ms.player_press_attack(False)
    time.sleep(0.1)
    ms.player_inventory_select_slot(0)
    time.sleep(0.1)
    ms.player_press_attack(True)
    time.sleep(0.1)
    state.start_time = time.time()
    cecho("✅ Ready! (left click held)", SUCCESS)


# ============================================================
# HARVEST DIRECTION
# ============================================================

def _interrupt_for_pests() -> str:
    """หยุดฟาร์มทันทีเพื่อไปกำจัด pest (รอเฉพาะถ้ากำลังสลับ loadout อยู่จริง)"""
    stop_movement_only()
    if state.changing_outfit:
        cecho("⚠ Waiting for loadout switch to finish...", WARN)
        wait_until(lambda: not state.changing_outfit, OUTFIT_WAIT_TIMEOUT, 0.05)
    cecho("⚠ Pests! Interrupting farm...", WARN)
    ms.execute("/setspawn")
    return "PEST_INTERRUPT"


def _pests_alive_estimate() -> int:
    """จำนวน pest ที่คาดว่ามี: ค่ามากสุดระหว่างข้อความ spawn กับ cache ของ tablist (ไม่บล็อก)"""
    (count, _), _t = sensors.cached_pests()
    return max(state.pest_alive_hint, count)


def _handle_event(ev: str) -> None:
    """จัดการ event จาก chat (รันใน main loop เท่านั้น ไม่แย่งกับ thread อื่น)"""
    if ev == "PEST_SPAWNED":
        switch_to_farming_outfit()
    elif ev == "PEST_COOLDOWN":
        switch_to_pest_outfit()


def harvest_direction(direction_data: dict, movement_num: int, profile: dict) -> str | None:
    """
    เดินทิศทางเดียวจนชนกำแพง
    คืน "PEST_INTERRUPT" ถ้า pest เกิน threshold ระหว่างเดิน
    """
    direction = direction_data["direction"]
    arrow = {"left": "←", "right": "→", "forward": "↑", "backward": "↓"}.get(direction, "→")
    cecho(f"🚜 Move {movement_num}: {direction_data['name']} {arrow}", GOLD)

    last_inventory  = None   # คำนวณเมื่อจำเป็นเท่านั้น (ดู stuck check)
    last_inv_change = time.time()

    pos = ms.player_position()
    last_x, last_z = pos[0], pos[2]
    stuck_counter = 0

    step_started = time.time()
    state.mode = state.Mode.FARMING
    stop_movement_only()
    ms.player_press_attack(True)
    start_movement(direction, hold_forward=profile.get("hold_forward", False))

    last_check      = time.time()
    last_pest_check = time.time()
    last_attack     = time.time()
    was_changing    = False

    while state.is_running:
        now = time.time()

        # --- Watchdog สั่งให้เริ่มรอบใหม่ ---
        if state.watchdog_triggered:
            stop_movement_only()
            return "WATCHDOG"

        # --- Pest check ---
        if now - last_pest_check >= PEST_CHECK_INTERVAL and not state.spraying_plots and not state.flying_to_start:
            last_pest_check = now
            count, _ = sensors.pest_info()
            if count >= AMOUNT_OF_PESTS:
                return _interrupt_for_pests()

        # --- event จาก chat (สลับ loadout ฯลฯ) จัดการที่นี่ที่เดียว ---
        ev = state.poll_event()
        if ev:
            # pest เกิดแล้วถึงเกณฑ์ → หยุดและไปกำจัดทันที ไม่ต้องรอสลับชุด/รอ tablist
            if ev == "PEST_SPAWNED" and _pests_alive_estimate() >= AMOUNT_OF_PESTS:
                return _interrupt_for_pests()
            _handle_event(ev)
            was_changing = True   # ให้ resume block ด้านล่างกดเดิน/คลิกใหม่
            continue

        # --- รอ outfit change ---
        if state.changing_outfit:
            was_changing = True
            time.sleep(0.1)
            last_inv_change = time.time()
            continue

        # --- resume หลัง outfit change ---
        if was_changing:
            cecho("▶️ Resuming after outfit change...", SUCCESS)
            ms.player_press_attack(True)
            time.sleep(0.1)
            start_movement(direction, hold_forward=profile.get("hold_forward", False))
            time.sleep(0.1)
            was_changing = False
            try:
                pos = ms.player_position()
                last_x, last_z = pos[0], pos[2]
            except:
                pass
            stuck_counter   = 0
            last_check      = now
            last_inv_change = now
            last_inventory  = None

        # --- กดคลิกซ้ายค้างซ้ำเป็นระยะ: สถานะปุ่มอาจหลุดเงียบ ๆ (เช่นหลังปิด GUI) แล้วบอทไม่รู้ ---
        if now - last_attack >= ATTACK_REASSERT_INTERVAL and not state.paused:
            ms.player_press_attack(True)
            last_attack = now

        # --- pause ---
        pause_duration = check_pause()
        if pause_duration > 0:
            last_inv_change += pause_duration
            ms.player_press_attack(True)
            time.sleep(0.1)
            start_movement(direction, hold_forward=profile.get("hold_forward", False))
            stuck_counter = 0
            last_check = now

        # --- stuck / position check ---
        if now - last_check >= STUCK_CHECK_INTERVAL:
            last_check = now

            pos = sensors.position()
            cx, cz = pos[0], pos[2]
            if abs(cx - last_x) + abs(cz - last_z) < STUCK_CHECK_THRESHOLD:
                # ดูเหมือนติด → ค่อยเช็ค inventory (หนัก) ว่ามีไอเทมเข้ามาไหม
                # ถ้ามี แปลว่ายังเก็บเกี่ยวอยู่ ไม่ถือว่าติด
                current_inventory = get_inventory_hash()
                if last_inventory is not None and current_inventory != last_inventory:
                    last_inv_change = now
                    stuck_counter   = 0
                else:
                    stuck_counter += 1
                last_inventory = current_inventory
                if stuck_counter >= STUCK_CHECK_COUNT:
                    break
            else:
                stuck_counter  = 0
                last_inventory = None
            last_x, last_z = cx, cz

        time.sleep(0.02)

    stop_movement_only()
    time.sleep(STEP_END_DELAY)
    metrics.record("step", time.time() - step_started, str(movement_num))
    if DEBUG_TIMING:
        cecho(f"⏱ step {movement_num} took {time.time() - step_started:.2f}s", DETAIL)


# ============================================================
# MAIN LOOP
# ============================================================

def _buff_due() -> bool:
    """ถึงเวลารับบัฟหรือยัง (บัฟ 30 นาที กดซ้อนไม่ได้ จึงรอให้ครบก่อน)"""
    return BUFF_EVERY_SECONDS > 0 and time.time() - state.last_buff_time >= BUFF_EVERY_SECONDS


def _buff_and_spray(profile: dict) -> None:
    """ท้ายรอบ: รับบัฟ (ทุก ~30 นาที) และ/หรือ spray (ทุก ~55 นาที) ตามเวลาที่ครบ แยกกัน"""
    do_buff = _buff_due()
    do_spray = _spray_due(profile)

    if not (do_buff or do_spray):
        buff_left = max(0, BUFF_EVERY_SECONDS - (time.time() - state.last_buff_time)) / 60
        spray_left = max(0, SPRAY_EVERY_SECONDS - (time.time() - state.last_spray_time)) / 60
        cecho(
            f"⏭️ Round {state.round_count} - next buff in {buff_left:.0f}m, next spray in {spray_left:.0f}m",
            DETAIL,
        )
        return

    ms.player_press_attack(False)
    state.spraying_plots = True   # กัน pest check/trigger อื่นแทรกระหว่างทำ
    try:
        with state.in_mode(state.Mode.SPRAY):
            if do_buff:
                cecho("📦 Getting Buff...", GOLD)
                if get_buff():
                    state.last_buff_time = time.time()
                else:
                    cecho("⚠️ Buff failed, will retry soon.", WARN)
                    state.last_buff_time = time.time() - BUFF_EVERY_SECONDS + BUFF_RETRY_SECONDS

            if do_spray:
                cecho(f"🌿 Round {state.round_count} - Spraying!", SUCCESS)
                spray_plots(profile)      # วาร์ปกลับ garden เองตอนจบ
                state.last_spray_time = time.time()
            else:
                warp_to_garden_and_land()  # รับบัฟอย่างเดียว ต้องกลับมาจุดฟาร์มเอง
    finally:
        state.spraying_plots = False
    time.sleep(0.5)


def _spray_due(profile: dict) -> bool:
    """ถึงเวลาสเปรย์หรือยัง: ตามเวลาจริง (SPRAY_EVERY_SECONDS) หรือนับรอบ (spray_interval)"""
    if not profile.get("spray_plots"):
        return False
    if SPRAY_EVERY_SECONDS > 0:
        return time.time() - state.last_spray_time >= SPRAY_EVERY_SECONDS
    interval = profile.get("spray_interval", 0)
    return interval > 0 and state.round_count % interval == 0


def auto_farm(profile_name: str):
    profile = load_profile(profile_name)
    if not profile:
        return

    state.current_profile = profile_name
    cecho(f"🚜 Starting: {profile['name']}", GOLD)

    initialized = False

    event_queue = ms.EventQueue()
    event_queue.register_key_listener()
    event_queue.register_chat_listener()
    event_queue.register_world_listener()  # ป้องกัน script ตายเงียบเมื่อ disconnect

    def event_loop():
        while True:
            try:
                event = event_queue.get(block=False)
                if event.type == "key" and event.action == 1:
                    if event.key == START_STOP_KEY:
                        state.is_running = not state.is_running
                        if state.is_running:
                            cecho("▶ Farm Started!", SUCCESS)
                        else:
                            cecho("⏹ Farm Stopped", ERROR)
                            stop_all_movement()
                            ms.execute("/setspawn")
                    elif event.key == PAUSE_KEY and state.is_running:
                        state.paused = not state.paused
                elif event.type == "chat" and not chatlog.is_active():
                    check_for_restart_message(event.message)
                    check_for_limbo_message(event.message)
                    check_for_pest_cooldown_message(event.message)
                    check_for_pest_spawn_message(event.message)
                elif event.type == EventType.WORLD:
                    if not event.connected:
                        cecho("🔌 Disconnected from world! Stopping farm...", ERROR)
                        state.is_running = False
                        stop_all_movement()
            except:
                pass
            time.sleep(0.05)

    threading.Thread(target=event_loop, daemon=True).start()
    sensors.start()
    watchdog.start()
    failsafe.start()
    if CHATLOG_ENABLED:
        ok = chatlog.start([
            check_for_restart_message, check_for_limbo_message,
            check_for_pest_cooldown_message, check_for_pest_spawn_message,
        ])
        cecho("📜 Chat log reader: " + ("on" if ok else "OFF (log not found, using chat events)"), DETAIL)

    try:
        while True:
            if not state.is_running:
                initialized = False
                state.mode = state.Mode.IDLE
                time.sleep(0.1)
                continue

            if not initialized:
                initialize_farm(profile)
                initialized = True

            state.round_count += 1
            round_started = time.time()
            check_pause()

            cecho("┌───────────────────────────────", DETAIL)

            pattern_pos = 0
            while pattern_pos < len(profile["pattern"]):
                if not state.is_running:
                    break

                step = profile["pattern"][pattern_pos]
                check_pause()

                if check_server_change():
                    cecho("⚠ Server change detected! Stopping farm...", ERROR)
                    state.is_running = False
                    stop_all_movement()
                    break

                result = harvest_direction(step, pattern_pos + 1, profile)

                if result == "WATCHDOG":
                    cecho("🛠 Watchdog recovery: restarting round...", WARN)
                    state.watchdog_triggered = False
                    time.sleep(3)  # รอ /warp garden เสร็จ
                    warp_to_garden_and_land()
                    pattern_pos = 0
                    continue

                if result == "PEST_INTERRUPT":
                    cecho("🐛 Pausing pattern to clear pests...", WARN)
                    ms.player_press_attack(False)
                    with state.in_mode(state.Mode.PEST):
                        pest_cycle()
                    state.clear_events()
                    ms.player_press_attack(False)
                    cecho("🔙 Returning to saved position...", DETAIL)
                    warp_to_garden_and_land()
                    switch_to_farming_outfit()
                    ms.player_inventory_select_slot(0)
                    time.sleep(0.1)
                    ms.player_press_attack(True)
                    cecho(f"▶️ Resuming at step {pattern_pos + 1}...", SUCCESS)
                    continue

                pattern_pos += 1

            if not state.is_running:
                continue

            cecho("│ 🔚 Respawning at start position...", DETAIL)
            stop_all_movement()

            if should_stop_for_pests():
                wait_deadline = time.time() + OUTFIT_WAIT_TIMEOUT
                while state.changing_outfit and time.time() < wait_deadline:
                    time.sleep(0.05)
                with state.in_mode(state.Mode.PEST):
                    pest_cycle()
                state.clear_events()
                warp_to_garden_and_land()
                
            ms.player_press_attack(False)
            # cecho("✈️ Flying to starting position...", AQUA)
            # fly_to_start_position(profile)
            time.sleep(0.5)

            smooth_look_at(profile["yaw"], profile["pitch"], steps=10, delay=0.03)
            cecho("📍 Setting new spawn point...", DETAIL)
            ms.execute("/setspawn")
            time.sleep(0.3)

            _buff_and_spray(profile)

            time.sleep(0.1)
            ms.player_inventory_select_slot(0)
            time.sleep(0.1)
            ms.player_press_attack(True)
            time.sleep(0.2)

            cecho("└───────────────────────────────\n", DETAIL)
            sell_items_to_npc()
            metrics.record("round", time.time() - round_started)
            cecho(f"🎉 Round {state.round_count} of '{profile_name}' complete!", GOLD)
            time.sleep(1)

    except KeyboardInterrupt:
        cecho("\n⏹ Farm stopped by user", ERROR)
    finally:
        stop_all_movement()
        _print_session_summary(profile_name)
        cecho("✅ Shutdown complete.", SUCCESS)