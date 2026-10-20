# -*- coding: utf-8 -*-
"""
profiles.py — Farm profiles ทั้งหมด

แต่ละ profile มี:
  name, description     : ข้อมูลแสดงผล
  yaw, pitch            : มุมกล้องขณะ farm
  max_speed             : ความเร็วสูงสุด (ข้อมูลเฉย ๆ)
  tool_id               : NBT ID ของ tool ใน hotbar
  pattern               : ลำดับทิศทางที่ bot จะเดิน
  hold_forward          : ค้าง W ตลอดหรือไม่
  start_pos             : จุดเริ่มต้นของ round ใหม่ (x, z, yaw, pitch)
  spray_plots           : plot ที่จะ spray ([] = ไม่ spray)
  spray_interval        : spray ทุกกี่รอบ (0 = ไม่ spray)
"""

# ============================================================
# PATTERN HELPERS
# ============================================================


def _moves(*pairs):
    """สร้าง pattern list จาก pairs ของทิศทาง"""
    result = []
    for pair in pairs:
        for d in pair:
            result.append({"direction": d, "name": d.capitalize()})
    return result


def _repeat(pair, times):
    """ทำซ้ำ pair ของทิศทาง n ครั้ง"""
    return _moves(*([pair] * times))


# ============================================================
# PROFILES
# ============================================================

FARM_PROFILES = {
    "mushroom": {
        "name": "Mushroom Farm",
        "description": "A-D alternating pattern with wall detection",
        "yaw": -116.5,
        "pitch": 5.5,
        "max_speed": 233,
        "tool_id": "FUNGI_CUTTER",
        "pattern": _repeat(("left", "right"), 6),
        "hold_forward": False,
        "start_pos": {"x": -45, "z": 49, "yaw": -116.5, "pitch": 5.5},
        "spray_plots": [],
        "spray_interval": 0,
    },
    "wheat": {
        "name": "Wheat Farm",
        "description": "Right-Left (D -> A) pattern",
        "yaw": 123.96,
        "pitch": 0,
        "tool_id": "THEORETICAL_HOE_WHEAT",
        "pattern": _repeat(("right", "left"), 17),
        "hold_forward": False,
        "start_pos": {"x": 36.3, "z": 143.512, "yaw": 123.96, "pitch": 0},
        "spray_plots": [4],
        "spray_interval": 5,
    },
    "potato": {
        "name": "Potato Farm",
        "description": "Simple left-right pattern",
        "yaw": -90.0,
        "pitch": 5.5,
        "max_speed": 93,
        "tool_id": "THEORETICAL_HOE_POTATO",
        "pattern": _repeat(("left", "right"), 5),
        "hold_forward": False,
        "start_pos": {"x": -45, "z": 49, "yaw": -90.0, "pitch": 5.5},
        "spray_plots": [],
        "spray_interval": 0,
    },
    "carrot": {
        "name": "Carrot Farm",
        "description": "Carrot harvesting pattern",
        "yaw": -90.0,
        "pitch": 5.5,
        "max_speed": 93,
        "tool_id": "THEORETICAL_HOE_CARROT",
        "pattern": _repeat(("left", "right"), 5),
        "hold_forward": False,
        "start_pos": {"x": -45, "z": 49, "yaw": -90.0, "pitch": 5.5},
        "spray_plots": [],
        "spray_interval": 0,
    },
    "wart": {
        "name": "Wart Farm",
        "description": "Wart harvesting pattern",
        "yaw": 90.0,
        "pitch": 5.5,
        "max_speed": 93,
        "tool_id": "THEORETICAL_HOE_WARTS",
        "pattern": _repeat(("right", "left"), 5),
        "hold_forward": False,
        "start_pos": {"x": -45, "z": 49, "yaw": 90.0, "pitch": 5.5},
        "spray_plots": [],
        "spray_interval": 0,
    },
    "cane": {
        "name": "Sugar Cane Farm",
        "description": "Left-backward alternating",
        "yaw": 45.0,
        "pitch": 0.0,
        "max_speed": 328,
        "tool_id": "THEORETICAL_HOE_CANE",
        "pattern": _repeat(("left", "backward"), 15)
        + [{"direction": "left", "name": "Left"}],
        "hold_forward": False,
        "start_pos": {"x": -45, "z": 49, "yaw": 45.0, "pitch": 0.0},
        "spray_plots": [],
        "spray_interval": 0,
    },
    "cocoa": {
        "name": "Cocoa Bean Farm",
        "description": "Forward-left-backward-left pattern",
        "yaw": -90.0,
        "pitch": 5.5,
        "max_speed": 180,
        "tool_name": "Coco Chopper",
        "pattern": _repeat(("forward", "left", "backward", "left"), 1),
        "hold_forward": False,
        "start_pos": {"x": -45, "z": 49, "yaw": -90.0, "pitch": 5.5},
        "spray_plots": [],
        "spray_interval": 0,
    },
    "melon": {
        "name": "Melon Farm",
        "description": "Left-Forward-Right-forward pattern",
        "yaw": 90.0,
        "pitch": -58.5,
        "max_speed": 277,
        "tool_id": "MELON_DICER",
        "pattern": _repeat(("left", "forward", "right", "forward"), 5)
        + [
            {"direction": "left", "name": "Left"},
            {"direction": "forward", "name": "Forward"},
            {"direction": "right", "name": "Right"},
        ],
        "hold_forward": False,
        "start_pos": {"x": -45, "z": 49, "yaw": 90.0, "pitch": -58.5},
        "spray_plots": [],
        "spray_interval": 0,
    },
    "pumpkin": {
        "name": "Pumpkin Farm",
        "description": "Left-Forward-Right-forward pattern",
        "yaw": 90.0,
        "pitch": -58.5,
        "max_speed": 277,
        "tool_id": "PUMPKIN_DICER",
        "pattern": _repeat(("left", "forward", "right", "forward"), 5)
        + [
            {"direction": "left", "name": "Left"},
            {"direction": "forward", "name": "Forward"},
            {"direction": "right", "name": "Right"},
        ],
        "hold_forward": False,
        "start_pos": {"x": -45, "z": 49, "yaw": 90.0, "pitch": -58.5},
        "spray_plots": [],
        "spray_interval": 0,
    },
    "cactus": {
        "name": "Cactus Farm",
        "description": "Right-forward-left-forward pattern",
        "yaw": 90.0,
        "pitch": 5.5,
        "max_speed": 478,
        "tool_id": "CACTUS_KNIFE",
        "pattern": _repeat(("right", "forward", "left", "forward"), 8)
        + [
            {"direction": "right", "name": "Right"},
            {"direction": "forward", "name": "Forward"},
        ],
        "hold_forward": False,
        "start_pos": {"x": -45, "z": 49, "yaw": 90.0, "pitch": 5.5},
        "spray_plots": [],
        "spray_interval": 0,
    },
    "flower": {
        "name": "Sunflower/Moonflower Farm",
        "description": "Left-backward alternating",
        "yaw": -135.0,
        "pitch": 10.0,
        "max_speed": 328,
        "tool_id": "THEORETICAL_HOE_SUNFLOWER",
        "pattern": _repeat(("left", "backward"), 5),
        "hold_forward": False,
        "start_pos": {"x": -148, "z": 238, "yaw": -135.0, "pitch": 10.0},
        "spray_plots": [23, 17, 10, 15, 21],
        "spray_interval": 3,
    },
}


from farm.utils import cecho, SUCCESS, WARN, ERROR, DETAIL, GOLD, AQUA


def load_profile(profile_name: str) -> dict | None:
    """โหลด profile ตามชื่อ คืน None ถ้าไม่พบ"""
    if profile_name not in FARM_PROFILES:
        cecho(f"❌ Profile '{profile_name}' not found!", ERROR)
        cecho(f"Available: {', '.join(FARM_PROFILES)}", DETAIL)
        return None
    return FARM_PROFILES[profile_name]
