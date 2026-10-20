# -*- coding: utf-8 -*-
"""
farm.py — Entry point สำหรับ Auto Farm Bot
วางไฟล์นี้ไว้ที่ /minescript/farm.py
วางโฟลเดอร์ farm/ ไว้ที่ /minescript/farm/

Usage: \\farm [profile]
Example: \\farm wheat
"""

import sys
from farm.profiles import FARM_PROFILES
from farm.farm_loop import auto_farm
from farm.utils import safe_echo

if len(sys.argv) < 2:
    safe_echo("\n=== Available Farm Profiles ===\n")
    for key, cfg in FARM_PROFILES.items():
        safe_echo(f"  {key:12s} - {cfg['description']}")
    safe_echo("\nUsage:   \\farm [profile]")
    safe_echo("Example: \\farm wheat\n")
else:
    auto_farm(sys.argv[1].lower())
