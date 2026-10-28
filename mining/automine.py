"""
AutoMine v2 - Full Optimized Edition
Performance improvements over previous version:
- VISIBILITY: Batch ray-cast across all candidate blocks in ONE getblocklist call
              + dedup ray positions with set (~80% fewer API calls)
- CLUSTER: deque.popleft() O(1) instead of list.pop(0) O(n)
           + pre-sort by distance before clustering
- BUG FIX: target_bases / target_set NameError on ignore_state branches
- MISC: player_position() cached per loop, not called multiple times
"""

from system.lib import minescript
from collections import deque
import math
import time
import random
import re
import threading

from botkit.link import BotLink
from botkit.reconnect import Reconnector
from botkit.unfocused import UnfocusedAttack
from botkit.discord_io import fmt_duration

# HUD วาดด้วย system/lib/lib_ren.py (import ใน thread แยกตอน start_hud: ตอน import มันรอ socket จากสคริปต์ในเกม)
# ไม่ใช้ minescript_plus แล้ว: มันเรียก exit(1) เมื่อไม่มี mappings ของเวอร์ชันเกม (26.2 ไม่มี)

# ============================================
# CONFIGURATION
# ============================================
CONFIG = {
    "toggle_key": 93,   # ] เปิด/ปิด
    "pause_key": 91,    # [ พัก/ต่อ
    "target_block": [
        "minecraft:light_blue_wool",
        "minecraft:cyan_terracotta",
        "minecraft:gray_wool",
        "minecraft:dark_prismarine",
        "minecraft:prismarine_bricks",
        "minecraft:prismarine",
        "minecraft:polished_diorite",
    ],
    "ignore_block_state": False,
    "search_distance": 4.5,
    # --- Rotation (Fitts' law + minimum-jerk, ดัดแปลงจาก Philogex/Minescript-Miner, MIT) ---
    # เวลาหัน = a + b * log2(มุมที่ต้องหัน / ความกว้างเชิงมุมของเป้า + 1)
    # เป้าใหญ่/ใกล้ หันเร็ว, เป้าเล็ก/ไกล/โดนบังเกือบหมด หันช้าลง เหมือนคนเล็ง
    "rotation_fitts_a": 0.08,         # วินาที
    "rotation_fitts_b": 0.11,         # วินาที ต่อ 1 bit ของความยาก
    "rotation_duration_min": 0.06,
    "rotation_duration_max": 0.55,
    "rotation_steps_per_second": 80,
    "rotation_steps_min": 12,
    "rotation_snap_threshold": 1.8,
    "rotation_human_variance": 0.04,
    # --- Aim point (เล็งจุดที่มองเห็นบนหน้าบล็อก แทนจุดกลางบล็อก) ---
    "reach_distance": 4.5,            # ระยะเอื้อมจากตา (บล็อก) จุดเล็งต้องอยู่ในระยะนี้
    "aim_face_inset": 0.2,            # จุดสุ่มบนหน้าบล็อกห่างขอบเท่านี้ (0.5 = กลางหน้าเท่านั้น)
    "aim_edge_penalty_deg": 3.0,      # จุดที่ไม่ใช่กลางหน้า ถูกนับว่าไกลขึ้นกี่องศา (ชอบกลางหน้าถ้าพอ ๆ กัน)
    # --- Timing ---
    "block_cooldown": 0.03,
    "break_delay": 0.03,
    # --- Mining ---
    "break_blocks": True,
    "break_hold_time": 1.2,
    "break_until_bedrock": True,
    "break_timeout": 3.5,
    "break_poll_rate": 0.02,
    # --- Scan ---
    "scan_cache_move_threshold": 0.8,
    "scan_cache_max_age": 1.5,
    # --- Visibility batch ---
    # How many top candidates to batch-check visibility for each loop.
    "visibility_batch_size": 12,
    # --- Cluster ---
    "use_cluster_mode": True,
    "cluster_distance": 1.5,
    # --- Obstructed TTL ---
    "obstructed_ttl": 4.0,
    # --- Targeting ---
    "targeting_retries": 2,
    "targeting_retry_delay": 0.02,
    "mining_target_check_interval": 0.1,  # ระหว่างขุด เช็คทุกกี่วินาทีว่ากล้องยังเล็งบล็อกเดิม
    "mining_target_lost_checks": 2,       # เล็งหลุดติดกันกี่ครั้งถึงเลิกขุดแล้วหาเป้าใหม่
    # --- ต่อเซิร์ฟเวอร์ใหม่เมื่อหลุด (ตัวหลักตั้งที่ botkit/settings.py) ---
    "reconnect_settle_seconds": 8.0,  # ต่อสำเร็จแล้วรอให้โลกโหลดกี่วินาทีก่อนพิมพ์คำสั่ง
    # (คำสั่ง, รอหลังพิมพ์กี่วินาที) ที่พิมพ์หลังต่อสำเร็จ ผมไม่รู้ว่าคุณขุดที่ไหน ถ้ามี warp ไปจุดขุดเพิ่มเข้าไปเอง เช่น ("/warp mines", 6.0)
    "reconnect_commands": (("/skyblock", 10.0),),
    "reconnect_resume": False,        # ต่อสำเร็จแล้วเริ่มขุดต่อเอง (เปิดเมื่อคำสั่งข้างบนพาไปจุดขุดเดิมเป๊ะ ๆ เท่านั้น)
    # --- Safety stops ---
    # ขุดต่อได้แม้หน้าต่างเกมไม่โฟกัส (alt-tab): เกมทุบบล็อกเฉพาะตอนเมาส์ถูกจับ จึงส่งสคริปต์เข้าเกมไปทุบแทน
    # (botkit/unfocused.py) ต้องปิด pauseOnLostFocus ใน options.txt / F3+P ไม่งั้นเกมเปิดเมนู Pause แล้วสคริปต์หยุดเอง
    # ห้ามรันพร้อม farm (ทั้งคู่ทุบบล็อกแทนเกม จะทุบซ้ำ)
    "mine_unfocused": True,
    "unfocused_attack_tick_ms": 50,   # ความถี่ทุบตอนไม่โฟกัส (ms) เท่ากับ 1 tick ของเกม
    # pause เมื่อหน้าต่างไม่โฟกัส: ปิดไว้เพราะขุดตอนไม่โฟกัสได้แล้ว (ถ้าสคริปต์ในเกมต่อไม่ติด จะ pause ให้เองเป็นตัวสำรอง)
    "pause_on_focus_loss": False,
    "stop_on_world_change": True,     # เปลี่ยนโลก/เซิร์ฟเวอร์/หลุด → ปิดสคริปต์
    "stop_on_teleport": True,         # ตำแหน่งกระโดดผิดปกติ (สคริปต์ไม่เดินเอง) → ปิดสคริปต์
    "teleport_stop_distance": 6.0,    # บล็อก
    # --- Instant neighbor scan (จับ block ที่เกิดใหม่ทันที เช่น titanium หลัง mithril) ---
    "instant_neighbor_check": True,
    # --- HUD / Debug ---
    "debug": True,
    "hud_enabled": True,
    "hud_anchor": "right",            # "right" = ชิดขวาบน, "left" = ชิดซ้ายบน
    "hud_x": 4,                       # ระยะห่างจากขอบจอฝั่งที่ชิด (GUI pixel)
    "hud_y": 4,                       # ระยะห่างจากขอบบน (ทับไอคอน potion effect ให้เพิ่มเป็น ~52)
    "hud_update_interval": 0.25,
    "hud_message_seconds": 4.0,       # ข้อความ debug ล่าสุดโชว์ในแผงกี่วินาที
    # --- Skill ---
    "enable_skill": True,
    # ตรวจว่าสกิลพร้อมจากข้อความในแชท (เช่น "Pickobulus is now available!") แทนการนับคูลดาวน์เอง
    # ต้องใช้ system/lib/lib_event.py ถ้าโหลดไม่ขึ้นจะถอยไปนับ skill_interval แทน
    "skill_use_chat_detect": True,
    "skill_ready_text": "Pickobulus is now available",   # ข้อความที่บอกว่าพร้อม (ไม่สนตัวพิมพ์เล็ก/ใหญ่ และสีของข้อความ)
    "skill_react_delay": (0.2, 0.8),  # หน่วงสุ่มหลังเห็นข้อความก่อนกด (วินาที)
    "skill_chat_timeout": 60.0,       # กดแล้วไม่เห็นข้อความพร้อมนานเกินนี้ ลองกดใหม่ (กันค้างถ้ากดตอนยังคูลดาวน์/พลาดข้อความ)
    "lib_event_load_timeout": 5.0,    # รอ lib_event ต่อกับเกมได้ไม่เกินกี่วินาที
    # --- โหมดสำรอง (นับเวลาเอง) ใช้เมื่อไม่ได้ตรวจจากแชท ---
    "skill_interval": 40.0,          # = คูลดาวน์สกิล (วินาที)
    "skill_hold_time": 0.3,
    "skill_random_variance": 2.0,    # หน่วงเพิ่มแบบสุ่ม 0..ค่านี้ (บวกเท่านั้น ไม่กดก่อนคูลดาวน์หมด)
    # --- Idle movement (safe: crouch + look_around only, ไม่ขยับตัว) ---
    "idle_movement_enabled": True,
    "idle_every_blocks": (8, 18),        # trigger ทุกกี่บล็อก (random range)
    "idle_weights": {"crouch": 55, "look_around": 45},
    "idle_crouch_duration": (0.4, 1.3),  # วินาทีที่นั่งยอง
    "idle_look_yaw_range":   (-30, 30),  # degrees หันซ้าย/ขวา
    "idle_look_pitch_range": (-12, 12),  # degrees หันขึ้น/ลง
    # --- Player detection ---
    "player_detection_enabled": True,
    "player_detection_radius": 20.0,   # blocks
    "player_detection_pause": True,    # pause อัตโนมัติเมื่อเจอ player
    "player_detection_resume": True,   # resume อัตโนมัติเมื่อ player ออกไป
    "player_detection_interval": 2.0,  # เช็คทุกกี่วินาที
}
# ============================================

PASSABLE_BLOCKS = {
    "minecraft:air", "minecraft:cave_air", "minecraft:void_air",
    "minecraft:water", "minecraft:lava", "minecraft:vine", "minecraft:web",
    "minecraft:grass", "minecraft:tall_grass", "minecraft:large_fern",
    "minecraft:torch", "minecraft:wall_torch", "minecraft:snow",
    "minecraft:grass_block", "minecraft:fern", "minecraft:sea_grass",
    "minecraft:kelp", "minecraft:seagrass",
}

# ===== Globals =====
_link = None                  # BotLink (Discord) ตั้งใน main()
_unfocused = None             # UnfocusedAttack (ขุดตอนไม่โฟกัส) ตั้งใน main()
_reconnector = None
_session_started = 0.0
_hud_ready = False            # True เมื่อ lib_ren โหลดเสร็จและแผงกำลังวาด (ก่อนนั้น/โหลดไม่ขึ้น debug ไปที่แชท)
_hud_stop = threading.Event()
_hud_draw_lock = threading.Lock()
_hud_renderer = None
_hud_last_msg = ("", 0.0)     # (ข้อความ, เวลา)
_total_broken = 0
_last_skill_time = 0.0
_skill_chat_active = False    # True = ตรวจสกิลพร้อมจากแชท (lib_event โหลดได้) False = นับเวลาเอง
_skill_ready = True           # โหมดแชท: เริ่มต้นถือว่าพร้อม ลองกดครั้งแรกเลย (ถ้ายังคูลดาวน์อยู่ ข้อความ "available" จะตามมาเอง)
_skill_ready_at = 0.0         # โหมดแชท: เวลาที่เริ่มกดได้ (หลังหน่วงสุ่มจากตอนเห็นข้อความ)
_script_active = False
_script_paused = False

# ----- Scan cache -----
_scan_cache_blocks: list = []
_scan_cache_player_pos = None
_scan_cache_time = 0.0

# ----- Obstructed TTL -----
_obstructed_positions: dict = {}  # { (x,y,z): expire_timestamp }

# ----- Sphere offset cache -----
_sphere_offsets_cache: dict = {}

# ----- Idle movement -----
_blocks_since_idle: int = 0
_next_idle_at: int = 0  # initialized on first block mined

# ----- Player detection -----
_last_player_check: float = 0.0
_player_nearby: bool = False
_auto_paused_by_detection: bool = False  # track ว่า pause มาจาก detection หรือ manual


# =========================================
# SPHERE OFFSETS
# =========================================
def _build_sphere_offsets(max_distance: float) -> list:
    r = int(math.ceil(max_distance))
    r2 = max_distance * max_distance
    offsets = []
    for dx in range(-r, r + 1):
        dx2 = dx * dx
        if dx2 > r2:
            continue
        for dy in range(-r, r + 1):
            dy2 = dy * dy
            if dx2 + dy2 > r2:
                continue
            for dz in range(-r, r + 1):
                if dx2 + dy2 + dz * dz <= r2:
                    offsets.append((dx, dy, dz))
    return offsets


def get_sphere_offsets(max_distance: float) -> list:
    if max_distance not in _sphere_offsets_cache:
        _sphere_offsets_cache[max_distance] = _build_sphere_offsets(max_distance)
    return _sphere_offsets_cache[max_distance]


# =========================================
# OBSTRUCTED TTL
# =========================================
def add_obstructed(pos: tuple):
    _obstructed_positions[pos] = time.time() + CONFIG["obstructed_ttl"]


def is_obstructed(pos: tuple) -> bool:
    expire = _obstructed_positions.get(pos)
    if expire is None:
        return False
    if time.time() > expire:
        del _obstructed_positions[pos]
        return False
    return True


def purge_expired_obstructed():
    now = time.time()
    expired = [p for p, t in _obstructed_positions.items() if now > t]
    for p in expired:
        del _obstructed_positions[p]



# =========================================
# INTERRUPTIBLE SLEEP
# =========================================
_INTERRUPT_CHUNK = 0.02  # ตรวจ state ทุก 20ms

def interruptible_sleep(duration: float):
    """หยุดทันทีเมื่อ disable หรือ pause"""
    deadline = time.time() + duration
    while time.time() < deadline:
        if not _script_active or _script_paused:
            return
        remaining = deadline - time.time()
        time.sleep(min(_INTERRUPT_CHUNK, remaining))


# =========================================
# DISCORD (botkit)
# =========================================
def bk_alert(title: str, description: str = "", level: str = "info", screenshot: bool = False, wait: bool = False):
    """แจ้งเตือน Discord พร้อมสถานะปัจจุบัน (ไม่ทำอะไรถ้ายังไม่ได้ตั้ง link/webhook)"""
    if _link is not None:
        try:
            _link.alert(title, description, level, screenshot, wait=wait)
        except Exception:
            pass


def bk_cancel_reconnect():
    if _reconnector is not None:
        _reconnector.cancel()


# =========================================
# DEBUG / HUD
# =========================================
def debug_msg(text: str):
    """ข้อความสถานะล่าสุด: แผง HUD พร้อมใช้ → โชว์ในแผง (ไม่รกแชท) ไม่งั้นพิมพ์ลงแชท"""
    global _hud_last_msg
    if not CONFIG["debug"]:
        return
    try:
        if _hud_ready:
            _hud_last_msg = (str(text), time.time())
        else:
            minescript.echo(str(text))
    except Exception:
        pass


def summary_update():
    """ตัวนับ Mined: HUD อ่านค่าเองทุกรอบ จึงไม่ต้องทำอะไร ถ้าไม่มี HUD พิมพ์ลงแชทแทน"""
    if _hud_ready:
        return
    try:
        minescript.echo(f"Mined: {_total_broken}")
    except Exception:
        pass


# --- HUD (lib_ren) ---
_HUD_CHAR_W = 6      # ความกว้างตัวอักษรของ font เกมโดยประมาณ (GUI pixel)
_HUD_LINE_H = 10
_HUD_PAD = 4
_HUD_BG = (140, 0, 0, 0)
_HUD_WHITE = (255, 255, 255, 255)
_HUD_GRAY = (255, 170, 170, 170)
_HUD_GOLD = (255, 255, 170, 0)
_HUD_GREEN = (255, 85, 255, 85)
_HUD_YELLOW = (255, 255, 255, 85)
_HUD_COLOR_CODES = re.compile("§.")


def hud_lines() -> list:
    """แต่ละบรรทัด = (ข้อความ, สี)"""
    if not _script_active:
        status, color = "OFF", _HUD_GRAY
    elif _script_paused:
        status, color = "PAUSED", _HUD_YELLOW
    else:
        status, color = "RUNNING", _HUD_GREEN
    lines = [("AutoMine", _HUD_GOLD), (f"Status: {status}", color), (f"Mined: {_total_broken}", _HUD_WHITE)]
    if _unfocused is not None and _unfocused.connected and _unfocused.stats()["active"] is False:
        lines.append(("Mining in background", _HUD_GRAY))

    if CONFIG["enable_skill"]:
        if _skill_chat_active:
            lines.append(("Skill: ready" if _skill_ready else "Skill: cooldown", _HUD_WHITE))
        else:
            left = CONFIG["skill_interval"] - (time.time() - _last_skill_time)
            lines.append(("Skill: ready" if left <= 0 else f"Skill in: {int(left) + 1}s", _HUD_WHITE))

    msg, at = _hud_last_msg
    if msg and time.time() - at <= CONFIG["hud_message_seconds"]:
        lines.append((_HUD_COLOR_CODES.sub("", msg)[:40], _HUD_GRAY))
    return lines


def hud_draw(gui, lines: list, screen_w: int) -> None:
    width = max(len(t) for t, _ in lines) * _HUD_CHAR_W + _HUD_PAD * 2
    height = len(lines) * _HUD_LINE_H + _HUD_PAD * 2 - 2
    x = screen_w - CONFIG["hud_x"] - width if CONFIG["hud_anchor"] == "right" and screen_w > 0 else CONFIG["hud_x"]
    y = CONFIG["hud_y"]
    gui.fill(x, y, x + width, y + height, _HUD_BG)
    for i, (text, color) in enumerate(lines):
        gui.text(text, x + _HUD_PAD, y + _HUD_PAD + i * _HUD_LINE_H, color)


def _hud_loop():
    global _hud_ready, _hud_renderer
    try:
        from system.lib.lib_ren import Renderer   # บล็อกจนสคริปต์ในเกมต่อ socket เสร็จ
        _hud_renderer = Renderer("automine-hud")
    except BaseException as e:   # lib เรียก sys.exit() ถ้าไม่ใช่ Fabric / เวอร์ชันเกมต่ำไป
        try:
            minescript.echo(f"§e[AutoMine] HUD unavailable (lib_ren): {e}")
        except Exception:
            pass
        return
    _hud_ready = True
    while not _hud_stop.is_set():
        try:
            lines = hud_lines()
            with _hud_draw_lock:
                if _hud_stop.is_set():
                    break
                with _hud_renderer.GuiGraphics as gui:   # รอเฟรมก่อน ขนาดจอจึงเป็นค่าล่าสุด
                    hud_draw(gui, lines, _hud_renderer._screen_size[0])
        except Exception as e:
            minescript.echo(f"§e[AutoMine] HUD draw error: {e}")
            time.sleep(2.0)
        _hud_stop.wait(CONFIG["hud_update_interval"])


def start_hud():
    if CONFIG["hud_enabled"]:
        threading.Thread(target=_hud_loop, daemon=True).start()


def stop_hud():
    """หยุดอัปเดตและล้างแผงออกจากจอ"""
    global _hud_ready
    _hud_stop.set()
    _hud_ready = False
    if _hud_renderer is None or not _hud_draw_lock.acquire(timeout=1.0):
        return
    try:
        _hud_renderer.clear()
        _hud_renderer.push_stack()   # ชุดคำสั่งว่าง = ลบแผง
    except Exception:
        pass
    finally:
        _hud_draw_lock.release()




# =========================================
# PLAYER DETECTION
# =========================================
def check_nearby_players(player_pos: tuple) -> list:
    """คืน list of (name, distance) ของ player อื่นที่อยู่ใน radius"""
    try:
        entities = minescript.entities()
    except Exception:
        return []
    if not entities:
        return []

    try:
        my_name = minescript.player().name
    except Exception:
        my_name = None

    px, py, pz = player_pos
    radius_sq = CONFIG["player_detection_radius"] ** 2
    nearby = []
    for e in entities:
        if getattr(e, "type", None) != "minecraft:player":
            continue
        if my_name and getattr(e, "name", None) == my_name:
            continue
        ex, ey, ez = e.position
        dist_sq = (ex - px) ** 2 + (ey - py) ** 2 + (ez - pz) ** 2
        if dist_sq <= radius_sq:
            nearby.append((e.name, round(math.sqrt(dist_sq), 1)))
    return nearby


def maybe_check_players(player_pos: tuple):
    """Throttled — เรียกทุก loop แต่จะ query จริงแค่ทุก detection_interval วินาที"""
    global _last_player_check, _player_nearby, _script_paused, _auto_paused_by_detection

    if not CONFIG["player_detection_enabled"]:
        return

    now = time.time()
    if now - _last_player_check < CONFIG["player_detection_interval"]:
        return
    _last_player_check = now

    nearby = check_nearby_players(player_pos)

    if nearby and not _player_nearby:
        # มี player เข้ามาใหม่
        _player_nearby = True
        names = ", ".join(f"§e{n}§f ({d}m)" for n, d in nearby)
        minescript.echo(f"§c[AutoMine] ⚠ Player nearby: {names}")
        bk_alert("👀 Player nearby — AutoMine auto-paused" if CONFIG["player_detection_pause"] else "👀 Player nearby",
                 ", ".join(f"{n} ({d}m)" for n, d in nearby), "warn", True)
        if CONFIG["player_detection_pause"] and not _script_paused:
            _script_paused = True
            _auto_paused_by_detection = True
            minescript.echo("§e[AutoMine] Auto-paused (player detected)")
            for release in (
                minescript.player_press_attack,
                minescript.player_press_sneak,
                minescript.player_press_use,
            ):
                try:
                    release(False)
                except Exception:
                    pass

    elif not nearby and _player_nearby:
        # player ออกไปแล้ว
        _player_nearby = False
        minescript.echo("§a[AutoMine] Player left area")
        if CONFIG["player_detection_resume"] and _auto_paused_by_detection and _script_paused:
            _script_paused = False
            _auto_paused_by_detection = False
            minescript.echo("§a[AutoMine] Auto-resumed")


# =========================================
# IDLE MOVEMENT (safe: crouch + look_around)
# =========================================
def _idle_crouch():
    """นั่งยองแบบ random duration แล้วลุกขึ้น"""
    lo, hi = CONFIG["idle_crouch_duration"]
    duration = random.uniform(lo, hi)
    minescript.player_press_sneak(True)
    interruptible_sleep(duration)
    minescript.player_press_sneak(False)
    interruptible_sleep(random.uniform(0.05, 0.15))


def _idle_look_around():
    """
    หันกล้องไปทิศสุ่มแล้วกลับมาที่เดิม
    ใช้ ease-in-out เหมือน smooth_look_at
    """
    cur_yaw, cur_pitch = minescript.player_orientation()

    ylo, yhi = CONFIG["idle_look_yaw_range"]
    plo, phi = CONFIG["idle_look_pitch_range"]
    delta_yaw   = random.uniform(ylo, yhi)
    delta_pitch = random.uniform(plo, phi)

    steps = random.randint(10, 20)
    delay = random.uniform(0.012, 0.022)

    # หันออก
    for i in range(1, steps + 1):
        if not _script_active:
            minescript.player_set_orientation(cur_yaw, cur_pitch)
            return
        t = i / steps
        s = t * t * (3.0 - 2.0 * t)
        minescript.player_set_orientation(
            cur_yaw   + delta_yaw   * s,
            cur_pitch + delta_pitch * s,
        )
        time.sleep(delay)  # step เล็ก ไม่ต้อง interrupt

    # หยุดนิดนึงแล้วกลับ
    interruptible_sleep(random.uniform(0.15, 0.45))
    if not _script_active:
        minescript.player_set_orientation(cur_yaw, cur_pitch)
        return

    ret_yaw, ret_pitch = minescript.player_orientation()
    for i in range(1, steps + 1):
        if not _script_active:
            minescript.player_set_orientation(cur_yaw, cur_pitch)
            return
        t = i / steps
        s = t * t * (3.0 - 2.0 * t)
        minescript.player_set_orientation(
            ret_yaw   + (cur_yaw   - ret_yaw)   * s,
            ret_pitch + (cur_pitch - ret_pitch) * s,
        )
        time.sleep(delay)

    # snap กลับตำแหน่งเดิมพอดี
    minescript.player_set_orientation(cur_yaw, cur_pitch)
    interruptible_sleep(random.uniform(0.05, 0.1))


def do_idle_movement():
    """เลือก action ตาม weight แล้วรัน"""
    weights = CONFIG["idle_weights"]
    pool = []
    for action, w in weights.items():
        pool.extend([action] * w)
    chosen = random.choice(pool)
    debug_msg(f"[Idle] {chosen}")
    if chosen == "crouch":
        _idle_crouch()
    elif chosen == "look_around":
        _idle_look_around()


def maybe_idle(mined: bool):
    """
    เรียกหลัง mine สำเร็จแต่ละครั้ง
    trigger เมื่อครบ _next_idle_at blocks
    """
    global _blocks_since_idle, _next_idle_at
    if not CONFIG["idle_movement_enabled"] or not mined:
        return
    # init ครั้งแรก
    if _next_idle_at == 0:
        lo, hi = CONFIG["idle_every_blocks"]
        _next_idle_at = random.randint(lo, hi)
    _blocks_since_idle += 1
    if _blocks_since_idle >= _next_idle_at:
        _blocks_since_idle = 0
        lo, hi = CONFIG["idle_every_blocks"]
        _next_idle_at = random.randint(lo, hi)
        do_idle_movement()


# =========================================
# SKILL
# =========================================
def on_chat_message(message: str):
    """ข้อความแชทจาก lib_event: เห็นข้อความว่าสกิลพร้อม → ตั้งสถานะพร้อม (กดจริงที่ loop หลัก)"""
    global _skill_ready, _skill_ready_at
    if not (_skill_chat_active and CONFIG["enable_skill"]):
        return
    text = _HUD_COLOR_CODES.sub("", message or "").lower()
    if CONFIG["skill_ready_text"].lower() in text:
        lo, hi = CONFIG["skill_react_delay"]
        _skill_ready = True
        _skill_ready_at = time.time() + random.uniform(lo, hi)
        debug_msg("Skill ready (chat)")


def start_chat_detection(event_queue):
    """โหลด lib_event แล้วลงทะเบียน chat listener (ใน thread แยกพร้อม timeout:
    ตอน import มันรอ socket จากสคริปต์ในเกมแบบไม่มี timeout) ไม่สำเร็จ → นับเวลาเองแทน"""
    global _skill_chat_active
    if not (CONFIG["enable_skill"] and CONFIG["skill_use_chat_detect"]):
        return
    result = {}

    def _import():
        try:
            import system.lib.lib_event  # noqa: F401 — ทำให้ EventQueue มี register_chat_listener(eventlib=True)
            result["ok"] = True
        except BaseException as e:   # lib เรียก sys.exit() ถ้าเวอร์ชัน Minescript ไม่ตรง
            result["err"] = e

    t = threading.Thread(target=_import, daemon=True)
    t.start()
    t.join(CONFIG["lib_event_load_timeout"])
    if result.get("ok"):
        try:
            event_queue.register_chat_listener(eventlib=True)
            _skill_chat_active = True
            return
        except Exception as e:
            result["err"] = e
    minescript.echo(f"§e[AutoMine] lib_event unavailable ({result.get('err', 'timeout')}), "
                    f"timing skill every {CONFIG['skill_interval']:.0f}s instead")


def should_use_skill() -> bool:
    global _last_skill_time, _skill_ready
    if not CONFIG["enable_skill"]:
        return False
    now = time.time()
    if _skill_chat_active:
        # พร้อมจากแชท (หลังหน่วงสุ่ม) หรือกดไปแล้วนานเกิน timeout โดยไม่เห็นข้อความ → ลองใหม่
        if (_skill_ready and now >= _skill_ready_at) or now - _last_skill_time >= CONFIG["skill_chat_timeout"]:
            _last_skill_time = now
            _skill_ready = False
            return True
        return False
    # สุ่มแค่ทางบวก: ถ้าสุ่มติดลบจะกดก่อนคูลดาวน์หมด สกิลไม่ทำงานและเสียรอบไปเปล่า ๆ
    interval = CONFIG["skill_interval"] + random.uniform(0.0, CONFIG["skill_random_variance"])
    if now - _last_skill_time >= interval:
        _last_skill_time = now
        return True
    return False


def use_skill():
    debug_msg("⚡ Using skill...")
    minescript.player_press_use(True)
    hold = CONFIG["skill_hold_time"]
    time.sleep(max(0.1, hold + random.uniform(-hold * 0.2, hold * 0.2)))
    minescript.player_press_use(False)
    debug_msg("✓ Skill used!")
    time.sleep(0.2)


# =========================================
# KEY HANDLER
# =========================================
def key_handler(event):
    global _script_active, _script_paused
    if event.action != 1:
        return

    if event.key == CONFIG["toggle_key"]:
        _script_active = not _script_active
        _script_paused = False  # reset pause เมื่อ toggle
        state = "§aENABLED" if _script_active else "§cDISABLED"
        minescript.echo(f"§b[AutoMine] §fScript {state}")
        if _script_active:
            bk_cancel_reconnect()      # คุณสั่งเริ่มเอง = เข้าเกมมาดูแลเองแล้ว
        bk_alert("▶️ AutoMine enabled" if _script_active else "⏹ AutoMine disabled (manual)", "", "info")
        if not _script_active:
            for release in (
                minescript.player_press_attack,
                minescript.player_press_sneak,
                minescript.player_press_use,
            ):
                try:
                    release(False)
                except Exception:
                    pass

    elif event.key == CONFIG["pause_key"]:
        if not _script_active:
            return
        _script_paused = not _script_paused
        state = "§ePAUSED" if _script_paused else "§aRESUMED"
        minescript.echo(f"§b[AutoMine] §f{state}")
        if _script_paused:
            for release in (
                minescript.player_press_attack,
                minescript.player_press_sneak,
                minescript.player_press_use,
            ):
                try:
                    release(False)
                except Exception:
                    pass


# =========================================
# BLOCK HELPERS
# =========================================
def get_block_id_at(x: int, y: int, z: int):
    try:
        return minescript.getblock(x, y, z)
    except Exception:
        return None


def get_blocklist_for_positions(pos_list: list):
    try:
        return minescript.getblocklist(pos_list)
    except Exception as e:
        debug_msg(f"[debug] getblocklist failed: {e}")
        return None


def get_target_sets(block_type) -> tuple:
    """
    คืน (target_bases, target_set) สำหรับเทียบ block type.
    target_bases: ชื่อ block ไม่รวม [...] blockstate (ใช้กับ ignore_state=True)
    target_set:   ชื่อ block แบบ exact รวม blockstate
    """
    if isinstance(block_type, list):
        target_bases = {t.split("[")[0] for t in block_type}
        target_set   = set(block_type)
    else:
        target_bases = {block_type.split("[")[0]}
        target_set   = {block_type}
    return target_bases, target_set


# =========================================
# SCAN — cached + partial invalidation
# BUG FIX: target_bases/target_set scoped correctly
# =========================================
def find_all_blocks(
    player_pos: tuple,
    max_distance: float = 5.0,
    block_type = "minecraft:redstone_block",
    ignore_state: bool = False,
) -> list:
    """
    Accepts player_pos from caller to avoid redundant player_position() call.
    """
    global _scan_cache_blocks, _scan_cache_player_pos, _scan_cache_time

    px, py, pz = player_pos
    now = time.time()

    # Cache validity
    if _scan_cache_player_pos is not None:
        cpx, cpy, cpz = _scan_cache_player_pos
        moved = math.sqrt((px - cpx) ** 2 + (py - cpy) ** 2 + (pz - cpz) ** 2)
        if moved < CONFIG["scan_cache_move_threshold"] and now - _scan_cache_time < CONFIG["scan_cache_max_age"]:
            return _scan_cache_blocks

    offsets = get_sphere_offsets(max_distance)
    ipx, ipy, ipz = int(px), int(py), int(pz)
    positions_to_check = [(ipx + dx, ipy + dy, ipz + dz) for dx, dy, dz in offsets]

    target_bases, target_set = get_target_sets(block_type)

    block_types_found = get_blocklist_for_positions(positions_to_check)
    if block_types_found is None:
        return []

    blocks_found = []
    for i, found_bt in enumerate(block_types_found):
        if found_bt is None:
            continue
        match = (found_bt.split("[")[0] in target_bases) if ignore_state else (found_bt in target_set)
        if not match:
            continue
        bx, by, bz = positions_to_check[i]
        dist = math.sqrt((bx - px) ** 2 + (by - py) ** 2 + (bz - pz) ** 2)
        blocks_found.append({"position": (bx, by, bz), "distance": dist, "full_type": found_bt})

    _scan_cache_blocks = blocks_found
    _scan_cache_player_pos = (px, py, pz)
    _scan_cache_time = now
    debug_msg(f"Scan: {len(blocks_found)} block(s) found")
    return blocks_found


def invalidate_position_from_cache(pos: tuple):
    """Remove one position from cache without forcing full rescan."""
    global _scan_cache_blocks
    _scan_cache_blocks = [b for b in _scan_cache_blocks if b["position"] != pos]


# =========================================
# INSTANT NEIGHBOR SCAN
# จับ block ที่เกิดขึ้นทันทีหลัง mine (เช่น titanium เกิดแทนที่ mithril)
# =========================================
# ตำแหน่งที่เพิ่งขุด (0,0,0) + 6 ด้านรอบๆ
_NEIGHBOR_OFFSETS = [
    (0, 0, 0),
    (1, 0, 0), (-1, 0, 0),
    (0, 1, 0), (0, -1, 0),
    (0, 0, 1), (0, 0, -1),
]


def instant_neighbor_scan(block_pos: tuple, player_pos: tuple) -> list:
    """
    เช็คตำแหน่งที่เพิ่งขุด + 6 ด้านรอบๆ ทันทีด้วย getblocklist เดียว
    เพื่อจับ target block ที่เกิดขึ้นใหม่ทันที (เช่น titanium spawn แทน mithril)
    คืน list ของ block dicts ที่ match target_block
    """
    bx, by, bz = block_pos
    positions = [(bx + dx, by + dy, bz + dz) for dx, dy, dz in _NEIGHBOR_OFFSETS]

    bts = get_blocklist_for_positions(positions)
    if bts is None:
        return []

    target_bases, target_set = get_target_sets(CONFIG["target_block"])
    ignore_state = CONFIG["ignore_block_state"]
    px, py, pz = player_pos

    found = []
    for i, bt in enumerate(bts):
        if bt is None:
            continue
        match = (bt.split("[")[0] in target_bases) if ignore_state else (bt in target_set)
        if not match:
            continue
        pos = positions[i]
        dist = math.sqrt((pos[0]-px)**2 + (pos[1]-py)**2 + (pos[2]-pz)**2)
        found.append({"position": pos, "distance": dist, "full_type": bt})

    return found


def merge_into_scan_cache(new_blocks: list):
    """เพิ่ม/อัปเดต block ใหม่ที่เจอเข้า scan cache โดยไม่ทำ full rescan"""
    global _scan_cache_blocks
    if not new_blocks:
        return
    by_pos = {b["position"]: b for b in _scan_cache_blocks}
    for nb in new_blocks:
        by_pos[nb["position"]] = nb  # add ใหม่ หรือ overwrite ของเดิม (type อาจเปลี่ยน)
    _scan_cache_blocks = list(by_pos.values())


# =========================================
# VISIBILITY — จุดเล็งที่มองเห็นได้บนหน้าบล็อก (ดัดแปลงแนวคิดจาก Philogex/Minescript-Miner, MIT)
# เดิมยิง ray ไปกลางบล็อกเส้นเดียว: ถ้ากลางบล็อกโดนบังแต่ขอบ/มุมหน้ายังเห็น ก็นับว่าโดนบังทั้งก้อน
# ตอนนี้สุ่มหลายจุดบน "หน้าที่หันเข้าหาผู้เล่น" ยิงทุก ray ใน getblocklist ครั้งเดียว แล้วเลือกจุดที่เห็น
# บล็อกที่ไม่ผ่าน (ไม่อยู่ใน PASSABLE_BLOCKS) ถือเป็นลูกบาศก์ทึบเต็มก้อน (ประเมินแบบระวังไว้ก่อน)
# =========================================
EYE_HEIGHT = 1.62
_FACE_EPS = 0.01   # ดันจุดเข้าไปในบล็อกนิดหน่อย ray จะได้จบในช่องของบล็อกเป้าแน่ ๆ


def face_aim_points(block_pos: tuple, eye: tuple, inset: float) -> list:
    """จุดบนหน้าบล็อกที่หันเข้าหาตา คืน [(point, face_id, is_center), ...] กลางหน้ามาก่อน
    หน้าหนึ่งหันเข้าหาตาก็ต่อเมื่อตาอยู่ "นอก" ระนาบของหน้านั้น (มองเห็นได้สูงสุด 3 หน้า)"""
    lo, hi = inset, 1.0 - inset
    pattern = [(0.5, 0.5), (lo, lo), (lo, hi), (hi, lo), (hi, hi),
               (0.5, lo), (0.5, hi), (lo, 0.5), (hi, 0.5)]
    if inset >= 0.5:
        pattern = pattern[:1]
    points = []
    for axis in range(3):
        b = block_pos[axis]
        if eye[axis] < b:
            plane = b + _FACE_EPS
        elif eye[axis] > b + 1:
            plane = b + 1 - _FACE_EPS
        else:
            continue
        u_axis, v_axis = [a for a in range(3) if a != axis]
        for i, (fu, fv) in enumerate(pattern):
            p = [0.0, 0.0, 0.0]
            p[axis] = plane
            p[u_axis] = block_pos[u_axis] + fu
            p[v_axis] = block_pos[v_axis] + fv
            points.append((tuple(p), axis, i == 0))
    return points


def ray_voxels(origin: tuple, target: tuple, target_voxel: tuple, max_steps: int = 64):
    """ช่องบล็อกที่ ray จาก origin ไป target ผ่าน ก่อนถึง target_voxel (ไม่รวมช่องของตาและของเป้า)
    ใช้ voxel traversal แบบแม่นยำ (Amanatides–Woo) ไม่ข้ามมุมเหมือนการเดินทีละ 0.3 บล็อก
    คืน None ถ้า ray ไม่เข้าช่องเป้าเลย"""
    x, y, z = math.floor(origin[0]), math.floor(origin[1]), math.floor(origin[2])
    d = (target[0] - origin[0], target[1] - origin[1], target[2] - origin[2])
    cell = [x, y, z]
    step, t_max, t_delta = [0, 0, 0], [math.inf] * 3, [math.inf] * 3
    for a in range(3):
        if d[a] > 0:
            step[a] = 1
            t_max[a] = (cell[a] + 1 - origin[a]) / d[a]
            t_delta[a] = 1 / d[a]
        elif d[a] < 0:
            step[a] = -1
            t_max[a] = (origin[a] - cell[a]) / -d[a]
            t_delta[a] = 1 / -d[a]
    voxels = []
    for _ in range(max_steps):
        a = min(range(3), key=lambda i: t_max[i])
        if t_max[a] > 1.0:
            return None          # ถึงปลาย ray แล้วยังไม่เข้าช่องเป้า
        cell[a] += step[a]
        t_max[a] += t_delta[a]
        c = (cell[0], cell[1], cell[2])
        if c == target_voxel:
            return voxels
        voxels.append(c)
    return None


def angular_size_deg(distance: float, size: float = 1.0) -> float:
    return math.degrees(2.0 * math.atan2(size / 2.0, max(distance, 1e-6)))


def batch_visibility_check(player_pos: tuple, block_positions: list, orientation: tuple = None) -> dict:
    """
    หาจุดเล็งที่มองเห็นได้ของแต่ละบล็อก ยิงทุก ray ด้วย getblocklist ครั้งเดียว
    คืน { block_pos: {"point": (x,y,z), "width_deg": float} } เฉพาะบล็อกที่เห็นอย่างน้อยหนึ่งจุด

    เลือกจุดที่ต้องหันน้อยที่สุดจาก orientation ปัจจุบัน (จุดที่ไม่ใช่กลางหน้าบวก penalty นิดหน่อย)
    width_deg = ความกว้างเชิงมุมโดยประมาณของส่วนที่มองเห็นบนหน้านั้น (ใช้คำนวณเวลาหันแบบ Fitts)
    """
    eye = (player_pos[0], player_pos[1] + EYE_HEIGHT, player_pos[2])
    reach = CONFIG["reach_distance"]
    inset = CONFIG["aim_face_inset"]

    all_positions: list = []
    index_of: dict = {}
    rays: dict = {}   # block_pos -> [(point, face_id, is_center, [voxel indices])]

    for block_pos in block_positions:
        entries = []
        for point, face, is_center in face_aim_points(block_pos, eye, inset):
            if math.dist(eye, point) > reach:
                continue
            voxels = ray_voxels(eye, point, block_pos)
            if voxels is None:
                continue
            idxs = []
            for v in voxels:
                i = index_of.get(v)
                if i is None:
                    i = index_of[v] = len(all_positions)
                    all_positions.append(v)
                idxs.append(i)
            entries.append((point, face, is_center, idxs))
        rays[block_pos] = entries

    bts = get_blocklist_for_positions(all_positions) if all_positions else []
    if bts is None:
        return {}   # อ่านบล็อกไม่ได้ อย่าเดา (เดิมถือว่าเห็นหมด ทำให้เล็งไปโดนของที่บัง)

    if orientation is None:
        orientation = minescript.player_orientation()
    cur_yaw, cur_pitch = orientation
    penalty = CONFIG["aim_edge_penalty_deg"]
    per_face = 9 if inset < 0.5 else 1

    result = {}
    for block_pos, entries in rays.items():
        visible = [
            (point, face, is_center) for point, face, is_center, idxs in entries
            if not any(bts[i] is not None and bts[i] not in PASSABLE_BLOCKS for i in idxs)
        ]
        if not visible:
            continue
        best, best_score = None, math.inf
        for point, face, is_center in visible:
            yaw, pitch = calculate_look_angles(player_pos, point)
            score = angular_distance_fast(cur_yaw, cur_pitch, yaw, pitch) + (0.0 if is_center else penalty)
            if score < best_score:
                best, best_score = (point, face), score
        point, face = best
        seen_on_face = sum(1 for _, f, _ in visible if f == face)
        width = angular_size_deg(math.dist(eye, point), 1.0 - 2.0 * min(inset, 0.45))
        width *= math.sqrt(seen_on_face / per_face)   # โดนบังเกือบหมด = เป้าเล็กลง
        result[block_pos] = {"point": point, "width_deg": width}
    return result


# =========================================
# ANGLES / ROTATION
# =========================================
def calculate_look_angles(player_pos: tuple, target_pos: tuple) -> tuple:
    px, py, pz = player_pos
    tx, ty, tz = target_pos
    dx, dy, dz = tx - px, ty - (py + 1.62), tz - pz
    horiz = math.sqrt(dx * dx + dz * dz)
    pitch = -math.degrees(math.atan2(dy, horiz))
    yaw   = math.degrees(math.atan2(-dx, dz))
    return yaw, pitch


def normalize_angle(angle: float) -> float:
    while angle >  180: angle -= 360
    while angle < -180: angle += 360
    return angle


def angle_difference(current: float, target: float) -> float:
    return normalize_angle(target - current)


def angular_distance_fast(yaw1, pitch1, yaw2, pitch2) -> float:
    dy = abs(normalize_angle(yaw2 - yaw1))
    dp = abs(normalize_angle(pitch2 - pitch1))
    return math.sqrt(dy * dy + dp * dp)


# =========================================
# ROTATION — Fitts' law + minimum-jerk (ดัดแปลงจาก Philogex/Minescript-Miner, MIT)
# =========================================
_FALLBACK_TARGET_WIDTH_DEG = 11.0   # ใช้เมื่อไม่รู้ความกว้างเป้า (≈ หน้าบล็อกที่ระยะ 3 บล็อก หักขอบ)


def minimum_jerk(t: float) -> float:
    """โปรไฟล์ minimum-jerk: เร่ง/ผ่อนนุ่มกว่า smoothstep ทั้งตอนเริ่มและตอนหยุด"""
    return t * t * t * (10.0 + t * (-15.0 + 6.0 * t))


def rotation_duration(amplitude_deg: float, width_deg: float = None) -> float:
    """กฎของ Fitts: เวลา = a + b * log2(A / W + 1) จำกัดอยู่ในช่วง [min, max]"""
    width = width_deg if width_deg and width_deg > 0 else _FALLBACK_TARGET_WIDTH_DEG
    width = max(width, 0.5)
    difficulty = math.log2(amplitude_deg / width + 1.0)
    duration = CONFIG["rotation_fitts_a"] + CONFIG["rotation_fitts_b"] * difficulty
    return min(max(duration, CONFIG["rotation_duration_min"]), CONFIG["rotation_duration_max"])


def rotate_to(tgt_yaw: float, tgt_pitch: float, width_deg: float = None) -> bool:
    """หันกล้องไป yaw/pitch เป้าหมาย คืน False ถ้าถูกปิด/pause ระหว่างหัน"""
    cur_yaw, cur_pitch = minescript.player_orientation()
    ang_dist = angular_distance_fast(cur_yaw, cur_pitch, tgt_yaw, tgt_pitch)

    if ang_dist < CONFIG["rotation_snap_threshold"]:
        minescript.player_set_orientation(tgt_yaw, tgt_pitch)
        return True

    yaw_diff   = angle_difference(cur_yaw, tgt_yaw)
    pitch_diff = angle_difference(cur_pitch, tgt_pitch)

    duration = rotation_duration(ang_dist, width_deg) * (1.0 + random.uniform(-0.08, 0.08))
    steps = max(CONFIG["rotation_steps_min"], int(duration * CONFIG["rotation_steps_per_second"]))

    variance = CONFIG["rotation_human_variance"]
    jitter_yaw   = [random.uniform(-variance, variance) * yaw_diff   * 0.012 for _ in range(steps)]
    jitter_pitch = [random.uniform(-variance, variance) * pitch_diff * 0.012 for _ in range(steps)]
    jy_mean = sum(jitter_yaw)   / steps
    jp_mean = sum(jitter_pitch) / steps
    jitter_yaw   = [v - jy_mean for v in jitter_yaw]
    jitter_pitch = [v - jp_mean for v in jitter_pitch]

    # ตั้งเวลาแต่ละ step จากเวลาเริ่ม (absolute) ไม่ใช่ sleep ต่อกัน: RPC ช้าแล้วเวลาไม่สะสมจนหันช้ากว่าที่คำนวณ
    started = time.time()
    cum_jy = cum_jp = 0.0
    for i in range(1, steps + 1):
        if not _script_active or _script_paused:
            return False
        cum_jy += jitter_yaw[i - 1]
        cum_jp += jitter_pitch[i - 1]
        if i == steps:
            minescript.player_set_orientation(tgt_yaw, tgt_pitch)
        else:
            s = minimum_jerk(i / steps)
            minescript.player_set_orientation(
                cur_yaw   + yaw_diff   * s + cum_jy,
                cur_pitch + pitch_diff * s + cum_jp,
            )
            wait = started + duration * i / steps - time.time()
            if wait > 0:
                time.sleep(wait)
    return True


# =========================================
# MINING
# =========================================
def _is_target_type(block_id) -> bool:
    if not block_id:
        return False
    target_bases, target_set = get_target_sets(CONFIG["target_block"])
    if CONFIG["ignore_block_state"]:
        return block_id.split("[")[0] in target_bases
    return block_id in target_set


def smooth_look_at(
    target_pos: tuple,
    block_pos: tuple,
    block_full_type: str,
    player_pos: tuple,
    width_deg: float = None,
) -> bool:
    """
    Rotate to the aim point on block_pos and mine it.
    target_pos = จุดเล็งที่มองเห็นได้ (จาก batch_visibility_check) ไม่จำเป็นต้องเป็นกลางบล็อก
    Returns True if block was successfully mined.
    """
    tgt_yaw, tgt_pitch = calculate_look_angles(player_pos, target_pos)
    if not rotate_to(tgt_yaw, tgt_pitch, width_deg):
        return False

    if not CONFIG["break_blocks"]:
        return False

    if CONFIG["break_delay"] > 0:
        interruptible_sleep(CONFIG["break_delay"])
        if not _script_active or _script_paused:
            return False

    # --- Targeting validation: เล็งโดนบล็อกนี้จริง และบล็อกยังเป็นเป้าอยู่ (แผนอาจเก่าไปแล้ว) ---
    is_targeted = False
    final_targeted = None
    for _ in range(CONFIG["targeting_retries"]):
        t = minescript.player_get_targeted_block(max_distance=6.0)
        final_targeted = t
        if t and tuple(t.position) == block_pos:
            is_targeted = True
            break
        interruptible_sleep(CONFIG["targeting_retry_delay"])

    if not is_targeted:
        if final_targeted:
            debug_msg(f"OBSTRUCTION: expected {block_pos}, got {final_targeted.position}")
        else:
            debug_msg(f"OBSTRUCTION: expected {block_pos}, got nothing")
        add_obstructed(block_pos)
        return False

    current_type = get_block_id_at(*block_pos)
    if current_type is not None and current_type != block_full_type and not _is_target_type(current_type):
        debug_msg(f"STALE: {block_pos} is now {current_type}, skipping")
        invalidate_position_from_cache(block_pos)
        return False

    # --- Mine ---
    minescript.player_press_attack(True)
    mined = False
    lost_target = False
    try:
        if CONFIG["break_until_bedrock"]:
            bx, by, bz = block_pos
            deadline = time.time() + CONFIG["break_timeout"]
            poll = CONFIG["break_poll_rate"]
            check_every = CONFIG["mining_target_check_interval"]
            next_check = time.time() + check_every
            next_assert = time.time() + 0.3
            last_grab_handled = _unfocused.grab_changed_at() if _unfocused is not None else 0.0
            lost_checks = 0
            while time.time() < deadline:
                if not _script_active or _script_paused:
                    break
                cur_block = get_block_id_at(bx, by, bz)
                if cur_block == "minecraft:air":
                    mined = True
                    break
                if cur_block == "minecraft:bedrock":
                    debug_msg(f"BEDROCK at {block_pos}, skipping")
                    add_obstructed(block_pos)
                    break
                if cur_block is not None and cur_block != block_full_type:
                    debug_msg(f"Block changed {block_pos}: {block_full_type}→{cur_block}")
                    mined = True
                    break
                # --- กดปุ่มโจมตีซ้ำเป็นระยะ: สลับโฟกัสแล้วเกมรีเซ็ตสถานะปุ่มที่กดค้าง ---
                now = time.time()
                if now >= next_assert:
                    next_assert = now + 0.3
                    minescript.player_press_attack(True)
                    if _unfocused is not None:
                        changed = _unfocused.grab_changed_at()
                        if changed > last_grab_handled:
                            last_grab_handled = changed
                            if _unfocused.stats()["grabbed"]:
                                # เมาส์เพิ่งถูกจับคืน (กลับมาโฟกัส): เกมตั้ง missTime=10000 ห้ามทุบ ล้างได้ด้วยการปล่อยปุ่มตีนานกว่า 1 tick
                                minescript.player_press_attack(False)
                                time.sleep(0.12)
                                minescript.player_press_attack(True)
                # --- ระหว่างขุด: GUI โผล่ หรือกล้องไม่ได้เล็งบล็อกนี้แล้ว → ปล่อยปุ่ม หาเป้าใหม่ทันที ---
                if now >= next_check:
                    next_check = now + check_every
                    if minescript.screen_name() is not None:
                        debug_msg("GUI opened while mining, releasing attack")
                        break
                    t = minescript.player_get_targeted_block(max_distance=6.0)
                    if t and tuple(t.position) == block_pos:
                        lost_checks = 0
                    else:
                        lost_checks += 1
                        if lost_checks >= CONFIG["mining_target_lost_checks"]:
                            debug_msg(f"LOST TARGET {block_pos} while mining, re-planning")
                            lost_target = True
                            break
                time.sleep(poll)
            if not mined and not lost_target and _script_active and time.time() >= deadline:
                debug_msg(f"TIMEOUT: {block_pos} after {CONFIG['break_timeout']}s")
        else:
            interruptible_sleep(CONFIG["break_hold_time"])
            mined = True
    finally:
        minescript.player_press_attack(False)

    return mined


# =========================================
# CLUSTERING — deque O(1) + pre-sorted input
# =========================================
def euclidean_distance(a: tuple, b: tuple) -> float:
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2)


def cluster_blocks(blocks: list, threshold: float = 1.5) -> list:
    """BFS clustering. Uses deque for O(1) popleft and distance² to avoid sqrt."""
    positions = [b["position"] for b in blocks]
    n = len(positions)
    visited = [False] * n
    clusters = []
    threshold_sq = threshold * threshold

    for i in range(n):
        if visited[i]:
            continue
        queue = deque([i])
        cluster_idxs = []
        while queue:
            idx = queue.popleft()
            if visited[idx]:
                continue
            visited[idx] = True
            cluster_idxs.append(idx)
            pix, piy, piz = positions[idx]
            for j in range(n):
                if not visited[j]:
                    pj = positions[j]
                    dx = pix - pj[0]; dy = piy - pj[1]; dz = piz - pj[2]
                    if dx*dx + dy*dy + dz*dz <= threshold_sq:
                        queue.append(j)
        clusters.append([blocks[ci] for ci in cluster_idxs])
    return clusters


def cluster_tightness(cluster: list) -> float:
    coords = [c["position"] for c in cluster]
    if len(coords) <= 1:
        return 0.0
    maxd_sq = 0.0
    for i in range(len(coords)):
        for j in range(i + 1, len(coords)):
            c, d = coords[i], coords[j]
            dx, dy, dz = c[0]-d[0], c[1]-d[1], c[2]-d[2]
            dist_sq = dx*dx + dy*dy + dz*dz
            if dist_sq > maxd_sq:
                maxd_sq = dist_sq
    return math.sqrt(maxd_sq)


def cluster_center(cluster: list) -> tuple:
    coords = [c["position"] for c in cluster]
    n = len(coords)
    return (
        sum(c[0] for c in coords) / n,
        sum(c[1] for c in coords) / n,
        sum(c[2] for c in coords) / n,
    )


def sort_clusters(clusters: list, player_pos: tuple) -> list:
    info = [
        (cluster_tightness(c), euclidean_distance(player_pos, cluster_center(c)), c)
        for c in clusters
    ]
    info.sort(key=lambda x: (x[0], x[1]))
    return [c for _, _, c in info]


# =========================================
# SAFETY STOPS — หยุดเองเมื่อสถานการณ์เปลี่ยน (แนวคิดจาก Philogex/Minescript-Miner)
# =========================================
_mc_instance = None
_last_focus_check = 0.0
_window_active = True
_auto_paused_by_focus = False
_last_safety_pos = None


def release_keys():
    for release in (
        minescript.player_press_attack,
        minescript.player_press_sneak,
        minescript.player_press_use,
    ):
        try:
            release(False)
        except Exception:
            pass


def stop_script(reason: str, alert: bool = True):
    """ปิดสคริปต์ (เหมือนกด toggle) พร้อมบอกเหตุผล + แจ้ง Discord"""
    global _script_active, _script_paused, _last_safety_pos
    if not _script_active:
        return
    _script_active = False
    _script_paused = False
    _last_safety_pos = None
    release_keys()
    minescript.echo(f"§c[AutoMine] §fStopped: {reason}")
    if alert:
        bk_alert("🛑 AutoMine stopped", reason, "error", True)


def window_active() -> bool:
    """หน้าต่างเกม active อยู่ไหม (เช็คจริงทุก 0.5 วินาที อ่านผ่าน Java ไม่ได้ให้ถือว่า active)"""
    global _mc_instance, _last_focus_check, _window_active
    now = time.time()
    if now - _last_focus_check < 0.5:
        return _window_active
    _last_focus_check = now
    try:
        if _mc_instance is None:
            from system.lib.java import JavaClass
            _mc_instance = JavaClass("net.minecraft.client.Minecraft").getInstance()
        _window_active = bool(_mc_instance.isWindowActive())
    except Exception:
        _window_active = True
    return _window_active


def check_focus():
    """หน้าต่างไม่ active: เกมปล่อยปุ่มที่กดค้างเอง ขุดต่อไม่ได้ → pause แล้ว resume เมื่อกลับมา"""
    global _script_paused, _auto_paused_by_focus
    # ขุดตอนไม่โฟกัสได้ (สคริปต์ในเกมทำงานอยู่) → ไม่ต้อง pause; ถ้าสคริปต์ในเกมไม่ทำงาน ใช้ pause เป็นตัวสำรอง
    assist_ok = CONFIG["mine_unfocused"] and _unfocused is not None and _unfocused.connected
    if not (CONFIG["pause_on_focus_loss"] or (CONFIG["mine_unfocused"] and not assist_ok)):
        if _auto_paused_by_focus and _script_paused:   # เพิ่งต่อสคริปต์ในเกมติดระหว่างที่ pause อยู่ → ปล่อยให้ขุดต่อ
            _script_paused = False
            _auto_paused_by_focus = False
            minescript.echo("§a[AutoMine] Auto-resumed (mining in background)")
        return
    if not window_active():
        if not _script_paused:
            _script_paused = True
            _auto_paused_by_focus = True
            release_keys()
            minescript.echo("§e[AutoMine] Auto-paused (game window lost focus)")
    elif _auto_paused_by_focus and _script_paused:
        _script_paused = False
        _auto_paused_by_focus = False
        minescript.echo("§a[AutoMine] Auto-resumed (focus back)")


def check_teleport(player_pos: tuple) -> bool:
    """สคริปต์ไม่เดินเอง ตำแหน่งกระโดดไกล = ถูกวาร์ป/ดึงตัว → ปิดสคริปต์ คืน True ถ้าปิด"""
    global _last_safety_pos
    if not CONFIG["stop_on_teleport"]:
        return False
    if _last_safety_pos is not None:
        moved = math.dist(_last_safety_pos, player_pos)
        if moved > CONFIG["teleport_stop_distance"]:
            stop_script(f"position jumped {moved:.1f} blocks")
            return True
    _last_safety_pos = tuple(player_pos)
    return False


# =========================================
# MAIN
# =========================================
def main():
    global _total_broken, _script_active, _scan_cache_time, _last_safety_pos
    global _link, _reconnector, _session_started, _script_paused, _auto_paused_by_detection, _auto_paused_by_focus, _unfocused

    minescript.echo("§b[AutoMine v2] §fLoaded. Press §e']'§f to toggle, §e'['§f to pause.")

    event_queue = minescript.EventQueue()
    event_queue.register_key_listener()
    # world listener จำเป็นสำหรับต่อเซิร์ฟเวอร์ใหม่ด้วย: Minescript จะปิดสคริปต์ตอนหลุดโลก ยกเว้นสคริปต์ที่มี world listener
    event_queue.register_world_listener()

    ctx = {"resume": False, "world_up": True}
    _session_started = time.time()

    def _status_fields():
        status = "OFF" if not _script_active else ("PAUSED" if _script_paused else "RUNNING")
        fields = [("Status", status), ("Mined", str(_total_broken)), ("Runtime", fmt_duration(time.time() - _session_started))]
        if CONFIG["enable_skill"]:
            fields.append(("Skill", ("ready" if _skill_ready else "cooldown") if _skill_chat_active else "timer"))
        if _player_nearby:
            fields.append(("Players nearby", "yes"))
        if _unfocused is not None:
            st = _unfocused.stats()
            fields.append(("Window", "ไม่ได้โฟกัส (ขุดอยู่เบื้องหลัง)" if st["active"] is False else ("โฟกัส" if st["active"] else "?")))
            if st["attacks"]:
                fields.append(("Background hits", str(st["attacks"])))
            if st["err"]:
                fields.append(("Background err", st["err"][:100]))
        try:
            x, y, z = minescript.player_position()
            fields.append(("Position", f"{x:.0f}, {y:.0f}, {z:.0f}"))
        except Exception:
            pass
        if _reconnector is not None and _reconnector.active:
            fields.append(("Reconnect", "trying…"))
        return fields

    def _alert(title, description="", level="info", screenshot=False):
        minescript.echo(f"§b[AutoMine] §f{title} {description}".strip().split("\n")[0])
        bk_alert(title, description, level, screenshot)

    def _remote_stop():
        _reconnector.cancel()
        ctx["resume"] = False
        if not _script_active:
            return "AutoMine ปิดอยู่แล้ว (ยกเลิกการต่อเซิร์ฟเวอร์/เริ่มต่อที่ค้างอยู่ด้วย)"
        stop_script("สั่งหยุดจาก Discord", alert=False)
        return "หยุด AutoMine แล้ว — กด ] ในเกมเมื่อพร้อมเปิดใหม่"

    def _remote_pause():
        global _script_paused
        if not _script_active:
            return "AutoMine ปิดอยู่"
        _script_paused = True
        release_keys()
        return "พักแล้ว — ส่ง `resume` เพื่อต่อ"

    def _remote_resume():
        global _script_paused, _auto_paused_by_detection, _auto_paused_by_focus
        if not _script_paused:
            return "AutoMine ไม่ได้พักอยู่"
        _script_paused = False
        _auto_paused_by_detection = _auto_paused_by_focus = False
        return "ต่อแล้ว"

    def _after_reconnect():
        """ต่อเซิร์ฟเวอร์สำเร็จ: รอโลกโหลด → พิมพ์คำสั่งที่ตั้งไว้ → (ถ้าเปิดไว้) เริ่มขุดต่อ"""
        global _script_active
        time.sleep(CONFIG["reconnect_settle_seconds"])
        for command, wait in CONFIG["reconnect_commands"]:
            minescript.execute(command)
            time.sleep(wait)
        if CONFIG["reconnect_resume"] and ctx["resume"]:
            ctx["resume"] = False
            _script_active = True
            _alert("▶️ AutoMine resumed after reconnect", "", "ok", True)
        else:
            _alert("Reconnected — AutoMine stays stopped", "ไปที่จุดขุดแล้วกด ] เพื่อเริ่ม", "info", True)

    _unfocused = None
    if CONFIG["mine_unfocused"]:
        _unfocused = UnfocusedAttack(CONFIG["unfocused_attack_tick_ms"])
        if not _unfocused.start():
            minescript.echo("§e[AutoMine] Background mining unavailable — จะ pause เมื่อหน้าต่างไม่โฟกัสแทน")
            _unfocused = None

    _link = BotLink("mining", _status_fields, {"stop": _remote_stop, "pause": _remote_pause, "resume": _remote_resume})
    _reconnector = Reconnector(_alert, after_connected=_after_reconnect)
    _reconnector.remember_server()

    if CONFIG["target_block"] == "select":
        minescript.echo("Look at a block to select it as the target...")
        while True:
            t = minescript.player_get_targeted_block()
            if t and t.type not in ("minecraft:air", "minecraft:bedrock"):
                CONFIG["target_block"] = t.type
                minescript.echo(f"[AutoMine] Target set to: {CONFIG['target_block']}")
                time.sleep(0.5)
                break
            time.sleep(0.1)

    processed_positions: set = set()
    _total_broken = 0
    start_hud()
    summary_update()
    _link.start()

    if CONFIG["enable_skill"]:
        start_chat_detection(event_queue)
        if not _skill_chat_active:
            debug_msg(f"⚡ Skill enabled (every {CONFIG['skill_interval']:.0f}s)")

    def _rounds():
        """ลูปขุดหลัก (เดิมอยู่ใน try โดยตรง) แยกเป็นฟังก์ชันเพื่อให้กลับมาทำงานต่อได้หลังหลุดเซิร์ฟเวอร์"""
        global _total_broken, _scan_cache_time, _last_safety_pos
        while True:
            # --- Events (key / world / chat): ดึงจนคิวว่าง แชทมาเป็นชุดได้ ---
            while True:
                try:
                    event = event_queue.get(block=False)
                except minescript.queue.Empty:
                    break
                except Exception as e:
                    debug_msg(f"[Event Error] {e}")
                    break
                try:
                    if event.type == minescript.EventType.KEY:
                        key_handler(event)
                    elif event.type == minescript.EventType.WORLD:
                        ctx["world_up"] = bool(event.connected)
                        _reconnector.world_event(event.connected)
                        if event.connected:
                            _reconnector.remember_server()
                        else:
                            if not _reconnector.active:   # หลุดซ้อนระหว่างกำลังต่อใหม่ ไม่ทับค่า resume เดิม
                                ctx["resume"] = _script_active
                            stop_script("disconnected from world", alert=False)
                            if not _reconnector.begin():   # begin() แจ้ง Discord เองเมื่อเริ่มต่อใหม่
                                bk_alert("🔌 Disconnected from world", "หยุด AutoMine แล้ว (ปิดการต่อใหม่อัตโนมัติ/ไม่รู้เซิร์ฟเวอร์)", "error", False)
                    elif event.type == minescript.EventType.CHAT:
                        on_chat_message(event.message)
                except Exception as e:
                    debug_msg(f"[Event Error] {e}")

            if not _script_active:
                _last_safety_pos = None
                time.sleep(0.05)
                continue

            check_focus()

            if _script_paused:
                _last_safety_pos = None   # ตอน pause ผู้เล่นขยับเองได้ ไม่นับเป็นการวาร์ป
                time.sleep(0.05)
                continue

            if minescript.screen_name() is not None:
                time.sleep(0.5)
                continue

            if should_use_skill():   # หลังเช็ค GUI: คลิกขวาตอนเปิดหน้าต่างอยู่จะไปกดของในหน้าต่างแทน
                use_skill()

            purge_expired_obstructed()

            # --- Cache player_pos once per loop ---
            player_pos = minescript.player_position()
            if check_teleport(player_pos):
                continue

            blocks = find_all_blocks(
                player_pos=player_pos,
                max_distance=CONFIG["search_distance"],
                block_type=CONFIG["target_block"],
                ignore_state=CONFIG["ignore_block_state"],
            )

            unprocessed = [
                b for b in blocks
                if b["position"] not in processed_positions
                and not is_obstructed(b["position"])
            ]

            if not unprocessed:
                debug_msg("No new blocks. Resetting cycle...")
                processed_positions.clear()
                _obstructed_positions.clear()
                _scan_cache_time = 0.0
                interruptible_sleep(0.8)
                continue

            # --- Pre-sort by distance (helps cluster quality + ordering) ---
            unprocessed.sort(key=lambda b: b["distance"])

            # --- Cluster ---
            if CONFIG["use_cluster_mode"]:
                clusters = cluster_blocks(unprocessed, threshold=CONFIG["cluster_distance"])
                sorted_clusters = sort_clusters(clusters, player_pos)
                ordered_blocks = []
                for cluster in sorted_clusters:
                    center = cluster_center(cluster)
                    members = sorted(cluster, key=lambda b: euclidean_distance(b["position"], center))
                    ordered_blocks.extend(members)
            else:
                ordered_blocks = unprocessed  # already sorted by distance

            # --- Batch visibility check (single API call for top N candidates) ---
            batch_size = CONFIG["visibility_batch_size"]
            candidates = ordered_blocks[:batch_size]
            candidate_positions = [b["position"] for b in candidates]
            aim_points = batch_visibility_check(player_pos, candidate_positions)

            # Filter to visible only; keep original order
            visible_blocks = [b for b in candidates if b["position"] in aim_points]

            # Mark invisible ones as obstructed (TTL)
            for b in candidates:
                if b["position"] not in aim_points:
                    debug_msg(f"OBSTRUCTED (no visible face point): {b['position']}")
                    add_obstructed(b["position"])

            if not visible_blocks:
                time.sleep(CONFIG["block_cooldown"])
                continue

            block_info = visible_blocks[0]
            x, y, z = block_info["position"]
            debug_msg(f"→ {block_info['full_type']} @ ({x},{y},{z}) {block_info['distance']:.1f}m")

            # --- Rotate + mine (เล็งจุดที่มองเห็นบนหน้าบล็อก) ---
            aim = aim_points[(x, y, z)]
            mined = smooth_look_at(
                target_pos=aim["point"],
                block_pos=(x, y, z),
                block_full_type=block_info["full_type"],
                player_pos=player_pos,
                width_deg=aim["width_deg"],
            )

            if mined:
                _total_broken += 1
                processed_positions.add((x, y, z))
                invalidate_position_from_cache((x, y, z))
                debug_msg(f"✓ Broken. Total: {_total_broken}")
                summary_update()

                # --- Instant neighbor check: จับ block ที่เกิดใหม่ทันที (เช่น titanium) ---
                if CONFIG["instant_neighbor_check"]:
                    instant_finds = instant_neighbor_scan((x, y, z), player_pos)
                    if instant_finds:
                        merge_into_scan_cache(instant_finds)
                        for nb in instant_finds:
                            npos = nb["position"]
                            # ถ้า block ใหม่เกิดที่ตำแหน่งเดิม (เช่น titanium แทน mithril)
                            # ให้เอาออกจาก processed/obstructed เพื่อให้ขุดต่อได้ทันที
                            if npos in processed_positions:
                                processed_positions.discard(npos)
                            if is_obstructed(npos):
                                _obstructed_positions.pop(npos, None)
                            debug_msg(f"⚡ Instant find: {nb['full_type']} @ {npos}")

                maybe_idle(mined)

            time.sleep(CONFIG["block_cooldown"])

    try:
        while True:
            try:
                _rounds()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                if not ctx["world_up"] or _reconnector.active:
                    # หลุดจากโลกแล้วคำสั่งเกมย่อมพัง: ไม่ใช่บั๊ก รอต่อใหม่
                    debug_msg(f"[Disconnected] ข้าม error ระหว่างหลุด: {type(e).__name__}: {e}")
                    release_keys()
                    time.sleep(1.0)
                    continue
                bk_alert("💥 AutoMine crashed", f"{type(e).__name__}: {e}", "error", True, wait=True)
                raise
    finally:
        _reconnector.cancel()
        try:
            minescript.player_press_attack(False)
        except Exception:
            pass
        stop_hud()
        bk_alert("⏹ AutoMine script ended", f"ขุดได้ {_total_broken} บล็อก ใน {fmt_duration(time.time() - _session_started)}", "warn", wait=True)
        _link.stop()
        minescript.echo("AutoMine v2 ended.")


if __name__ == "__main__":
    minescript.echo("§b╔════════════════════════════╗")
    minescript.echo("§b║  §e⚔ Mining Grinder Bot v2 ⚔  §b║")
    minescript.echo("§b╠════════════════════════════╣")
    minescript.echo("§b║ §f] toggle   [ pause       §b║")
    minescript.echo("§b╚════════════════════════════╝")
    main()