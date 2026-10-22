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

DEBUG_TIMING = False   # True = แสดงเวลาที่ใช้ในแต่ละ step/plot ในแชท (ไว้หาคอขวด)
CHAT_QUIET   = True    # ซ่อนข้อความรายละเอียด (สีเทา/ฟ้า: เดินเลน, สลับชุด, บิน ฯลฯ) เหลือแค่เรื่องสำคัญ/เตือน/error

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
MAINTENANCE_CHECK_INTERVAL = 1.0   # ระหว่างเดิน เช็คทุกกี่วินาทีว่าถึงเวลารับบัฟ/สเปรย์ (ถึงแล้วหยุดกลางเลนไปทำทันที)
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
PEST_PROGRESS_EXTEND  = 12.0   # ฆ่า pest ได้ 1 ตัว → ต่อเวลาใน plot นี้ให้อีกกี่วินาที (log จริง: ~4 วินาทีต่อตัว)
PEST_PLOT_MAX_SECONDS = 90.0   # เพดานเวลาต่อ plot ไม่ว่าฆ่าได้กี่ตัว (กันค้างไม่รู้จบ)
PEST_APPEAR_TIMEOUT   = 1.5    # รอ entity ของ pest โหลดหลัง /plottp

# --- Failsafe: เจอเหตุผิดปกติที่เหมือนการตรวจ macro → หยุดบอททันที (ไม่ตอบสนองแทนผู้เล่น) ---
FAILSAFE_ENABLED              = True
FAILSAFE_GUI_ENABLED          = False  # ตรวจ GUI ที่โผล่เอง (ทั้งแบบค้างและแว็บ) ปิดไว้ตามที่สั่ง
FAILSAFE_JUMP_BLOCKS          = 4.0   # ตำแหน่งกระโดดเกินกี่บล็อกระหว่างสองการอ่านติดกัน ถือว่าถูกวาร์ป/ดึง (เดินเต็มที่ ~6 บล็อก/วินาที)
FAILSAFE_MAX_GAP_SECONDS      = 0.4   # ถ้าสองการอ่านห่างกันเกินนี้ (loop สะดุด) ไม่เทียบกัน กันตรวจผิดจากการสะดุด
FAILSAFE_SCREEN_POLLS         = 3     # GUI เปิดติดกันกี่รอบ (×0.1 วินาที) ที่สคริปต์ไม่ได้สั่ง
FAILSAFE_ROTATION_DEGREES     = 15.0  # มุมกล้อง (yaw/pitch) เปลี่ยนเกินกี่องศาในรอบเดียวที่สคริปต์ไม่ได้สั่ง = ถูกหันหัวบังคับ
FAILSAFE_GRACE_SECONDS        = 1.5   # ต้องอยู่ในโหมดฟาร์มปกติต่อเนื่องกี่วินาที ถึงเริ่มนับ GUI แว็บ (กัน GUI ของสคริปต์เอง)
FAILSAFE_BEDROCK_CHECK_SECONDS = 1.0  # ตรวจ bedrock รอบตัวทุกกี่วินาที
FAILSAFE_BEDROCK_MIN_BLOCKS   = 7     # ต้องเจอ bedrock อย่างน้อยกี่ตำแหน่งจาก 9 จุด (4 ทิศ × เท้า/หัว + เหนือหัว) ถึงถือว่า "โดนล้อม"
                                      # (ฟาร์มที่อยู่ติดขอบ bedrock ตามปกติจะเจอแค่ 1-3 จุด)

# --- Input: ให้คลิกซ้ายค้างทำงานต่อเนื่อง ---
FARM_TOOL_SLOT          = 0      # hotbar slot ของเครื่องมือฟาร์ม (hoe) ที่ต้องถือเสมอตอนฟาร์ม
RESTORE_LOOK_STEPS      = 6      # หันกล้องกลับตาม profile หลังจบ action กี่ step
RESTORE_SETTLE          = 0.1    # รอสั้น ๆ ระหว่างขั้นตอนของ restore_farm_state
AUTO_REGRAB_MOUSE        = True  # ถ้าหน้าต่างเกม active แต่เมาส์ไม่ถูกจับ (ต้องคลิกเอง) ให้เกมจับเมาส์คืนเอง
AUTO_ATTACK_UNFOCUSED    = True  # เมาส์ไม่ถูกจับ (หน้าต่างไม่ได้ focus) ก็ให้เกมทุบบล็อกที่เล็งอยู่ต่อเอง ตราบที่บอทกดโจมตีค้างอยู่
ATTACK_TICK_MS           = 50    # ความถี่ทุบบล็อก (ms) เท่ากับ 1 tick ของเกม
REGRAB_STABLE_FRAMES     = 30    # ต้องอยู่ในสถานะนั้นต่อเนื่องกี่เฟรมก่อนจับคืน (กันชนกับช่วงเปลี่ยนโฟกัส)
REFOCUS_GRACE_SECONDS    = 2.0   # เพิ่งกลับมา focus (เกมรีเซ็ตปุ่มที่กดค้าง) ภายในกี่วินาที ถ้าหยุดเดินช่วงนี้ไม่นับว่าชนกำแพง
ATTACK_REASSERT_INTERVAL = 0.5   # กดคลิกซ้ายค้างซ้ำทุกกี่วินาทีระหว่างเดิน (กันสถานะปุ่มหลุดเงียบ ๆ)
INPUT_MONITOR_ENABLED    = False # แจ้งเตือนเมื่อเมาส์ไม่ถูกจับ/หน้าต่างเกมไม่ active ระหว่างฟาร์ม

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