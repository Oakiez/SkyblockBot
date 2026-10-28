# -*- coding: utf-8 -*-
"""\\mining — ตัวเรียกคำสั่ง (Minescript หาคำสั่งจากไฟล์ .py ที่อยู่ระดับบนสุดของโฟลเดอร์ minescript เท่านั้น)
โค้ดจริงอยู่ที่ mining/automine.py
"""
import os
import runpy

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    runpy.run_path(os.path.join(here, "mining", "automine.py"), run_name="__main__")
