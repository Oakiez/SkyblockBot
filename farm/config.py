# -*- coding: utf-8 -*-
"""
config.py — ค่า configuration ทั้งหมด แก้ได้จากที่นี่ที่เดียว
"""

# ============================================================
# DISCORD
# ============================================================

try:
    from farm.secrets_local import DISCORD_WEBHOOK_URL  # ไฟล์ลับ ไม่ commit
except ImportError:
    DISCORD_WEBHOOK_URL = ""
SCREENSHOT_INTERVAL = 5   # ถ่าย screenshot ทุกกี่ rounds (0 = ปิด)

# ============================================================
# KEY BINDINGS
# ============================================================

PAUSE_KEY = 91       # [ key
START_STOP_KEY = 93  # ] key

# ============================================================
# FARMING
# ============================================================

AUTO_UNPAUSE_SECONDS  = 30

# ============================================================
# TIMING / TUNING — ค่าที่กำหนดความเร็วของบอท (หน่วยวินาที)
# ปรับที่นี่ที่เดียว ไม่ต้องไล่แก้ในโค้ด
# ============================================================

DEBUG_TIMING = True    # เปิดไว้ก่อนจนกว่าจะหาคอขวดเจอ   # True = แสดงเวลาที่ใช้ในแต่ละ step/ขั้นตอน pest ในแชท

# --- Harvest loop: ตรวจว่าชนกำแพง (stuck) ---
STUCK_CHECK_INTERVAL  = 0.1    # เช็คตำแหน่งทุกกี่วินาที
STUCK_CHECK_THRESHOLD = 0.125  # ระยะขั้นต่ำต่อ 1 check (≈1.25 บล็อก/วินาที)
STUCK_CHECK_COUNT     = 3      # เช็คติดกันกี่ครั้งถึงนับว่าชนกำแพง (3 × 0.1 = 0.3 วินาที)
STEP_END_DELAY        = 0.05   # รอหลังหยุดเดินก่อนเริ่ม step ถัดไป

# --- Pest ---
PEST_COOLDOWN_TRIGGER_SECONDS = 5   # SkyHanni แจ้ง "cooldown expires in Ns" ที่ 5s → สลับ Pest loadout เมื่อเหลือ ≤ ค่านี้
FLY_BACKOFF_SECONDS   = 0.3    # ถอยหลังก่อนบิน (ให้พ้นบล็อกที่ติดหัวหลัง /plottp) ถ้ายังบินไม่ขึ้นให้เพิ่ม
TAB_BRIDGE_INTERVAL_MS = 250   # สคริปต์ในเกมส่งค่า tablist (Alive/Plots) ทุกกี่มิลลิวินาที
TAB_BRIDGE_MAX_AGE    = 3.0    # ค่าจาก bridge เก่ากว่านี้ไม่เชื่อ (วินาที)
CHATLOG_ENABLED       = True   # อ่านแชทจาก logs/latest.log (เพราะ chat listener ไม่ส่งข้อความเซิร์ฟเวอร์มา)
TABLIST_SLOW_WARN     = 1.0    # อ่าน tablist นานเกินกี่วินาทีให้เตือนในแชท
PEST_CHECK_INTERVAL   = 1.0    # เช็คจำนวน pest จาก tablist ทุกกี่วินาทีระหว่างเดิน
OUTFIT_WAIT_TIMEOUT   = 10.0   # รอสลับ loadout เสร็จก่อนไปกำจัด pest ไม่เกินกี่วินาที
ENTITY_SCAN_INTERVAL  = 0.15   # สแกน entity (หนัก) ทุกกี่วินาทีตอน vacuum
ENTITY_SCAN_RANGE     = 120    # รัศมีสแกนหา pest (บล็อก) plot กว้าง ~95
PLOT_TP_SETTLE        = 0.4    # รอหลัง /plottp
PLOT_LAND_SNEAK       = 0.6    # sneak ลงพื้นหลัง /plottp ก่อนบินขึ้น

# --- Spray: ตั้งเวลาตามจริง (แทนนับรอบ) ---
# บัฟ Phillip อยู่ 30 นาที และกดรับซ้อนไม่ได้จนกว่าจะหมด (ต่างจาก spray ที่ spray ทับได้)
BUFF_EVERY_SECONDS    = 30 * 60 + 10  # +10 วินาทีเผื่อ lag ไม่งั้นไปกดตอนบัฟยังไม่หมด 0 = ปิดการรับบัฟ
BUFF_RETRY_SECONDS    = 120           # ถ้ารับบัฟพลาด (เดินไปไม่ถึง NPC) ลองใหม่อีกกี่วินาที
SPRAY_EVERY_SECONDS   = 55 * 60  # สเปรย์ใหม่ทุกกี่วินาที (บัฟนาน 1 ชม.) 0 = ใช้ spray_interval (นับรอบ) ของ profile

# --- Pest: โหมด warp (AOTV คลิกขวา = วาร์ปไปทางที่หัน) ---
PEST_USE_WARP         = True   # False = โหมดเดิม (บินขึ้น + ไล่)
WARP_SLOT             = 1      # hotbar slot ของ AOTV
WARP_MIN_DISTANCE     = 12.0   # ไกลกว่านี้ให้วาร์ปเข้าไปก่อน (ระยะวาร์ปต่อครั้งของ AOTV)
WARP_MAX_PER_PEST     = 8      # วาร์ปได้สูงสุดกี่ครั้งต่อ pest หนึ่งตัว (กันวนไม่รู้จบ)
WARP_SELECT_DELAY     = 0.08   # รอหลังเปลี่ยน slot ก่อนคลิก
WARP_SETTLE_TIMEOUT   = 0.6    # รอให้ตำแหน่งเปลี่ยนหลังวาร์ป ไม่เกินกี่วินาที
VACUUM_REACH          = 5.0    # ใกล้กว่านี้ถึงหยุดเดินแล้วดูดอยู่กับที่
VACUUM_TICK           = 0.05   # รอบอัปเดตตอนดูด
PEST_APPEAR_TIMEOUT   = 1.5    # รอ entity ของ pest โหลดหลัง /plottp

# --- Sensors / Watchdog / Metrics ---
SENSOR_POLL_INTERVAL   = 0.05   # poller อ่านตำแหน่งทุกกี่วินาที
SENSOR_MAX_AGE         = 0.3    # cache เก่ากว่านี้ให้อ่านตรงแทน
WATCHDOG_ENABLED       = True
WATCHDOG_STUCK_SECONDS = 30.0   # ตำแหน่งไม่ขยับนานเท่านี้ขณะฟาร์ม = ค้าง → กู้คืน
METRICS_WRITE_CSV      = False  # True = เขียน farm/metrics.csv ทุกครั้ง (สรุปในแชทตอนจบ session มีเสมอ)

AMOUNT_OF_PESTS = 4
FLY_HEIGHT      = 79.0
VACUUM_SLOT     = 2   # hotbar slot ของ vacuum

# ============================================================
# SELLING
# ============================================================

SELL_AFTER_ROUND = True

SELL_ITEMS = [
    "OVERCLOCKER_3000",
    "TOOL_EXP_CAPSULE",
    "VINYL_IMAGINE_DRAGONFLIES",
    "VINYL_SLOW_AND_GROOVY",
    "VINYL_EARTHWORM_ENSEMBLE",
    "VINYL_CICADA_SYMPHONY",
    "VINYL_BUZZIN_BEATS",
    "RAREFINDER_GARDEN_CHIP",
    "WRIGGLING_LARVA",
    "BOOKWORM_BOOK",
    "MANTID_CLAW",
    "FIRE_IN_A_BOTTLE",
    "CLIPPED_WINGS",
    "CHIRPING_STEREO",
    "BEADY_EYES",
    "ATMOSPHERIC_FILTER",
]

# ============================================================
# LOADOUT (/ld) — slot ในหน้าจอ loadout
# ============================================================

FARM_LOADOUT_SLOT = 15
PEST_LOADOUT_SLOT = 14

# ============================================================
# PEST
# ============================================================

PEST_PLOT_TIMEOUT = 20.0