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
# การแจ้งเตือน Discord / สั่งการจากมือถือ / ต่อเซิร์ฟเวอร์ใหม่: ตั้งค่าที่ botkit/settings.py (ค่าลับอยู่ farm/secrets_local.py)
RECONNECT_WORLD_SETTLE_SECONDS = 8.0   # ต่อเซิร์ฟเวอร์สำเร็จแล้วรอให้โลกโหลดกี่วินาทีก่อนพิมพ์คำสั่ง
RECONNECT_REJOIN_COMMANDS = (("/skyblock", 10.0), ("/warp garden", 6.0))   # (คำสั่ง, รอหลังพิมพ์กี่วินาที) ตามลำดับ
RECONNECT_RESUME_FARM = True           # ต่อสำเร็จแล้วเริ่มฟาร์มต่อเอง (เฉพาะถ้าตอนหลุดบอททำงานอยู่ และไม่ได้ถูก failsafe/คำสั่งหยุด)

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
CHAT_SOURCE           = "eventlib"  # แหล่งข้อความแชทจากเซิร์ฟเวอร์ (chat listener ปกติของ Minescript ไม่ส่งข้อความระบบมา):
                                    #   "eventlib" = chat listener ของ system/lib/lib_event.py (อ่านแชทบนจอโดยตรง) โหลดไม่ขึ้นจะถอยไปใช้ "log"
                                    #   "log"      = อ่าน logs/latest.log (farm/chatlog.py)
LIB_EVENT_LOAD_TIMEOUT = 5.0   # รอ lib_event ต่อกับสคริปต์ในเกมได้ไม่เกินกี่วินาที (เกินนี้ถอยไปใช้ log)
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
PEST_AIM_STEPS        = 5      # หันไปหา pest ก่อนวาร์ปแบบ smooth กี่ step
PEST_AIM_DELAY        = 0.03   # เว้นแต่ละ step (5 × 0.03 ≈ 0.15 วินาทีต่อการวาร์ป)
PEST_TRACK_MAX_DEGREES = 20.0  # ตอนดูด หันตาม pest ได้ไม่เกินกี่องศาต่อ tick (20 ต่อ 0.05 วินาที ≈ 400°/วินาที) มาก = เร็ว/แข็ง น้อย = นุ่ม/ตามช้า
PEST_WALK_MAX_ANGLE   = 30.0   # หันห่างจากเป้าเกินกี่องศายังไม่เดินเข้าหา (กันเดินผิดทางระหว่างหัน)
VACUUM_TICK           = 0.05   # รอบอัปเดตตอนดูด
PEST_PROGRESS_EXTEND  = 12.0   # ฆ่า pest ได้ 1 ตัว → ต่อเวลาใน plot นี้ให้อีกกี่วินาที (log จริง: ~4 วินาทีต่อตัว)
PEST_PLOT_MAX_SECONDS = 90.0   # เพดานเวลาต่อ plot ไม่ว่าฆ่าได้กี่ตัว (กันค้างไม่รู้จบ)
PEST_APPEAR_TIMEOUT   = 1.5    # รอ entity ของ pest โหลดหลัง /plottp

# --- Failsafe: เจอเหตุผิดปกติที่เหมือนการตรวจ macro → หยุดบอททันที (ไม่ตอบสนองแทนผู้เล่น) ---
FAILSAFE_ENABLED              = True
FAILSAFE_GUI_ENABLED          = False  # ตรวจ GUI ที่โผล่เอง (ทั้งแบบค้างและแว็บ) ปิดไว้ตามที่สั่ง
FAILSAFE_JUMP_BLOCKS          = 4.0   # ตำแหน่งกระโดดเกินกี่บล็อกระหว่างสองการอ่านติดกัน ถือว่าถูกวาร์ป/ดึง (เดินเต็มที่ ~6 บล็อก/วินาที)
FAILSAFE_MAX_GAP_SECONDS      = 0.4   # ถ้าสองการอ่านห่างกันเกินนี้ (loop สะดุด) ไม่เทียบกัน กันตรวจผิดจากการสะดุด
# เน็ตกระตุก (ปิงสูง) ทำให้เซิร์ฟเวอร์ดึงตัวละครกลับมาจุดที่เพิ่งเดินผ่าน (rubber-band) ต่างจากการถูกวาร์ปจริงที่ไปโผล่ที่ใหม่
# ถ้าตำแหน่งใหม่ตรงกับจุดที่เพิ่งผ่านมาในช่วง FAILSAFE_HISTORY_SECONDS และกระโดดไม่เกิน FAILSAFE_RUBBERBAND_MAX_BLOCKS → ไม่ถือเป็น failsafe
FAILSAFE_RUBBERBAND_ENABLED   = True
FAILSAFE_HISTORY_SECONDS      = 8.0   # จำเส้นทางที่เดินผ่านย้อนหลังกี่วินาที (ปิงสูงมาก = ถูกดึงกลับไปไกลในเวลา เพิ่มได้)
FAILSAFE_RUBBERBAND_TOLERANCE = 2.0   # ตำแหน่งใหม่ห่างจากจุดที่เคยผ่านไม่เกินกี่บล็อก ถึงนับว่า "กลับมาจุดเดิม"
FAILSAFE_RUBBERBAND_MAX_BLOCKS = 30.0  # ถูกดึงกลับไกลเกินนี้ถือเป็นการวาร์ปจริงเสมอ
FAILSAFE_RUBBERBAND_GRACE     = 1.0   # หลังถูกดึงกลับ ข้ามการตรวจมุมกล้องกี่วินาที (เซิร์ฟเวอร์อาจรีเซ็ตมุมพร้อมกัน)
FAILSAFE_RUBBERBAND_LIMIT     = (12, 30.0)  # (ครั้ง, วินาที) ถูกดึงกลับถี่เกินนี้ = เน็ตแย่เกินจะฟาร์มได้ → หยุด  (0, ... ) = ไม่หยุดไม่ว่าถี่แค่ไหน
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
ATTACK_RELEASE_SECONDS   = 0.12  # หลังจับเมาส์คืน ปล่อยปุ่มตีนานเท่านี้ (> 1 tick = 0.05s) เพื่อล้าง missTime ของเกม
ATTACK_REASSERT_INTERVAL = 0.5   # กดคลิกซ้ายค้างซ้ำทุกกี่วินาทีระหว่างเดิน (กันสถานะปุ่มหลุดเงียบ ๆ)
INPUT_MONITOR_ENABLED    = False # แจ้งเตือนเมื่อเมาส์ไม่ถูกจับ/หน้าต่างเกมไม่ active ระหว่างฟาร์ม

# --- Sensors / Watchdog / Metrics ---
SENSOR_POLL_INTERVAL   = 0.05   # poller อ่านตำแหน่งทุกกี่วินาที
SENSOR_MAX_AGE         = 0.3    # cache เก่ากว่านี้ให้อ่านตรงแทน
WATCHDOG_ENABLED       = True
WATCHDOG_STUCK_SECONDS = 30.0   # ตำแหน่งไม่ขยับนานเท่านี้ขณะฟาร์ม = ค้าง → กู้คืน
METRICS_WRITE_CSV      = False  # True = เขียน farm/metrics.csv ทุกครั้ง (สรุปในแชทตอนจบ session มีเสมอ)

# --- HUD: แผงสถานะบนจอ (ใช้ system/lib/lib_ren.py) ---
HUD_ENABLED         = True
HUD_ANCHOR          = "right"  # "right" = ชิดขวาบน, "left" = ชิดซ้ายบน
HUD_X               = 4      # ระยะห่างจากขอบจอฝั่งที่ชิด (หน่วย GUI pixel ที่ scale แล้ว)
HUD_Y               = 4      # ระยะห่างจากขอบบน (ถ้าทับไอคอน potion effect มุมขวาบน ให้เพิ่มเป็น ~52)
HUD_UPDATE_INTERVAL = 0.5    # อัปเดตแผงทุกกี่วินาที

AMOUNT_OF_PESTS = 4
FLY_HEIGHT      = 79.0
VACUUM_SLOT     = 2   # hotbar slot ของ vacuum

# ============================================================
# SELLING
# ============================================================

SELL_AFTER_ROUND = True
SELL_ALL_VINYLS = True   # True = ขาย vinyl ทุกแบบ (music disc ทุกแผ่น + ไอเท็มที่รหัสขึ้นต้น VINYL_) ไม่ต้องไล่ใส่ทีละตัวใน SELL_ITEMS
                         # False = ขายเฉพาะ VINYL_* ที่ระบุใน SELL_ITEMS เท่านั้น

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