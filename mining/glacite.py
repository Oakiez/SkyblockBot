# -*- coding: utf-8 -*-
from system.lib import minescript
import math
import time
import threading
import random
from system.lib.minescript import EventType
from mining.rotation import rotate

# ------------------------------
# --- Configuration
# ------------------------------

CONFIG = {
    # --- General ---
    "rotation_speed": 0.75,  # Speed for the new rotation system
    "toggle_key": 82,  # 'R' Key
    "min_attack_cps": 7,  # Minimum attacks per second
    "max_attack_cps": 20,  # Maximum attacks per second
    # --- Patrol ---
    "patrol_path": [(0, 128, 166), (6, 128, 160), (0, 128, 154)],
    "waypoint_tolerance": 1.5,  # How close to get to a waypoint (in blocks)
    # --- Combat ---
    "mob_search_range": 10.0,  # How far to look for targets
    "attack_range": 3.5,  # How close to attack targets
    "target_bot_names": [
        "Ice Walker",
        # "AnotherBotName",
    ],
    # --- Healing ---
    "low_health_threshold": 12.0,  # Flee if health is AT or BELOW this
    "full_health_threshold": 36.0,  # Return when health is AT this
    "heal_spot": (0, 128, 108),
    "heal_slot_index": 6,  # Slot 7 (indexes 0-8)
    "combat_slot_index": 0,  # Slot 1 (indexes 0-8)
    # --- NOWA FUNKCJA ---
    "ability_cooldown": 7.0,  # Co 7 sekund
    "ability_slot_index": 7,  # Slot 8 (indeksy 0-8)
}

# ------------------------------
# --- Global State
# ------------------------------

STATE = {
    "active": False,
    "script_mode": "PATROLLING",  # PATROLLING, COMBAT, HEALING
    "current_patrol_index": 0,
    "my_name": "",
    "my_id": "",
    "last_attack_time": 0.0,
    "attack_cooldown": 1.0
    / random.randint(CONFIG["min_attack_cps"], CONFIG["max_attack_cps"]),
    "last_ability_time": 0.0,  # Timer dla nowej umiejętności
}

# Keep track of camera velocity for smooth looking - REMOVED

try:
    player_data = minescript.player()
    STATE["my_name"] = player_data.name
    STATE["my_id"] = player_data.uuid
except Exception as e:
    print(f"Could not get player data: {e}")

# ------------------------------
# --- Threading for Looking
# ------------------------------

look_lock = threading.Lock()
current_look = [None]  # Tuple: (yaw, pitch, urgent)
look_thread = [None]
look_thread_running = [False]


def thread_look():
    """Continuously looks at the target specified in current_look."""
    look_thread_running[0] = True
    while look_thread_running[0]:
        with look_lock:
            target = current_look[0]

        if target:
            yaw, pitch, speed = target
            # This is a blocking call that performs a smooth rotation.
            rotate(yaw, pitch, speed=speed)
        else:
            # No target, wait a bit to avoid busy-looping
            time.sleep(0.05)


def start_look_thread():
    """Starts the look thread if it's not already running."""
    if look_thread[0] is None or not look_thread[0].is_alive():
        look_thread_running[0] = True
        look_thread[0] = threading.Thread(target=thread_look, daemon=True)
        look_thread[0].start()
        minescript.echo("§a[Grinder] Look thread started.")


def stop_look_thread():
    """Stops the look thread."""
    look_thread_running[0] = False
    if look_thread[0] and look_thread[0].is_alive():
        look_thread[0].join(timeout=0.1)
    look_thread[0] = None
    with look_lock:
        current_look[0] = None
    minescript.echo("§c[Grinder] Look thread stopped.")


# ------------------------------
# --- Helper Functions
# ------------------------------


def _get_player_data():
    try:
        return minescript.player()
    except Exception:
        return None


def _h_dist(pos1, pos2):
    dx = pos1[0] - pos2[0]
    dz = pos1[2] - pos2[2]
    return math.sqrt(dx * dx + dz * dz)


def calculate_look_angles(player_pos, target_pos):
    player_eye_pos = (player_pos[0], player_pos[1] + 1.62, player_pos[2])
    dx = target_pos[0] - player_eye_pos[0]
    dy = target_pos[1] - player_eye_pos[1]
    dz = target_pos[2] - player_eye_pos[2]
    h_dist = math.sqrt(dx * dx + dz * dz)

    yaw = math.degrees(math.atan2(-dx, dz))
    pitch = -math.degrees(math.atan2(dy, h_dist))
    return yaw, pitch


def stop_all_actions():
    """Stops all player movement and actions."""
    minescript.player_press_forward(False)
    minescript.player_press_backward(False)
    minescript.player_press_left(False)
    minescript.player_press_right(False)
    minescript.player_press_attack(False)
    # minescript.player_press_sprint(False) # <-- USUNIĘTE (naprawa buga ze sprintem)
    minescript.player_press_jump(False)


# ------------------------------
# --- Core Logic Functions
# ------------------------------


def find_best_target():
    """Finds the nearest named bot from the config list."""
    try:
        nearby_players = minescript.players(
            max_distance=CONFIG["mob_search_range"], sort="nearest"
        )

        for target in nearby_players:
            if (
                target.name in CONFIG["target_bot_names"]
                and target.uuid != STATE["my_id"]
            ):
                try:
                    if target.health > 0:
                        return target
                except AttributeError:
                    continue

    except Exception as e:
        minescript.echo(f"§c[Grinder] Error finding target: {e}")
    return None


def handle_combat(target):
    """Faces, moves towards, and attacks the target."""
    global STATE

    player_pos = minescript.player_position()
    if not player_pos:
        return

    target_pos = target.position
    target_eye_pos = (target_pos[0], target_pos[1] + 1.6, target_pos[2])
    dist = _h_dist(player_pos, target_pos)

    # 1. Aim
    player_pos = minescript.player_position()
    if player_pos:
        yaw, pitch = calculate_look_angles(player_pos, target_eye_pos)
        with look_lock:
            current_look[0] = (yaw, pitch, CONFIG["rotation_speed"])

    # 2. Move
    if dist > CONFIG["attack_range"] * 0.8:
        # Move towards target
        minescript.player_press_forward(True)
        # minescript.player_press_sprint(True) # <-- USUNIĘTE (naprawa buga ze sprintem)
        minescript.player_press_backward(False)
    else:
        # Close enough, stop moving forward
        minescript.player_press_forward(False)
        # minescript.player_press_sprint(False) # <-- USUNIĘTE (naprawa buga ze sprintem)

    # 3. Attack
    current_time = time.time()
    if dist <= CONFIG["attack_range"] and (
        current_time - STATE["last_attack_time"] > STATE["attack_cooldown"]
    ):
        minescript.player_press_attack(True)
        time.sleep(0.01)
        minescript.player_press_attack(False)
        STATE["last_attack_time"] = current_time

        # Set a new random cooldown for the next attack
        random_cps = random.randint(CONFIG["min_attack_cps"], CONFIG["max_attack_cps"])
        STATE["attack_cooldown"] = 1.0 / random_cps


def handle_patrol():
    """Moves the player along the defined patrol path."""
    global STATE

    player_pos = minescript.player_position()
    if not player_pos:
        return

    target_waypoint = CONFIG["patrol_path"][STATE["current_patrol_index"]]
    dist = _h_dist(player_pos, target_waypoint)

    if dist < CONFIG["waypoint_tolerance"]:
        # Reached waypoint, advance to the next one
        STATE["current_patrol_index"] = (STATE["current_patrol_index"] + 1) % len(
            CONFIG["patrol_path"]
        )
        target_waypoint = CONFIG["patrol_path"][STATE["current_patrol_index"]]

    # Look towards the waypoint (at player height)
    look_target_pos = (target_waypoint[0], player_pos[1] + 1.62, target_waypoint[2])
    yaw, pitch = calculate_look_angles(player_pos, look_target_pos)
    with look_lock:
        current_look[0] = (
            yaw,
            pitch,
            CONFIG["rotation_speed"] / 2,
        )  # Slower speed for patrolling

    # Move towards the waypoint
    # stop_all_actions() # <-- USUNIĘTE (to powodowało migotanie sprintu)
    minescript.player_press_forward(True)
    # minescript.player_press_sprint(True) # <-- USUNIĘTE (naprawa buga ze sprintem)


def handle_healing():
    """Moves to the heal spot, uses the heal item, and waits."""
    global STATE

    player_pos = minescript.player_position()
    if not player_pos:
        return

    heal_spot = CONFIG["heal_spot"]
    dist = _h_dist(player_pos, heal_spot)

    if dist > CONFIG["waypoint_tolerance"]:
        # Not at heal spot yet, move there
        look_target_pos = (heal_spot[0], player_pos[1] + 1.62, heal_spot[2])
        yaw, pitch = calculate_look_angles(player_pos, look_target_pos)
        with look_lock:
            current_look[0] = (
                yaw,
                pitch,
                CONFIG["rotation_speed"] / 2,
            )  # Slower speed for healing

        # stop_all_actions() # <-- USUNIĘTE (to powodowało migotanie sprintu)
        minescript.player_press_forward(True)
        # minescript.player_press_sprint(True) # <-- USUNIĘTE (naprawa buga ze sprintem)
    else:
        # At heal spot
        stop_all_actions()

        # Check health again *after* stopping
        player_data = _get_player_data()
        if player_data and player_data.health >= CONFIG["full_health_threshold"]:
            minescript.echo("§a[Grinder] Fully healed! Returning to patrol.")
            STATE["script_mode"] = "PATROLLING"

            # (OSTRZEŻENIE: Ta linia może powodować błąd)
            try:
                minescript.player_inventory_select_slot(CONFIG["combat_slot_index"])
            except Exception as e:
                minescript.echo(f"§c[Heal Error] Failed to switch slot: {e}")
            return

        # We are at the spot and still need healing
        try:
            # (OSTRZEŻENIE: Te linie mogą powodować błąd)
            minescript.player_inventory_select_slot(CONFIG["heal_slot_index"])
            time.sleep(0.1)
            minescript.player_press_use(True)
            time.sleep(0.1)
            minescript.player_press_use(False)
            minescript.player_inventory_select_slot(CONFIG["combat_slot_index"])

        except Exception as e:
            minescript.echo(f"§c[Grinder] Heal failed (API Error?): {e}")
            STATE["script_mode"] = "PATROLLING"  # Avoid getting stuck


# ------------------------------
# --- Event Handler
# ------------------------------


def key_handler(event):
    """Handles key presses to toggle the script."""
    global STATE
    if event.key == CONFIG["toggle_key"] and event.action == 1:
        STATE["active"] = not STATE["active"]
        status = "§aENABLED" if STATE["active"] else "§cDISABLED"
        minescript.echo(f"§b[Grinder] §fScript has been {status}§f.")

        if STATE["active"]:
            start_look_thread()
        else:
            stop_look_thread()
            stop_all_actions()
            STATE["script_mode"] = "PATROLLING"


# ------------------------------
# --- Script Entry Point
# ------------------------------

if __name__ == "__main__":
    minescript.echo(
        f"§b[Grinder] §fLoaded. Press §e'R'§f to toggle."
    )  # Zmieniono 'O' na 'R'
    if not STATE["my_name"]:
        minescript.echo("§c[Grinder Warning] §fCould not get self-player data.")

    # Ustawiamy czas ostatniej umiejętności na teraz, aby uniknąć natychmiastowego użycia
    STATE["last_ability_time"] = time.time()

    with minescript.EventQueue() as event_queue:
        event_queue.register_key_listener()

        while True:
            # 1. Handle Key-press Events
            try:
                event = event_queue.get(block=False)
                if event.type == EventType.KEY:
                    key_handler(event)
            except minescript.queue.Empty:
                pass
            except Exception as e:
                minescript.echo(f"§c[Event Error] {e}")

            # 2. Check if script is active
            if not STATE["active"]:
                time.sleep(0.1)
                continue

            # 3. Main State Machine
            try:
                # --- State Checks ---
                player_data = _get_player_data()
                if not player_data:
                    time.sleep(0.1)
                    continue

                current_health = player_data.health

                if (
                    current_health <= CONFIG["low_health_threshold"]
                    and STATE["script_mode"] != "HEALING"
                ):
                    minescript.echo("§c[Grinder] Low health! Fleeing to heal.")
                    stop_all_actions()
                    STATE["script_mode"] = "HEALING"

                elif (
                    current_health >= CONFIG["full_health_threshold"]
                    and STATE["script_mode"] == "HEALING"
                ):
                    # (Sprawdzanie powrotu do zdrowia jest teraz w handle_healing())
                    pass

                target = None
                if STATE["script_mode"] != "HEALING":
                    target = find_best_target()
                    if target:
                        if STATE["script_mode"] != "COMBAT":
                            STATE["script_mode"] = "COMBAT"
                    elif STATE["script_mode"] == "COMBAT":
                        STATE["script_mode"] = "PATROLLING"

                # --- State Actions ---
                if STATE["script_mode"] == "HEALING":
                    handle_healing()
                elif STATE["script_mode"] == "COMBAT":
                    handle_combat(target)
                elif STATE["script_mode"] == "PATROLLING":
                    handle_patrol()

                # --- NOWA FUNKCJA: Ability Cooldown Check ---
                current_time = time.time()
                # if (
                #     current_time - STATE["last_ability_time"]
                #     > CONFIG["ability_cooldown"]
                # ) and STATE["script_mode"] != "HEALING":
                #     try:
                #         # (OSTRZEŻENIE: Te linie mogą powodować błąd)
                #         minescript.echo("§d[Grinder] Using ability...")
                #         minescript.player_inventory_select_slot(
                #             CONFIG["ability_slot_index"]
                #         )
                #         time.sleep(0.1)
                #         minescript.player_press_use(True)
                #         time.sleep(0.1)
                #         minescript.player_press_use(False)
                #         time.sleep(0.5)
                #         minescript.player_inventory_select_slot(
                #             CONFIG["combat_slot_index"]
                #         )
                #         STATE["last_ability_time"] = current_time
                #     except Exception as e:
                #         minescript.echo(f"§c[Ability Error] Failed to use ability: {e}")
                #         # Reset timera, aby nie spamował błędami
                #         STATE["last_ability_time"] = current_time

            except Exception as e:
                minescript.echo(f"§c[Main Loop Error] {e}")
                stop_all_actions()

            # Prevent 100% CPU usage
            time.sleep(0.01)
