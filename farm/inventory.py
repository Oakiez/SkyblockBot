# -*- coding: utf-8 -*-
"""
inventory.py — Inventory helpers, outfit switching, selling
"""

import re
import time

from system.lib import minescript as ms
from system.lib import lib_inv  # works without mappings
from farm.config import (
    SELL_AFTER_ROUND,
    SELL_ITEMS,
    SELL_ALL_VINYLS,
    FARM_LOADOUT_SLOT,
    PEST_LOADOUT_SLOT,
)
from farm.utils import cecho, SUCCESS, WARN, ERROR, DETAIL, GOLD, AQUA
import farm.state as state


# ============================================================
# SLOT HELPERS
# ============================================================


def inventory_slot_to_container(inv_slot: int, container_size: int = 54) -> int:
    """แปลง player inventory slot เป็น container slot"""
    if 9 <= inv_slot <= 35:
        return container_size + (inv_slot - 9)
    if 0 <= inv_slot <= 8:
        return container_size + 27 + inv_slot
    return inv_slot


def get_inventory_hash() -> str:
    return "|".join(
        f"{item.item}:{item.count}:{item.slot}" for item in ms.player_inventory()
    )


def find_and_click_item_in_container(
    item_id: str, container_size: int = 54
) -> int | None:
    """หา item จาก NBT ID แล้ว click container slot ที่ตรงกัน"""
    target = item_id.upper()
    for item in ms.player_inventory():
        if item.slot is None or not item.nbt:
            continue
        if target in item.nbt.upper():
            slot = inventory_slot_to_container(item.slot, container_size)
            lib_inv.pickup(slot)
            return slot
    return None


def find_items_to_sell() -> list[dict]:
    """คืน list ของ {slot, id, count} สำหรับ item ที่จะขาย
    
    รองรับ 2 วิธี detect:
        1. NBT ID match  — สำหรับ item ทั่วไป (OVERCLOCKER_3000, WRIGGLING_LARVA ฯลฯ)
        2. item type     — สำหรับ music_disc (VINYL_*) ที่ NBT อาจ format ต่างกัน
    """
    # แยก SELL_ITEMS ออกเป็น 2 กลุ่ม
    vinyl_ids   = {s for s in SELL_ITEMS if s.startswith("VINYL_")}
    regular_ids = {s for s in SELL_ITEMS if not s.startswith("VINYL_")}

    found = []

    for item in ms.player_inventory():
        if item.slot is None:
            continue

        item_type = (item.item or "").lower()   # เช่น "minecraft:music_disc_far"
        item_nbt  = (item.nbt  or "").upper()   # NBT string ทั้งหมด

        matched_id = None

        # --- วิธีที่ 1: vinyl = music disc หรือไอเท็มที่รหัสขึ้นต้น VINYL_ ---
        if "music_disc" in item_type or "VINYL_" in item_nbt:
            # ตรงกับ vinyl ที่ระบุใน SELL_ITEMS ตัวไหนจาก NBT
            for vid in vinyl_ids:
                if vid in item_nbt:
                    matched_id = vid
                    break
            # ไม่อยู่ในลิสต์: ขายอยู่ดีถ้าเปิด SELL_ALL_VINYLS (ไม่งั้นข้าม ขายเฉพาะที่ระบุ)
            if matched_id is None and SELL_ALL_VINYLS:
                found_id = re.search(r"VINYL_[A-Z0-9_]+", item_nbt)
                matched_id = found_id.group(0) if found_id else "VINYL(music_disc)"

        # --- วิธีที่ 2: เช็ค NBT ID สำหรับ item ทั่วไป ---
        if matched_id is None:
            for sid in regular_ids:
                if sid in item_nbt:
                    matched_id = sid
                    break

        if matched_id:
            found.append({"slot": item.slot, "id": matched_id, "count": item.count})
            cecho(f"  📦 Found: {matched_id} x{item.count} (slot {item.slot})", DETAIL)

    return found


# ============================================================
# SCREEN WAIT HELPERS
# ============================================================


def wait_for_screen(timeout: float = 3.0) -> bool:
    """รอจนกว่า screen จะเปิด คืน True ถ้าเปิดภายใน timeout"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ms.screen_name() is not None:
            return True
        time.sleep(0.05)
    return False


def wait_for_no_screen(timeout: float = 3.0) -> bool:
    """รอจนกว่า screen จะปิด คืน True ถ้าปิดภายใน timeout"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ms.screen_name() is None:
            return True
        time.sleep(0.05)
    return False


# ============================================================
# OUTFIT SWITCHING
# ============================================================


def _switch_loadout(loadout_slot: int, loadout_name: str):
    """สลับ loadout ด้วย /ld แล้วคลิก slot ของ loadout นั้น (Farm=15, Pest=14)"""
    if state.changing_outfit:
        time.sleep(0.1)
        return
    if state.current_outfit_slot == loadout_slot:
        return

    from farm.movement import stop_all_movement

    stop_all_movement()

    state.changing_outfit = True
    was_paused = state.paused
    state.paused = False
    prev_mode = state.mode
    state.mode = state.Mode.SWITCHING

    try:
        ms.execute("/ld")
        if not wait_for_screen(timeout=3.0):
            cecho("⚠️ Loadout screen did not open!", WARN)
            return

        time.sleep(0.75)
        lib_inv.pickup(loadout_slot)
        time.sleep(0.75)

        lib_inv.close()
        wait_for_no_screen(timeout=2.0)
        time.sleep(0.5)  # ให้หน้าจอปิดสนิทก่อน ไม่งั้นปุ่มที่กดจะถูกรีเซ็ตตอนปิด GUI

        ms.player_press_attack(True)
        time.sleep(0.1)

        state.current_outfit_slot = loadout_slot
        cecho(f"👔 Switched to {loadout_name}", AQUA)
    finally:
        state.mode = prev_mode
        state.paused = was_paused
        state.changing_outfit = False


def switch_to_farming_outfit():
    _switch_loadout(FARM_LOADOUT_SLOT, "Farm loadout")


def switch_to_pest_outfit():
    _switch_loadout(PEST_LOADOUT_SLOT, "Pest loadout")


def find_and_use_fishing_rod():
    """Cast แล้ว reel fishing rod จาก hotbar"""
    if state.changing_outfit:
        return

    state.changing_outfit = True
    was_paused = state.paused
    state.paused = False
    cecho("🎣 Using fishing rod...", DETAIL)

    from farm.movement import stop_all_movement

    stop_all_movement()

    for item in ms.player_inventory():
        if item.slot is None or not (0 <= item.slot <= 8):
            continue
        name = (item.item or "").lower()
        nbt = (item.nbt or "").lower()
        if "fishing" in name or "fishing" in nbt:
            ms.player_press_sneak(True)
            ms.player_inventory_select_slot(item.slot)
            time.sleep(0.2)
            for _ in range(2):
                ms.player_press_use(True)
                time.sleep(0.1)
                ms.player_press_use(False)
                time.sleep(0.4)
            ms.player_inventory_select_slot(0)
            time.sleep(0.1)
            ms.player_press_sneak(False)
            break

    ms.player_press_attack(True)
    time.sleep(0.1)
    state.paused = was_paused
    state.changing_outfit = False
    cecho("✅ Fishing rod used.", SUCCESS)


# ============================================================
# SELLING
# ============================================================


def sell_items_to_npc():
    """เปิด trade menu แล้วขาย items ทั้งหมด"""
    if not SELL_AFTER_ROUND:
        return

    cecho("💰 Starting sell routine...", GOLD)
    ms.player_press_attack(False)
    state.spraying_plots = True

    try:
        items = find_items_to_sell()
        if not items:
            cecho("✅ No items to sell", SUCCESS)
            return

        cecho(f"💵 Selling {len(items)} item(s)...", GOLD)
        ms.execute("/pickupstash")
        ms.execute("/trades")

        if not wait_for_screen(timeout=4.0):
            cecho("⚠️ Trade screen did not open, skipping sell.", WARN)
            return

        for info in items:
            slot = inventory_slot_to_container(info["slot"])
            cecho(f"  💰 Selling {info['id']} x{info['count']}...", GOLD)
            lib_inv.pickup(slot)
            time.sleep(0.5)

        lib_inv.close()
        wait_for_no_screen(timeout=2.0)
        cecho(f"💵 Sold {len(items)} item(s) successfully!", SUCCESS)

    except Exception as e:
        cecho(f"❌ Error during selling: {e}", ERROR)
        try:
            lib_inv.close()
        except:
            pass
    finally:
        state.spraying_plots = False
