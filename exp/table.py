import system.lib.lib_inv as inv
import minescript as m
import re
import sys
import time
import base64
import json
import functools

# --- Settings ---------------------------------------------------------------
spend_bits = True         # True = spend bits to recharge, False to turn off
is_serum = True           # True = serum active: every round cap is reduced by 3
SERUM_ROUND_PENALTY = 3

chroma_slot = 29
pairs_slot = 22
ultra_slot = 33
bits_slot = 31            # Costs bits + XP levels to reset

CHROMA_RANGE = (20, 25)
ULTRA_RANGE = (21, 24)

BOOKSHELF_SLOT = 4        # Item count = finished rounds
STATUS_SLOT = 49          # Glowstone = "Remember the pattern!", clock = "Timer: Xs"
ROUND_OFFSET = 1          
LATE_FLASH_POLLS = 15     
POLL_DELAY = 0.03         # Optimized for 20 Hz MC tick rate
CLICK_DELAY = 0.6

ULTRA_POLL_DELAY = 0.03   # Reduced from 0.01 to prevent RPC overhead
ULTRA_CLICK_DELAY = 0.12  
ULTRA_UNWANTED = ("glass", "clock", "star", "glowstone", "air")

COLOR_RE = re.compile(r"(?:minecraft:)?(\w+?)_(stained_glass|terracotta)$")
XP_COST_RE = re.compile(r"Starting cost:\s*(\d+)\s*XP Levels?", re.IGNORECASE)
XP_LEVELS_RE = re.compile(r"(\d[\d,]*)\s*XP Levels?", re.IGNORECASE)
EXP_RE = re.compile(r"\b\d+\s*k\b", re.IGNORECASE)
XP_BLOCK_RE = re.compile(r"\+\s*([\d,]+)\s*XP\b", re.IGNORECASE)   # lapis block: "+124,082 XP"
ENCHANT_RE = re.compile(r"^[A-Za-z' -]+ (?:[IVX]+|\d+)$")
# Enchant levels III / IV at the end of a name (VIII etc. do not match)
LOW_LEVEL_RE = re.compile(r"\b(?:III|IV)$", re.IGNORECASE)

XP_SHOP_SLOT = 50
XP_BUY_SLOT = 14
XP_MAX_ATTEMPTS = 40
XP_CLICK_DELAY = 0.5
XP_UPDATE_TIMEOUT = 3.0

PAIRS_BOARD = [row * 9 + col for row in (1, 2, 3, 4) for col in range(1, 8)]
PAIRS_CLICKS_SLOT = 4
PAIRS_TIMEOUT = 3.0
PAIRS_FLIP_TIMEOUT = 1.5  # max time to wait for mismatched tiles to flip back (never treated as matched)
PAIRS_DELAY = 0.12        # gap between the two clicks of a pair (was 0.25)
PAIRS_POLL = 0.03
SETTLE_STABLE = 4         # identical reads needed in settle() (was 8)
PAIRS_START_RATIO = 0.5   # Start matching pairs once clicks left <= initial clicks * this
PAIRS_EARLY_HIGH = False  # True = also pair known high value tiles before the halfway point
PAIRS_DEBUG = True        # Print the key/tier of every revealed tile

# High-value item ranking setup
HIGH_VALUE_ORDER = [
    "Nadeshiko Dye", "Looting V", "Critical VII", "Sharpness VI", "Giant Killer VII",
    "Prosecute VI", "Power VII", "First Strike V", "Cubism VI", "Protection VII",
    "Growth VII", "Snipe IV", "End Stone Idol", "Execute VI", "Golden Bounty",
    "Luck VII", "Triple-Strike V", "Life Steal V", "Cleave VI", "Chance V",
    "Drain V", "Gold Bottle Cap", "Severed Hand", "Titan Killer VII", "Troubled Bubble",
    "Thunderlord VII", "Gravity VI", "Octopus Tendril", "Fateful Stinger", "Vibrant Coral",
    "Projectile Protection VII", "Severed Pincer", "A Beginner's Guide to Pesthunting",
    "Protection VI", "Growth VI", "Fire Protection VII", "Chain of the End Times",
    "Thunderbolt VII", "Ensnared Snail", "Blast Protection VII",
]
HIGH_VALUE_RANK = {name.lower(): i for i, name in enumerate(HIGH_VALUE_ORDER)}
HIGH_VALUE = set(HIGH_VALUE_RANK)
NOT_RANKED = len(HIGH_VALUE_ORDER)

LOW_VALUE = {s.lower() for s in [
    "Venomous VI", "Life Steal IV", "Titanic Experience Bottle", "Scavenger V",
    "Giant Killer VI", "Ender Slayer VI", "Metaphysical Serum", "Drain IV",
    "Respite III", "Chance IV", "Power VI", "Fire Protection VI",
    "Blast Protection VI", "Woodsplitter VI", "Titan Killer VI", "Thunderbolt VI",
    "Projectile Protection VI", "Experiment the Fish","Grand Experience Bottle", "Experience Bottle",
]}

LOW_KEYWORDS = ("experience bottle", "metaphysical serum", "guardian")   # substring match -> always low value
KNOWN_NAME_RES = [
    (n, re.compile(r"(?<![\w])" + re.escape(n) + r"(?![\w])"))
    for n in sorted(HIGH_VALUE | LOW_VALUE, key=len, reverse=True)
]

TIER_HIGH, TIER_EXP, TIER_LOW, TIER_OTHER = 1, 2, 3, 4   # 4 = unclassified (still pairable, lowest priority)
GUARDIAN_PROFILE_ID = "f4c2cad70ace4ce6867869d0b653a98b"
GUARDIAN_TEXTURE_HASH = "221025434045bda7025b3e514b316a4b770c6faa4ba9adb4be3809526db77f9d"

# --- Helpers ----------------------------------------------------------------
def strip_color(text: str) -> str:
    """Strip Minecraft formatting codes."""
    return re.sub(r"\u00a7.", "", text) if text else ""


def get_lore(item):
    return item.get('components', {}).get('minecraft:lore', []) if item else []


def last_line(lore):
    return lore[-1].get('text', "") if lore else ""


def on_cooldown(lore):
    return "cooldown!" in last_line(lore)


def item_id(item):
    if not item:
        return ""
    return item.get('item') or item.get('id') or ""


AIR_RE = re.compile(r"(?:^|:)(?:void_|cave_)?air$")


def is_empty(item):
    """True for empty slots / minecraft:air (shown briefly while a tile flips)."""
    if not item:
        return True
    if AIR_RE.search(item_id(item)):
        return True
    return item.get('count', 1) == 0


def color_of(item):
    iid = item_id(item)
    if "glazed" in iid or "pane" in iid:
        return None
    match = COLOR_RE.match(iid)
    return (match.group(1), match.group(2) == "terracotta") if match else None


def open_table():
    m.player_press_use(True)
    m.player_press_use(False)
    time.sleep(1)


def reset_and_reopen(delay=0.5):
    inv.close()
    time.sleep(delay)
    open_table()


def pick_from_menu(first, last):
    menu = inv.inventory()
    for slot in range(last, first - 1, -1):
        if slot < len(menu) and "Click" in last_line(get_lore(menu[slot])):
            print(f"Selecting slot {slot}")
            inv.throw(slot)
            return slot
    print("No valid option found in menu")
    return None


def lore_text(item):
    text = " ".join(text_of(line) for line in get_lore(item))
    return strip_color(text)


def text_of(comp):
    if not comp:
        return ""
    if isinstance(comp, str):
        return comp
    if isinstance(comp, list):
        return "".join(text_of(c) for c in comp)
    if isinstance(comp, dict):
        return str(comp.get('text', "")) + "".join(text_of(c) for c in comp.get('extra', []))
    return str(comp)

def decode_textures(nbt_string):
    decoded = []
    for b64_value in re.findall(r'value:"([A-Za-z0-9+/=]+)"', nbt_string):
        try:
            decoded.append(json.loads(base64.b64decode(b64_value).decode("utf-8")))
        except Exception:
            pass
    return decoded


def guardian_equipped():
    try:
        for e in m.entities(max_distance=6, nbt=True):
            nbt = str(e.nbt or "")
            if "player_head" not in nbt:
                continue
            for t in decode_textures(nbt):
                skin_url = t.get("textures", {}).get("SKIN", {}).get("url", "")
                if (
                    t.get("profileName", "").lower() == "guardian"
                    or t.get("profileId", "") == GUARDIAN_PROFILE_ID
                    or GUARDIAN_TEXTURE_HASH in skin_url
                ):
                    return True
    except Exception:
        pass
    return False

# --- XP Handling ------------------------------------------------------------
def get_xp():
    try:
        player_uuid = m.player().uuid
        for entity in m.entities(nbt=True):
            if entity.type == "entity.minecraft.player" and entity.uuid == player_uuid:
                match = re.search(r"XpLevel:(\d+)", str(entity.nbt or ""))
                return match.group(1) if match else None
    except Exception:
        pass
    return None


def get_player_xp():
    raw = get_xp()
    return int(raw) if raw and raw.isdigit() else None


def wait_xp_change(before, timeout=XP_UPDATE_TIMEOUT):
    end = time.time() + timeout
    while time.time() < end:
        level = get_player_xp()
        if level is not None and level != before:
            return level
        time.sleep(0.1)
    return None


def check_out_of_coins():
    items = inv.inventory()
    if len(items) <= XP_BUY_SLOT:
        return
    item = items[XP_BUY_SLOT]
    text = (lore_text(item) + " " + tile_name(item)).lower()
    if "enough coins" in text:
        print("You don't have enough Coins! Stopping script")
        inv.close()
        sys.exit("Not enough coins to buy XP, script stopped")


def buy_xp(required):
    level = get_player_xp()
    if level is not None and level >= required:
        return True

    reset_and_reopen()
    inv.throw(XP_SHOP_SLOT)
    time.sleep(XP_CLICK_DELAY)

    for attempt in range(1, XP_MAX_ATTEMPTS + 1):
        check_out_of_coins()
        before = get_player_xp()
        inv.throw(XP_BUY_SLOT)
        level = wait_xp_change(before)
        if level is None:
            check_out_of_coins()
            print(f"XP level didn't change after buy {attempt} (level {before}), giving up")
            return False
        print(f"XP buy {attempt}: level {before} -> {level} / required {required}")
        if level >= required:
            return True

    print("Gave up: XP requirement not met")
    return False


def find_pairs_level(first, last):
    menu = inv.inventory()
    for slot in range(last, first - 1, -1):
        if slot >= len(menu) or not menu[slot]:
            continue
        item = menu[slot]
        lore = get_lore(item)
        if "Click" in last_line(lore) or "Click" in text_of(lore[-1] if lore else None):
            print(f"Selecting slot {slot}")
            inv.throw(slot)
            return slot, None

        full = lore_text(item)
        if "not enough experience" in full.lower():
            found = XP_COST_RE.search(full)
            if found:
                cost = int(found.group(1))
                print(f"Slot {slot} needs {cost} XP Levels")
                return None, cost

    print("No valid option found in menu")
    return None, None


# --- Minigames --------------------------------------------------------------
def after_game():
    time.sleep(0.5)
    inv.throw(11)
    time.sleep(0.5)
    open_table()


def scan_grid(prev, curr, color_slots):
    prev_lit = set()
    for slot in range(9, min(45, len(prev))):
        p = color_of(prev[slot])
        if p and p[1]:
            prev_lit.add(p[0])

    flashed = []
    for slot in range(9, min(45, len(curr))):
        c = color_of(curr[slot])
        if not c:
            continue
        color, lit = c
        if color not in color_slots or slot < color_slots[color]:
            color_slots[color] = slot

        p = color_of(prev[slot])
        if lit and p and not p[1] and color not in prev_lit and color not in flashed:
            flashed.append(color)

    return flashed


def chroma_game(target_rounds=10):
    sequence, idx, round_start_len = [], 0, 0
    replayed, last_status, started = False, None, False
    gone, clock_polls, rnd, color_slots = 0, 0, 0, {}
    prev = inv.inventory()

    print(f"Starting Chroma game (Target rounds: {target_rounds})...")

    while True:
        curr = inv.inventory()
        if len(curr) <= STATUS_SLOT:
            print("Menu closed, stopping")
            return

        status = item_id(curr[STATUS_SLOT])
        reading, clock = "glowstone" in status, "clock" in status

        if reading or clock:
            started, gone = True, 0
        elif started:
            gone += 1
            if gone >= 10:
                print(f"Game over ({status}), stopping")
                return

        shelf = curr[BOOKSHELF_SLOT]
        if shelf and "bookshelf" in item_id(shelf):
            new_rnd = shelf.get('count', 0)
            if new_rnd < rnd:
                sequence = []
            rnd = new_rnd

        flashed = scan_grid(prev, curr, color_slots)

        if status != last_status:
            if reading:
                idx, round_start_len, replayed, clock_polls = 0, len(sequence), False, 0
            last_status = status

        if flashed and (reading or (clock and not replayed)):
            color = flashed[0]
            if reading and idx < len(sequence):
                if sequence[idx] == color:
                    idx += 1
            elif len(sequence) == round_start_len:
                sequence.append(color)
                idx += 1
                print(f"New color: {color} (sequence: {sequence})")

        if clock and not replayed:
            clock_polls += 1
            if len(sequence) == round_start_len and clock_polls < LATE_FLASH_POLLS:
                pass
            else:
                print(f"Replaying: {sequence}")
                for i, color in enumerate(sequence):
                    slot = color_slots.get(color)
                    if slot is not None:
                        inv.throw(slot)
                        if i < len(sequence) - 1:
                            time.sleep(CLICK_DELAY)
                replayed = True
                curr = inv.inventory()
                if len(curr) <= STATUS_SLOT:
                    return

        if rnd >= target_rounds:
            print(f"Reached {rnd}/{target_rounds} bookshelves, closing")
            inv.close()
            after_game()
            return

        prev = curr
        time.sleep(POLL_DELAY)


def ultra_game(target_rounds=10):
    detected_slots, replayed = {}, False

    print(f"Starting Ultra game (Target rounds: {target_rounds})...")

    while True:
        curr = inv.inventory()
        if len(curr) <= STATUS_SLOT:
            print("Menu closed, stopping Ultra game")
            return

        status = item_id(curr[STATUS_SLOT])
        is_reading, is_clock = "glowstone" in status, "clock" in status

        if is_reading:
            if replayed:
                detected_slots.clear()
                replayed = False

            for slot_num in range(9, min(45, len(curr))):
                item = curr[slot_num]
                iid = item_id(item)
                count = item.get('count', 0) if item else 0
                if count > 0 and not any(u in iid for u in ULTRA_UNWANTED):
                    if slot_num not in detected_slots or count > detected_slots[slot_num]:
                        detected_slots[slot_num] = count

        elif is_clock and not replayed:
            if not detected_slots:
                for slot_num in range(9, min(45, len(curr))):
                    item = curr[slot_num]
                    iid = item_id(item)
                    count = item.get('count', 0) if item else 0
                    if count > 0 and not any(u in iid for u in ULTRA_UNWANTED):
                        detected_slots[slot_num] = count

            sequence = sorted(
                [{'slot': s, 'count': c} for s, c in detected_slots.items()],
                key=lambda x: x['count']
            )

            print(f"Clock detected! Replaying {len(sequence)} items")
            for entry in sequence:
                inv.throw(entry['slot'])
                time.sleep(ULTRA_CLICK_DELAY)

            replayed = True

            if len(sequence) >= target_rounds:
                print(f"Completed sequence {len(sequence)}/{target_rounds}")
                time.sleep(1)
                inv.close()
                after_game()
                return

        time.sleep(ULTRA_POLL_DELAY)


# --- Pairs Logic ------------------------------------------------------------
def tile_name(item):
    if not item:
        return ""
    comps = item.get('components', {})
    name = ""
    for raw in (comps.get('minecraft:custom_name'), comps.get('minecraft:item_name'), item.get('name')):
        name = strip_color(text_of(raw)).strip()
        if name:
            break
    # "Rare Book!" heads: the real enchant is in the lore, e.g. "Growth VI Grants +90 Health."
    # Lore lines contain extra text, so search the whole lore for a known enchant (longest name first).
    if name.lower().rstrip("! ") == "rare book":
        joined = " ".join(strip_color(text_of(l)).strip() for l in get_lore(item)).lower()
        for known_name, pattern in KNOWN_NAME_RES:
            if pattern.search(joined):
                return known_name
        for line in (strip_color(text_of(l)).strip() for l in get_lore(item)):
            if ENCHANT_RE.match(line):
                return line
    # Enchanted books are all named "Enchanted Book"; the real enchant is in the lore
    if item_id(item).endswith("enchanted_book") or name.lower() == "enchanted book":
        for line in get_lore(item):
            txt = strip_color(text_of(line)).strip()
            if txt and txt.lower() != "combinable in anvil":
                return txt
    return name


def tile_kind(item):
    iid = item_id(item)
    if is_empty(item):
        return "empty"      # air: tile is mid-flip, NOT a revealed item
    if "glass" in iid:
        return "hidden"
    name = tile_name(item).lower()
    if "instant find" in name:
        return "instant"
    if "+1 click" in name or "+3 click" in name:
        return "bonus"
    return "normal"


def tile_key(item):
    key = item_id(item) + "|" + tile_name(item)
    if tile_name(item).lower().rstrip("! ") == "rare book":
        key += "|" + lore_text(item)   # unidentified: don't let different books look equal
    if not EXP_RE.search(tile_name(item)):
        lore = " ".join(text_of(line) for line in get_lore(item))
        found = EXP_RE.search(lore)
        if found:
            key += "|" + found.group(0).lower()
    return key


def norm_name(name):
    return strip_color(name).strip().lower()


def tier_of_name(name):
    n = norm_name(name)
    if n in HIGH_VALUE:
        return TIER_HIGH
    if n in LOW_VALUE or LOW_LEVEL_RE.search(n) or any(k in n for k in LOW_KEYWORDS):
        return TIER_LOW
    if EXP_RE.search(n) or XP_BLOCK_RE.search(n):
        return TIER_EXP
    return TIER_OTHER


def key_name(key):
    """Name part of a tile key; unidentified 'Rare Book!' tiles are resolved via the lore text in the key."""
    rest = key.split("|", 1)[1] if "|" in key else key
    name = rest.split("|")[0]
    if name.lower().rstrip("! ") == "rare book":
        low = strip_color(rest).lower()
        for known_name, pattern in KNOWN_NAME_RES:
            if pattern.search(low):
                return known_name
    return name


@functools.lru_cache(maxsize=4096)
def tier_of_key(key):
    rest = key.split("|", 1)[1] if "|" in key else key
    tier = tier_of_name(key_name(key))
    if tier == TIER_OTHER and any(k in rest.lower() for k in LOW_KEYWORDS):
        return TIER_LOW   # name didn't match exactly, but key still says bottle/serum/guardian
    if tier == TIER_OTHER and (EXP_RE.search(rest) or XP_BLOCK_RE.search(rest)):
        return TIER_EXP
    return tier


@functools.lru_cache(maxsize=4096)
def rank_of_key(key):
    return HIGH_VALUE_RANK.get(norm_name(key_name(key)), NOT_RANKED)


def revealed_set(curr):
    return {s for s in PAIRS_BOARD if s < len(curr) and tile_kind(curr[s]) not in ("hidden", "empty")}


def wait_reveal(slot):
    end = time.time() + PAIRS_TIMEOUT
    while time.time() < end:
        curr = inv.inventory()
        if len(curr) <= PAIRS_BOARD[-1]:
            return None
        if tile_kind(curr[slot]) not in ("hidden", "empty"):
            return curr[slot]
        time.sleep(PAIRS_POLL)
    return None


def wait_hidden(slots, timeout=None):
    end = time.time() + (PAIRS_FLIP_TIMEOUT if timeout is None else timeout)
    curr = []
    while time.time() < end:
        curr = inv.inventory()
        if len(curr) <= PAIRS_BOARD[-1]:
            return
        if all(tile_kind(curr[s]) == "hidden" for s in slots):
            return
        time.sleep(PAIRS_POLL)


def settle():
    last, stable, end = None, 0, time.time() + PAIRS_TIMEOUT
    while time.time() < end and stable < SETTLE_STABLE:
        curr = inv.inventory()
        if len(curr) <= PAIRS_BOARD[-1]:
            return
        cur = revealed_set(curr)
        stable = stable + 1 if cur == last else 0
        last = cur
        time.sleep(0.03)


def find_known_pair(known, high_only=False):
    by_key = {}
    for slot, key in known.items():
        by_key.setdefault(key, []).append(slot)
    best = None
    for key, slots in by_key.items():
        t = tier_of_key(key)
        if len(slots) < 2 or t == TIER_LOW:
            continue
        if high_only and t != TIER_HIGH:
            continue
        # high value by rank, then exp from highest to lowest
        score = (t, rank_of_key(key), -exp_amount(key))
        if best is None or score < best[0]:
            best = (score, slots[0], slots[1])
    return (best[1], best[2]) if best else None


def remember(known, ignored, slot, key):
    if key.split("|", 1)[0] in ("", "minecraft:air", "air"):
        return  # never remember air
    if tier_of_key(key) == TIER_LOW:
        ignored.add(slot)       # seen it, don't waste clicks on it again
    else:
        known[slot] = key


@functools.lru_cache(maxsize=4096)
def exp_amount(key):
    block = XP_BLOCK_RE.search(key)
    if block:
        return int(block.group(1).replace(",", "")) // 1000
    found = EXP_RE.search(key)
    return int(re.search(r"\d+", found.group(0)).group()) if found else 0


def best_instant_target(known, high_only=False):
    best = None
    for slot, key in known.items():
        t = tier_of_key(key)
        if t > TIER_EXP or (high_only and t != TIER_HIGH):
            continue
        rank = (t, rank_of_key(key), -exp_amount(key))
        if best is None or rank < best[0]:
            best = (rank, slot)
    return best[1] if best else None


def pairs_game():
    print("[pairs v3] started")
    known = {}      # slot -> key of tiles we've seen and want to pair
    ignored = set() # low value tiles (never click again)
    done = set()    # tiles confirmed matched / consumed (only set explicitly, never guessed)
    initial_clicks, pairing = None, False
    idle = 0

    while True:
        curr = inv.inventory()
        if len(curr) <= PAIRS_BOARD[-1]:
            print("Menu closed, stopping")
            return

        shelf = curr[PAIRS_CLICKS_SLOT]
        if not shelf or "bookshelf" not in item_id(shelf):
            print("No clicks left, stopping")
            return

        clicks = shelf.get('count', 0)
        if initial_clicks is None:
            initial_clicks = clicks
        if not pairing and clicks <= initial_clicks * PAIRS_START_RATIO:
            pairing = True
            print(f"Clicks {clicks}/{initial_clicks}: switching to pairing mode")

        hidden = {sl for sl in PAIRS_BOARD if sl not in done and tile_kind(curr[sl]) == "hidden"}
        live = {sl: k for sl, k in known.items() if sl not in done}  # tile may still be flipping back; we wait before clicking
        unknown = [sl for sl in PAIRS_BOARD if sl in hidden and sl not in known and sl not in ignored]

        if not hidden and not any(sl not in done and tile_kind(curr[sl]) != "empty" for sl in PAIRS_BOARD):
            print("Board cleared")
            return

        # Explore first; once past the halfway point pair known tiles (high value first, then exp highest to lowest).
        pair = find_known_pair(live, high_only=not pairing) if (pairing or PAIRS_EARLY_HIGH) else None
        if pair:
            a, b = pair
            print(f"Pairing known tiles {a} + {b}: {known.get(a)}")
            wait_hidden([a, b], 4.0)   # make sure both are glass again before clicking
            inv.throw(a)
            wait_reveal(a)
            time.sleep(PAIRS_DELAY)
            inv.throw(b)
            wait_reveal(b)
            known.pop(a, None)
            known.pop(b, None)
            done.update((a, b))
            settle()
            idle = 0
            continue

        if not unknown:
            if not pairing:
                pairing = True
                continue
            # Some known tiles may not have flipped back yet; give them a moment
            if idle < 25 and any(sl in known and sl not in done for sl in PAIRS_BOARD):
                idle += 1
                time.sleep(0.2)
                continue
            print("No more useful tiles, stopping")
            return
        idle = 0

        a = unknown[0]
        inv.throw(a)
        item_a = wait_reveal(a)
        if item_a is None:
            time.sleep(0.3)
            continue

        kind_a, key_a = tile_kind(item_a), tile_key(item_a)
        t_a = tier_of_key(key_a)
        if PAIRS_DEBUG:
            print(f"Slot {a}: kind={kind_a} tier={t_a} key={key_a}")
        others = [sl for sl in unknown if sl != a] or [sl for sl in live if sl != a]

        if kind_a == "bonus":
            done.add(a)
            settle()
            continue

        if kind_a == "instant":
            done.add(a)
            target = best_instant_target(live, high_only=not pairing) or (others[0] if others else None)
            if target is not None:
                print(f"Instant find -> slot {target}")
                time.sleep(PAIRS_DELAY)
                inv.throw(target)
                known.pop(target, None)
                done.add(target)
            settle()
            continue

        # Known partner for this tile? Always take it for high value tiles, otherwise only in pairing mode
        if (pairing or (PAIRS_EARLY_HIGH and t_a == TIER_HIGH)) and t_a != TIER_LOW:
            partner = next((sl for sl, k in live.items() if k == key_a and sl != a), None)
            if partner is not None:
                print(f"Matching slot {a} with known slot {partner}: {key_a}")
                wait_hidden([partner], 4.0)
                time.sleep(PAIRS_DELAY)
                inv.throw(partner)
                wait_reveal(partner)
                known.pop(partner, None)
                done.update((a, partner))
                settle()
                continue

        if not others:
            remember(known, ignored, a, key_a)
            continue

        b = others[0]
        time.sleep(PAIRS_DELAY)
        inv.throw(b)
        item_b = wait_reveal(b)
        if item_b is None:
            remember(known, ignored, a, key_a)
            continue

        if tile_kind(item_b) == "instant":
            # Instant Find revealed as the 2nd click: use it just like when it is the 1st click
            remember(known, ignored, a, key_a)
            done.add(b)
            pool = {sl: k for sl, k in known.items() if sl not in done and sl != a}
            target = best_instant_target(pool, high_only=not pairing) or next(
                (sl for sl in unknown if sl not in (a, b)), None)
            if target is not None:
                print(f"Instant find (2nd click) -> slot {target}")
                time.sleep(PAIRS_DELAY)
                inv.throw(target)
                known.pop(target, None)
                done.add(target)
            settle()
            continue

        if tile_kind(item_b) != "normal":
            remember(known, ignored, a, key_a)
            if tile_kind(item_b) == "bonus":
                done.add(b)
            settle()
            continue

        key_b = tile_key(item_b)
        if PAIRS_DEBUG:
            print(f"Slot {b}: tier={tier_of_key(key_b)} key={key_b}")
        if key_a == key_b:
            known.pop(a, None)
            known.pop(b, None)
            done.update((a, b))
            settle()
        else:
            remember(known, ignored, a, key_a)
            remember(known, ignored, b, key_b)
            wait_hidden([a, b])


def handle_bits_option():
    if not spend_bits:
        return False

    items = inv.inventory()
    if len(items) <= bits_slot:
        return False

    if not (on_cooldown(get_lore(items[pairs_slot]))
            and on_cooldown(get_lore(items[chroma_slot]))
            and on_cooldown(get_lore(items[ultra_slot]))):
        return False

    text = lore_text(items[bits_slot])
    found = XP_LEVELS_RE.search(text)
    if not found:
        return False
    required = int(found.group(1).replace(",", ""))

    xp = get_player_xp()
    if xp is None:
        return False

    if xp < required:
        if not buy_xp(required):
            return False
        reset_and_reopen()
        items = inv.inventory()
        if len(items) <= bits_slot:
            return False
        text = lore_text(items[bits_slot])

    if "cannot afford this!" in text.lower():
        return False

    inv.throw(bits_slot)
    time.sleep(1)
    if m.screen_name() is None:
        open_table()
    return True


def main():
    
    if not guardian_equipped():
        sys.exit("Guardian pet not equipped, script stopped")
    
    open_table()

    while True:
        items = inv.inventory()
        pairs = get_lore(items[pairs_slot])
        chroma = get_lore(items[chroma_slot])
        ultra = get_lore(items[ultra_slot])

        if "Click" in last_line(pairs):
            inv.throw(pairs_slot)
            time.sleep(1)
            level_slot, xp_needed = find_pairs_level(21, 32)

            if level_slot is None and xp_needed is not None:
                if buy_xp(xp_needed):
                    reset_and_reopen()
                    inv.throw(pairs_slot)
                    time.sleep(1)
                    level_slot, _ = find_pairs_level(21, 32)

            if level_slot is not None:
                time.sleep(1)
                pairs_game()
                time.sleep(0.5)
                inv.close()
                time.sleep(0.5)
                inv.throw(13)
                time.sleep(0.5)
                open_table()
                continue

        if not on_cooldown(chroma):
            inv.throw(chroma_slot)
            time.sleep(0.5)
            selected_slot = pick_from_menu(*CHROMA_RANGE)
            if selected_slot is not None:
                chroma_game((13 if selected_slot == 24 else 10) - (SERUM_ROUND_PENALTY if is_serum else 0))
                time.sleep(1)
                continue

        if not on_cooldown(ultra):
            inv.throw(ultra_slot)
            time.sleep(0.5)
            selected_slot = pick_from_menu(*ULTRA_RANGE)
            if selected_slot is not None:
                ultra_game((8 if selected_slot == 23 else 6) - (SERUM_ROUND_PENALTY if is_serum else 0))
                time.sleep(1)
                continue

        if handle_bits_option():
            continue

        print("Nothing left to play, done")
        return


if __name__ == "__main__":
    main()