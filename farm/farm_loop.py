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
    PEST_CHECK_INTERVAL, OUTFIT_WAIT_TIMEOUT, DEBUG_TIMING, CHAT_SOURCE, LIB_EVENT_LOAD_TIMEOUT, ATTACK_REASSERT_INTERVAL, FARM_TOOL_SLOT, REFOCUS_GRACE_SECONDS, SPRAY_EVERY_SECONDS,
    BUFF_EVERY_SECONDS, BUFF_RETRY_SECONDS, MAINTENANCE_CHECK_INTERVAL, ATTACK_RELEASE_SECONDS,
)
from farm.profiles import load_profile
from farm.buff import get_buff
from farm.utils import cecho, SUCCESS, WARN, ERROR, DETAIL, GOLD, AQUA, wait_until
from farm.movement import (
    stop_all_movement, stop_movement_only, start_movement, hold_movement,
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
from farm import sensors, watchdog, metrics, chatlog, failsafe, tab_bridge, hud, notify
from farm.config import RECONNECT_WORLD_SETTLE_SECONDS, RECONNECT_REJOIN_COMMANDS, RECONNECT_RESUME_FARM
from botkit.link import BotLink
from botkit.reconnect import Reconnector
from botkit.discord_io import fmt_duration
from farm.actions import restore_farm_state
import farm.state as state



# ============================================================
# CHAT SOURCE
# ============================================================

def _load_lib_event(timeout: float) -> bool:
    """import system.lib.lib_event ใน thread แยก: ตอน import มันรอ socket จากสคริปต์ในเกมแบบไม่มี timeout
    ถ้าสคริปต์ในเกมพัง บอทจะค้างตั้งแต่เริ่ม จึงรอแค่ timeout แล้วถอยไปใช้ log แทน"""
    result = {}

    def _import():
        try:
            import system.lib.lib_event  # noqa: F401 — import แล้ว EventQueue มี register_chat_listener(eventlib=True)
            result["ok"] = True
        except BaseException as e:      # lib เรียก sys.exit() ถ้าเวอร์ชัน Minescript ไม่ตรง
            result["err"] = e

    t = threading.Thread(target=_import, daemon=True)
    t.start()
    t.join(timeout)
    if result.get("ok"):
        return True
    cecho(f"📜 lib_event failed to load ({result.get('err', 'timeout')})", WARN)
    return False


def _start_chat_source(event_queue, handlers) -> None:
    """ให้ข้อความแชทจากเซิร์ฟเวอร์ไปถึง handlers: lib_event (ผ่าน event_queue) หรืออ่าน latest.log"""
    if CHAT_SOURCE == "eventlib" and _load_lib_event(LIB_EVENT_LOAD_TIMEOUT):
        event_queue.register_chat_listener(eventlib=True)   # ข้อความเข้า event_loop เป็น event "chat"
        cecho("📜 Chat source: lib_event", DETAIL)
        return
    ok = chatlog.start(handlers)
    cecho("📜 Chat source: " + ("latest.log" if ok else "chat events only (log not found)"), DETAIL)
    if not ok:
        event_queue.register_chat_listener()


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
        if elapsed >= AUTO_UNPAUSE_SECONDS and not state.pause_hold:
            cecho("⏯️ Auto-unpausing farm...", WARN)
            state.paused = False
            break
        if not state.pause_hold and int(elapsed) % 5 == 0 and int(elapsed) != last_log and int(elapsed) > 0:
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
    """ลำดับตอนเริ่ม: หันหน้า → setspawn → loadout → รับบัฟ → สเปรย์ → (เคลียร์สถานะ) → เริ่มคลิกซ้าย"""
    cecho("🚀 Initializing farm...", GOLD)
    ms.player_press_attack(False)
    land_if_flying()

    # 1) หันหน้าตามฟาร์ม
    smooth_look_at(profile["yaw"], profile["pitch"], steps=15, delay=0.03)
    time.sleep(0.3)

    # 2) setspawn ที่จุดเริ่ม (บัฟ/สเปรย์จะวาร์ปกลับมาที่นี่)
    cecho("📍 Setting spawn...", DETAIL)
    ms.execute("/setspawn")
    time.sleep(0.3)

    # 3) loadout: pest เกิดค้างอยู่แล้ว → Farm ไม่งั้น Pest (รอ pest เกิด)
    state.current_outfit_slot = None  # บังคับสลับใหม่เสมอ เผื่อ loadout จริงต่างจากที่จำไว้
    alive, _ = sensors.pest_info_wait(timeout=2.0)
    if alive > 0:
        cecho(f"🐛 {alive} pest(s) already alive → Farm loadout", WARN)
        switch_to_farming_outfit()
    else:
        switch_to_pest_outfit()

    # 4-5) รับบัฟ + สเปรย์ (ครั้งแรกถึงเวลาเสมอ) แล้ววาร์ปกลับจุด setspawn
    _buff_and_spray(profile)

    # 6) เคลียร์สถานะ: ปล่อยปุ่ม/ปิด GUI/ถือ hoe/หันกล้อง แล้วกดคลิกซ้ายเป็นขั้นสุดท้าย
    restore_farm_state(profile, "start")
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


_last_grab_handled = 0.0


def _refresh_attack_after_regrab(direction: str, profile: dict) -> None:
    """ปล่อยปุ่มตี > 1 tick หลังเกมจับเมาส์คืน เพื่อล้าง missTime ของเกม (ทำครั้งเดียวต่อการจับคืนหนึ่งครั้ง)"""
    global _last_grab_handled
    changed_at = tab_bridge.grab_changed_at()
    if changed_at <= _last_grab_handled:
        return
    _last_grab_handled = changed_at
    grabbed, _active = tab_bridge.input_state()
    if not grabbed:
        return
    ms.player_press_attack(False)
    time.sleep(ATTACK_RELEASE_SECONDS)
    ms.player_press_attack(True)
    hold_movement(direction, hold_forward=profile.get("hold_forward", False))
    cecho("🖱️ Mouse re-grabbed — refreshed attack", DETAIL)


def harvest_direction(direction_data: dict, movement_num: int, profile: dict) -> str | None:
    """
    เดินทิศทางเดียวจนชนกำแพง
    คืน "PEST_INTERRUPT" ถ้า pest เกิน threshold ระหว่างเดิน
    """
    direction = direction_data["direction"]
    arrow = {"left": "←", "right": "→", "forward": "↑", "backward": "↓"}.get(direction, "→")
    cecho(f"🚜 Move {movement_num}: {direction_data['name']} {arrow}", DETAIL)

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
    last_maint      = time.time()
    was_changing    = False

    while state.is_running:
        now = time.time()

        # --- Watchdog สั่งให้เริ่มรอบใหม่ ---
        if state.watchdog_triggered:
            stop_movement_only()
            return "WATCHDOG"

        # --- ถึงเวลารับบัฟ/สเปรย์ → หยุดกลางเลนไปทำทันที (ไม่ต้องรอจบรอบ) ---
        if now - last_maint >= MAINTENANCE_CHECK_INTERVAL and not state.spraying_plots and not state.changing_outfit:
            last_maint = now
            if _buff_due() or _spray_due(profile):
                stop_movement_only()
                cecho("🧪 Buff/spray due — pausing lane...", WARN)
                ms.execute("/setspawn")       # วาร์ปกลับมาเดินต่อจากจุดนี้
                return "MAINTENANCE"

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

        # --- เพิ่งจับเมาส์คืน (กลับมา focus): เกมตั้ง missTime=10000 ใน grabMouse() ซึ่งห้ามทุบบล็อก
        #     และจะล้างก็ต่อเมื่อมี tick ที่ "ไม่ได้กดปุ่มตี" — ถ้าบอทกดค้างตลอด จะไม่ทุบเลยหลายนาที
        #     จึงปล่อยปุ่มตีสั้น ๆ ให้เกินหนึ่ง tick แล้วกดใหม่ ---
        _refresh_attack_after_regrab(direction, profile)

        # --- กดคลิกซ้ายค้างซ้ำเป็นระยะ: สถานะปุ่มอาจหลุดเงียบ ๆ (เช่นหลังปิด GUI) แล้วบอทไม่รู้ ---
        if now - last_attack >= ATTACK_REASSERT_INTERVAL and not state.paused:
            ms.player_inventory_select_slot(FARM_TOOL_SLOT)
            ms.player_press_attack(True)
            hold_movement(direction, hold_forward=profile.get("hold_forward", False))   # ปุ่มเดินก็หลุดได้เหมือนกัน
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
                    # เพิ่งกลับมา focus: เกมรีเซ็ตปุ่มเดินทิ้ง (KeyMapping.setAll ใน grabMouse) ตัวละครเลยหยุด
                    # ไม่ใช่ชนกำแพง → กดเดินใหม่แล้วเดินเลนเดิมต่อ แทนการข้ามไปเลนถัดไป
                    if time.time() - tab_bridge.grab_changed_at() < REFOCUS_GRACE_SECONDS:
                        cecho("↩️ Focus changed — re-pressing keys, continuing same lane", DETAIL)
                        ms.player_press_attack(True)
                        hold_movement(direction, hold_forward=profile.get("hold_forward", False))
                        stuck_counter = 0
                        last_inventory = None
                    else:
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
    ctx = {"resume": False, "world_up": True}   # resume = ตอนหลุดบอททำงานอยู่ → ต่อสำเร็จแล้วเริ่มต่อ

    def _status_fields():
        elapsed = time.time() - state.start_time if state.start_time else 0
        status = "RUNNING" if state.is_running and not state.paused else ("PAUSED" if state.paused else "STOPPED")
        fields = [("Profile", state.current_profile or "-"), ("Status", status), ("Mode", state.mode),
                  ("Round", str(state.round_count)), ("Runtime", fmt_duration(elapsed) if elapsed else "-")]
        try:
            (count, plots), _t = sensors.cached_pests()
            fields.append(("Pests", f"{max(state.pest_alive_hint, count)}/{AMOUNT_OF_PESTS}"))
            x, y, z = sensors.position()
            fields.append(("Position", f"{x:.0f}, {y:.0f}, {z:.0f}"))
        except Exception:
            pass
        if state.failsafe_reason:
            fields.append(("Failsafe", state.failsafe_reason))
        if reconnector.active:
            fields.append(("Reconnect", "trying…"))
        return fields

    def _alert(title, description="", level="info", screenshot=False):
        cecho(f"{title} {description}".strip().split("\n")[0], {"error": ERROR, "warn": WARN, "ok": SUCCESS}.get(level, DETAIL))
        link.alert(title, description, level, screenshot)

    def _remote_stop():
        reconnector.cancel()
        ctx["resume"] = False
        if not state.is_running:
            return "บอทหยุดอยู่แล้ว (ยกเลิกการต่อเซิร์ฟเวอร์/เริ่มต่อที่ค้างอยู่ด้วย)"
        state.is_running = False
        state.paused = False
        state.pause_hold = False
        try:
            stop_all_movement()
        except Exception:
            pass
        return "สั่งหยุดบอทแล้ว — กด ] ในเกมเมื่อพร้อมเริ่มใหม่"

    def _remote_pause():
        if not state.is_running:
            return "บอทไม่ได้ทำงานอยู่"
        state.pause_hold = True    # พักค้างไว้จนกว่าจะสั่ง resume (ไม่ auto-unpause)
        state.paused = True
        return "พักบอทแล้ว — ส่ง `resume` เพื่อต่อ"

    def _remote_resume():
        if not state.paused:
            return "บอทไม่ได้พักอยู่"
        state.pause_hold = False
        state.paused = False
        return "ต่อบอทแล้ว"

    link = BotLink("farm", _status_fields, {"stop": _remote_stop, "pause": _remote_pause, "resume": _remote_resume})
    notify.link = link

    def _after_reconnect():
        """ต่อเซิร์ฟเวอร์สำเร็จ: รอโลกโหลด → กลับเข้า Skyblock/Garden → เริ่มฟาร์มต่อ (ถ้าตอนหลุดกำลังฟาร์มอยู่)"""
        time.sleep(RECONNECT_WORLD_SETTLE_SECONDS)
        if not chatlog.is_active():
            # สคริปต์ที่ฝังในเกม (เช่น lib_event) อาจไม่รอดการหลุด → สลับไปอ่านแชทจาก latest.log ที่ไม่พึ่งสคริปต์ในเกม
            # (ตอน chatlog ทำงาน event แชทจาก eventlib จะถูกข้าม จึงไม่ซ้ำ)
            chatlog.start(chat_handlers)
        for command, wait in RECONNECT_REJOIN_COMMANDS:
            ms.execute(command)
            time.sleep(wait)
        if RECONNECT_RESUME_FARM and ctx["resume"]:
            ctx["resume"] = False
            state.is_running = True
            _alert("▶️ Farm resumed after reconnect", "", "ok", True)
        else:
            _alert("Reconnected — farm stays stopped", "บอทไม่ได้ทำงานตอนหลุด หรือปิดการเริ่มต่ออัตโนมัติไว้ — กด ] เมื่อพร้อม", "info", True)

    reconnector = Reconnector(_alert, after_connected=_after_reconnect)
    reconnector.remember_server()

    event_queue = ms.EventQueue()
    event_queue.register_key_listener()
    event_queue.register_world_listener()  # ป้องกัน script ตายเงียบเมื่อ disconnect
    chat_handlers = [
        check_for_restart_message, check_for_limbo_message,
        check_for_pest_cooldown_message, check_for_pest_spawn_message,
    ]
    _start_chat_source(event_queue, chat_handlers)   # chat listener ลงทะเบียนในนี้ตามแหล่งที่ใช้

    def event_loop():
        while True:
            try:
                # lib_event ส่งแชททุกข้อความ (มาเป็นชุดได้) → ดึงต่อทันทีจนคิวว่าง ค่อยพัก
                event = event_queue.get(block=True, timeout=0.05)
                if event.type == "key" and event.action == 1:
                    if event.key == START_STOP_KEY:
                        state.is_running = not state.is_running
                        if state.is_running:
                            cecho("▶ Farm Started!", SUCCESS)
                            reconnector.cancel()      # คุณสั่งเริ่มเอง = เข้าเกมมาดูแลเองแล้ว
                        else:
                            cecho("⏹ Farm Stopped", ERROR)
                            ctx["resume"] = False
                            stop_all_movement()
                            ms.execute("/setspawn")
                            link.alert("⏹ Farm stopped (manual)", "", "info")
                    elif event.key == PAUSE_KEY and state.is_running:
                        state.pause_hold = False      # พักด้วยปุ่มยังมี auto-unpause เหมือนเดิม
                        state.paused = not state.paused
                elif event.type == "chat" and not chatlog.is_active():
                    for handler in chat_handlers:
                        handler(event.message)
                elif event.type == EventType.WORLD:
                    ctx["world_up"] = bool(event.connected)
                    reconnector.world_event(event.connected)
                    if event.connected:
                        reconnector.remember_server()
                    else:
                        cecho("🔌 Disconnected from world! Stopping farm...", ERROR)
                        if not reconnector.active:    # หลุดซ้อนระหว่างกำลังต่อใหม่ ไม่ทับค่า resume เดิม
                            ctx["resume"] = state.is_running and not state.failsafe_reason
                        state.is_running = False
                        try:
                            stop_all_movement()
                        except Exception:
                            pass
                        if not reconnector.begin():   # begin() แจ้ง Discord เองเมื่อเริ่มต่อใหม่
                            link.alert("🔌 Disconnected from world", "หยุดบอทแล้ว (ปิดการต่อใหม่อัตโนมัติ/ไม่รู้เซิร์ฟเวอร์)",
                                       "error", False)
            except:
                pass

    threading.Thread(target=event_loop, daemon=True).start()
    sensors.start()
    watchdog.start()
    failsafe.start()
    hud.start(profile)
    link.start()

    def _rounds():
        """ลูปฟาร์มหลัก (เดิมอยู่ใน try โดยตรง) แยกเป็นฟังก์ชันเพื่อให้กลับมาทำงานต่อได้หลังหลุดเซิร์ฟเวอร์"""
        nonlocal initialized
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
                    notify.event("⚠️ Server change detected — farm stopped", "ตำแหน่งกระโดดไกลผิดปกติ (อาจถูกย้ายเซิร์ฟเวอร์)", "error", True)
                    break

                result = harvest_direction(step, pattern_pos + 1, profile)

                if result == "WATCHDOG":
                    cecho("🛠 Watchdog recovery: restarting round...", WARN)
                    notify.event("🛠 Watchdog recovery", "ตำแหน่งไม่ขยับนานผิดปกติ → /warp garden แล้วเริ่มรอบใหม่", "warn")
                    state.watchdog_triggered = False
                    time.sleep(3)  # รอ /warp garden เสร็จ
                    warp_to_garden_and_land()
                    restore_farm_state(profile, "watchdog")
                    pattern_pos = 0
                    continue

                if result == "MAINTENANCE":
                    _buff_and_spray(profile)          # วาร์ปกลับจุด /setspawn กลางเลนเองตอนจบ
                    restore_farm_state(profile, "after buff/spray")
                    cecho(f"▶️ Resuming at step {pattern_pos + 1}...", SUCCESS)
                    continue

                if result == "PEST_INTERRUPT":
                    cecho("🐛 Pausing pattern to clear pests...", WARN)
                    ms.player_press_attack(False)
                    with state.in_mode(state.Mode.PEST):
                        pest_cycle()
                    state.clear_events()
                    cecho("🔙 Returning to saved position...", DETAIL)
                    warp_to_garden_and_land()
                    switch_to_farming_outfit()
                    restore_farm_state(profile, "after pest clearing")
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

            cecho("└───────────────────────────────\n", DETAIL)
            sell_items_to_npc()
            restore_farm_state(profile, "end of round")
            metrics.record("round", time.time() - round_started)
            cecho(f"🎉 Round {state.round_count} of '{profile_name}' complete!", GOLD)
            time.sleep(1)

    try:
        while True:
            try:
                _rounds()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                if not ctx["world_up"] or reconnector.active:
                    # หลุดจากโลกแล้วคำสั่งเกม (ตำแหน่ง/คลิก ฯลฯ) ย่อมพัง: ไม่ใช่บั๊ก รอต่อใหม่แล้วเริ่มรอบใหม่
                    cecho(f"[Disconnected] ข้าม error ระหว่างหลุด: {type(e).__name__}: {e}", DETAIL)
                    initialized = False
                    time.sleep(1.0)
                    continue
                link.alert("💥 farm crashed", f"{type(e).__name__}: {e}", "error", screenshot=True, wait=True)
                raise
    except KeyboardInterrupt:
        cecho("\n⏹ Farm stopped by user", ERROR)
    finally:
        reconnector.cancel()
        try:
            stop_all_movement()
        except Exception:
            pass
        hud.stop()
        elapsed = time.time() - state.start_time if state.start_time else 0
        link.alert("⏹ farm script ended", f"{state.round_count} รอบ ใน {fmt_duration(elapsed)}", "warn", wait=True)
        link.stop()
        _print_session_summary(profile_name)
        cecho("✅ Shutdown complete.", SUCCESS)