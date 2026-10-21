# -*- coding: utf-8 -*-
"""
pest.py — Pest detection, vacuum, spray
"""

import math
import re
import threading
import time

from system.lib import minescript as ms
from system.lib.minescript import entities
from system.lib.java import JavaClass
from system.lib import lib_inv  # works without mappings
from farm import metrics, sensors, tab_bridge
from farm.config import (
    AMOUNT_OF_PESTS, FLY_HEIGHT, PEST_PLOT_TIMEOUT, VACUUM_SLOT,
    ENTITY_SCAN_INTERVAL, ENTITY_SCAN_RANGE, PLOT_TP_SETTLE, PLOT_LAND_SNEAK,
    PEST_CHECK_INTERVAL, TABLIST_SLOW_WARN, TAB_BRIDGE_MAX_AGE, FARM_TOOL_SLOT,
    DEBUG_TIMING, PEST_USE_WARP, WARP_SLOT, WARP_MIN_DISTANCE, WARP_MAX_PER_PEST,
    WARP_SELECT_DELAY, WARP_SETTLE_TIMEOUT, VACUUM_REACH, VACUUM_TICK,
    PEST_APPEAR_TIMEOUT, PEST_PROGRESS_EXTEND, PEST_PLOT_MAX_SECONDS,
)
from farm.garden import PLOT_CENTERS
from farm.utils import (
    cecho,
    SUCCESS,
    WARN,
    ERROR,
    DETAIL,
    GOLD,
    AQUA,
    strip_color_codes,
    wait_until,
)
from farm.movement import (
    fly_to_height,
    move_to_plot_center,
    smooth_look_at,
    stop_all_movement,
    land_if_flying,
    release_all_keys,
    warp_to_garden_and_land,
    _sqrt,
)
import farm.state as state


# ============================================================
# PEST DETECTION
# ============================================================


_tablist_lock = threading.Lock()   # JavaClass ไม่ปลอดภัยถ้าหลาย thread เรียกพร้อมกัน → ต่อคิว
TABLIST_RETRIES = 3                # tablist เปลี่ยนระหว่างวนอ่านได้ (ConcurrentModification) → อ่านใหม่


def _read_tablist_once() -> tuple[int, list[str]]:
    mc = JavaClass("net.minecraft.client.Minecraft").getInstance()
    connection = mc.getConnection()
    pest_count = 0
    pest_plots = []

    for p in connection.getOnlinePlayers():
        display = p.getTabListDisplayName()
        if not display:
            continue
        text = display.getString()
        if "Alive" in text:
            m = re.search(r"Alive:\s*(\d+)", text)
            if m:
                pest_count = int(m.group(1))
        elif "Plots" in text:
            m = re.search(r"Plots:\s*(.*)", text)
            if m:
                pest_plots = [x.strip() for x in m.group(1).split(",") if x.strip()]

    return pest_count, pest_plots


def get_pest_info() -> tuple[int, list[str]]:
    """อ่าน pest count และ plots จาก tablist คืน (count, plots)"""
    fast = tab_bridge.latest(TAB_BRIDGE_MAX_AGE)
    if fast is not None:
        return fast
    t0 = time.time()
    last_error = None
    with _tablist_lock:
        for _ in range(TABLIST_RETRIES):
            try:
                result = _read_tablist_once()
                took = time.time() - t0
                metrics.record("tablist", took)
                if took >= TABLIST_SLOW_WARN:
                    cecho(f"[Pest] tablist read took {took:.1f}s (slow)", WARN)
                return result
            except Exception as e:
                last_error = e
                time.sleep(0.05)
    cecho(f"[Pest] Error reading tablist: {last_error}", ERROR)
    return 0, []


def should_stop_for_pests() -> bool:
    pests, _ = get_pest_info()
    if pests >= AMOUNT_OF_PESTS:
        cecho(f"[Farming] {pests} pests detected! Triggering pest clearing...", ERROR)
        return True
    return False


# ============================================================
# VACUUM
# ============================================================


def find_all_silverfish() -> list:
    return [
        e
        for e in entities(max_distance=ENTITY_SCAN_RANGE)
        if e and e.position and (e.health == 600 or e.name in ("Silverfish", "Bat"))
    ]


def _vacuum_single_silverfish(sf, deadline: float = None) -> bool:
    """ไล่ vacuum silverfish ตัวเดียว คืน True เมื่อหาย False เมื่อ skip"""
    if not sf or not sf.position:
        return False

    stuck_since = None
    last_reachable = True
    target = sf
    last_scan = 0.0   # สแกน entity ทุก ENTITY_SCAN_INTERVAL ไม่ใช่ทุก tick (หนักมาก)

    while state.is_running:
        if deadline and time.time() > deadline:
            cecho("[Vacuum] Timeout inside silverfish chase, stopping...", WARN)
            ms.player_press_forward(False)  # ← หยุดวิ่งด้วย!
            ms.player_press_use(False)
            return False
        
        now = time.time()
        if now - last_scan >= ENTITY_SCAN_INTERVAL:
            last_scan = now
            # ติดตามด้วย id (เทียบ object ตรง ๆ ใช้ไม่ได้ เพราะตำแหน่งเปลี่ยนทุก tick)
            fresh = next((e for e in find_all_silverfish() if e.id == sf.id), None)
            if fresh is None:
                return True
            target = fresh

        p = ms.player_position()
        s = target.position
        dx, dy, dz = s[0] - p[0], s[1] - p[1], s[2] - p[2]
        dist = _sqrt(dx**2 + dy**2 + dz**2)
        horiz = _sqrt(dx**2 + dz**2)

        ms.player_look_at(s[0], s[1], s[2])
        ms.player_press_forward(dist > 5)

        above_and_unreachable = horiz < 1.5 and dy < -1.0 and dist > 5

        if above_and_unreachable:
            if not last_reachable:
                if stuck_since is None:
                    stuck_since = time.time()
                elif time.time() - stuck_since > 15.0:
                    cecho("[Vacuum] Silverfish unreachable for 15s, skipping...", WARN)
                    return False
            last_reachable = False
        else:
            stuck_since = None
            last_reachable = True

        if above_and_unreachable:
            ms.player_press_sneak(True)
            ms.player_press_jump(False)
        elif p[1] < s[1] - 2:
            ms.player_press_jump(True)
            ms.player_press_sneak(False)
        else:
            ms.player_press_jump(False)
            ms.player_press_sneak(False)

        ms.player_press_use(True)
        time.sleep(0.05)

    return False


def _warp_toward(target) -> bool:
    """หันไปหา target แล้วคลิกขวา AOTV หนึ่งครั้ง คืน True ถ้าตำแหน่งเปลี่ยนจริง"""
    ms.player_press_forward(False)
    ms.player_press_sneak(False)   # sneak + คลิกขวา AOTV ทำงานต่างจากคลิกขวาปกติ
    ms.player_press_use(False)
    ms.player_inventory_select_slot(WARP_SLOT)
    s = target.position
    ms.player_look_at(s[0], s[1], s[2])
    time.sleep(WARP_SELECT_DELAY)
    before = ms.player_position()
    ms.player_press_use(True)
    time.sleep(0.03)
    ms.player_press_use(False)
    return wait_until(
        lambda: math.dist(before, ms.player_position()) > 1.0, WARP_SETTLE_TIMEOUT
    )


def _chase_with_warp(sf, deadline: float = None) -> bool:
    """warp เข้าใกล้ pest แล้วดูดอยู่กับที่ คืน True เมื่อ pest หาย False เมื่อ skip"""
    if not sf or not sf.position:
        return False

    target = sf
    last_scan = 0.0
    warps = 0
    vacuum_ready = False

    try:
        while state.is_running:
            now = time.time()
            if deadline and now > deadline:
                cecho("[Vacuum] Timeout inside pest chase, stopping...", WARN)
                return False

            if now - last_scan >= ENTITY_SCAN_INTERVAL:
                last_scan = now
                fresh = next((e for e in find_all_silverfish() if e.id == sf.id), None)
                if fresh is None:
                    return True
                target = fresh

            p = ms.player_position()
            s = target.position
            dist = math.dist(p, s)

            if dist > WARP_MIN_DISTANCE and warps < WARP_MAX_PER_PEST:
                warps += 1
                vacuum_ready = False
                _warp_toward(target)
                continue

            if not vacuum_ready:
                ms.player_press_sneak(False)
                ms.player_inventory_select_slot(VACUUM_SLOT)
                time.sleep(WARP_SELECT_DELAY)
                vacuum_ready = True

            ms.player_look_at(s[0], s[1], s[2])
            ms.player_press_forward(dist > VACUUM_REACH)  # วาร์ปหมดแล้วยังไกลอยู่ → เดินเข้าไป
            ms.player_press_use(True)
            time.sleep(VACUUM_TICK)
    finally:
        ms.player_press_forward(False)
        ms.player_press_use(False)

    return False


def vacuum_all_silverfish(deadline: float = None):
    """Vacuum silverfish ทั้งหมดใน range โดยเริ่มจากตัวที่ใกล้ที่สุด"""
    ms.player_inventory_select_slot(VACUUM_SLOT)
    time.sleep(0.05)

    # เวลาต่อ plot ไม่ตายตัว: ฆ่าได้ทีละตัวก็ต่อเวลาให้ (ไม่งั้นตัวสุดท้ายถูกตัดทิ้ง) แต่ไม่เกินเพดาน
    started = time.time()
    hard_deadline = started + PEST_PLOT_MAX_SECONDS
    kills = 0

    while state.is_running:
        if deadline and time.time() > deadline:
            cecho("⏱️ Plot timeout! Skipping remaining pests...", WARN)
            break
        
        sfs = find_all_silverfish()
        if not sfs:
            break
        p = ms.player_position()
        closest = min(sfs, key=lambda e: math.dist(p, e.position))
        chase = _chase_with_warp if PEST_USE_WARP else _vacuum_single_silverfish
        if chase(closest, deadline=deadline):
            kills += 1
            if deadline:
                deadline = min(hard_deadline, max(deadline, time.time() + PEST_PROGRESS_EXTEND))
        else:
            cecho("[Vacuum] Skipping unreachable silverfish...", WARN)

    release_all_keys()


def vacuum_plot(plot_number, timeout: float = 20.0):
    """Teleport ไป plot, บินขึ้น, แล้ว vacuum"""
    ms.player_press_attack(False)
    try:
        plot_number = int(plot_number)
    except ValueError:
        cecho(f"[Pest] Invalid plot '{plot_number}', skipping", WARN)
        return

    if plot_number == 25:
        cecho("[Pest] Barn plot skipped", DETAIL)
        return

    t0 = time.time()
    ms.execute(f"/plottp {plot_number}")
    time.sleep(PLOT_TP_SETTLE)

    if PEST_USE_WARP:
        # จุดที่ /plottp ลงอาจอยู่ใต้เพดาน/มีบล็อกติดหัว: fly_to_height ถอยหลังนิดหนึ่งก่อน
        # (ให้พ้นบล็อกที่ติดหัว) แล้วเข้า fly mode บินขึ้นพ้นเพดานที่ FLY_HEIGHT ก่อนค่อยวาร์ป/ดูด
        if not fly_to_height(FLY_HEIGHT):
            cecho("⚠️ Cannot climb above the ceiling, trying anyway...", WARN)
        wait_until(lambda: bool(find_all_silverfish()), PEST_APPEAR_TIMEOUT)
    else:
        land_if_flying(timeout=PLOT_LAND_SNEAK)
        ms.player_inventory_select_slot(1)
        if not fly_to_height(FLY_HEIGHT):
            cecho("❌ Cannot fly, skipping this plot", ERROR)
            return
        time.sleep(0.2)

        if plot_number in PLOT_CENTERS:
            tx, tz = PLOT_CENTERS[plot_number]
            time.sleep(0.1)
            ms.player_press_use(True)
            time.sleep(1)
            ms.player_press_use(False)
            move_to_plot_center(tx, tz)
            time.sleep(0.1)

    plot_deadline = time.time() + timeout
    vacuum_all_silverfish(deadline=plot_deadline)

    cecho("🧹 Cleanup after vacuum...", DETAIL)
    release_all_keys()
    metrics.record("plot", time.time() - t0, str(plot_number))
    if DEBUG_TIMING:
        cecho(f"⏱ plot {plot_number} took {time.time() - t0:.1f}s", DETAIL)


def _plots_to_clear() -> list:
    """plot ที่ต้องไปกำจัด: รวมจากข้อความ spawn (ทันที) + cache ของ tablist (ถ้ายังสด)
    ไม่อ่าน tablist ตรง ๆ ถ้าไม่จำเป็น เพราะช้า (เป็นสาเหตุที่เคยรอนานก่อน /plottp)"""
    plots = {str(p) for p in state.pending_pest_plots}
    (_, cached_plots), cached_at = sensors.cached_pests()
    if time.time() - cached_at <= PEST_CHECK_INTERVAL * 3:
        plots |= {str(p) for p in cached_plots}
    if not plots:
        _, direct = get_pest_info()   # fallback สุดท้าย
        plots = {str(p) for p in direct}
    return sorted(plots, key=lambda p: int(p) if p.isdigit() else 0)


def pest_cycle() -> bool:
    """Clear pests จากทุก plot ที่ติด (สลับเป็น Farm loadout ก่อนเสมอ เพราะ Farming Fortune สูงสุด ฆ่าได้ดีสุด)"""
    from farm.inventory import switch_to_farming_outfit  # import ตอนใช้ ป้องกัน circular import

    pest_plots = _plots_to_clear()
    if pest_plots:
        switch_to_farming_outfit()   # ถ้าอยู่ Farm อยู่แล้วจะข้ามเอง
    ms.player_press_attack(False)    # หลังสลับชุด (สลับชุดจะกดคลิกซ้ายค้างทิ้งไว้)

    if not pest_plots:
        cecho("[Pest] No pests, continuing farming", SUCCESS)
        return True

    state.cycling_pests = True
    try:
        for plot in pest_plots:
            if not state.is_running:
                break
            vacuum_plot(plot, timeout=PEST_PLOT_TIMEOUT)
            state.pending_pest_plots.discard(str(plot))
    finally:
        state.cycling_pests = False
        state.pending_pest_plots.clear()
        state.pest_alive_hint = 0
        release_all_keys()
        ms.player_inventory_select_slot(FARM_TOOL_SLOT)

    return True


# ============================================================
# SPRAY
# ============================================================


def spray_plots(profile: dict):
    """Spray plots ที่กำหนดใน profile"""
    from farm.inventory import wait_for_screen, wait_for_no_screen

    plots = profile.get("spray_plots", [])
    if not plots:
        cecho("⏭️ No spray plots configured, skipping.", DETAIL)
        return

    cecho("🌿 Starting spray routine...", SUCCESS)
    ms.player_press_attack(False)
    state.spraying_plots = True

    ms.player_inventory_select_slot(3)
    time.sleep(0.3)

    for plot_num in plots:
        if not state.is_running:
            break
        cecho(f"🚁 Warping to plot {plot_num}...", AQUA)
        ms.execute(f"/plottp {plot_num}")
        time.sleep(1.5)
        ms.player_press_forward(True)
        time.sleep(0.5)
        ms.player_press_forward(False)
        time.sleep(0.1)
        cecho(f"  🌿 Spraying plot {plot_num}...", SUCCESS)
        ms.player_press_use(True)
        time.sleep(0.1)
        ms.player_press_use(False)
        time.sleep(1.5)

    cecho("🏠 Returning to starting position...", AQUA)
    warp_to_garden_and_land()
    state.spraying_plots = False
    cecho("✅ Spray routine complete!", SUCCESS)
