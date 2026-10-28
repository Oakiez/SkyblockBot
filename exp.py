# -*- coding: utf-8 -*-
"""\\exp — ตัวเรียกคำสั่ง (Minescript หาคำสั่งจากไฟล์ .py ที่อยู่ระดับบนสุดของโฟลเดอร์ minescript เท่านั้น)
โค้ดจริงอยู่ที่ exp/table.py
"""
import os
import runpy

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    runpy.run_path(os.path.join(here, "exp", "table.py"), run_name="__main__")
