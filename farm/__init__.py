# -*- coding: utf-8 -*-
"""
farm/__init__.py — Entry point

Usage: \\farm [profile]
Example: \\farm wheat
"""

import sys
from farm.profiles import FARM_PROFILES
from farm.farm_loop import auto_farm
from farm.utils import cecho, SUCCESS, WARN, ERROR, DETAIL, GOLD, AQUA

if __name__ == "__main__":
    if len(sys.argv) < 2:
        cecho("\n=== Available Farm Profiles ===\n", GOLD)
        for key, cfg in FARM_PROFILES.items():
            cecho(f"  {key:12s} - {cfg['description']}", DETAIL)
        cecho("\nUsage:   \\farm [profile]", AQUA)
        cecho("Example: \\farm wheat\n", AQUA)
    else:
        auto_farm(sys.argv[1].lower())
