# -*- coding: utf-8 -*-
"""
metrics.py — จับเวลาแต่ละขั้นตอน (step / plot / round ฯลฯ) เพื่อดูว่าตรงไหนช้า
"""

import csv
import os
import time

from farm.config import METRICS_WRITE_CSV

_stats: dict = {}
_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metrics.csv")


def record(kind: str, seconds: float, name: str = "") -> None:
    n, total = _stats.get(kind, (0, 0.0))
    _stats[kind] = (n + 1, total + seconds)
    if METRICS_WRITE_CSV:
        try:
            with open(_CSV_PATH, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([int(time.time()), kind, name, round(seconds, 3)])
        except OSError:
            pass


def summary_lines() -> list:
    return [
        f"{kind}: n={n} avg={total / n:.2f}s total={total:.0f}s"
        for kind, (n, total) in sorted(_stats.items())
        if n
    ]


def reset() -> None:
    _stats.clear()
