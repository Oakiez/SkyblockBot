from system.lib import minescript as ms
import time
import threading

# ==================== CONFIGURATION ====================

# Key Controls
PAUSE_KEY = 93  # ] key for pause/resume
START_STOP_KEY = 295  # F6 key for start/stop

# Camera settings
FARM_LOOK_YAW = -90.0  # Yaw angle to look while farming
FARM_LOOK_PITCH = 5.5  # Pitch angle to look while farming

# Farm settings
STUCK_CHECK_THRESHOLD = 0.01  # Movement threshold to detect wall
STUCK_CHECK_COUNT = 3  # Number of checks before considering stuck
INVENTORY_TIMEOUT = 5.0  # Seconds without inventory change before auto-pause

# Speed settings
MAX_SPEED = 93

# ==================== GLOBAL STATE ====================

is_running = False
paused = False
round_count = 0
detected_restart = False

# ==================== UTILITY FUNCTIONS ====================


def smooth_look_at(target_yaw, target_pitch, steps=10, delay=0.05):
    """Smoothly rotates the camera to a fixed direction"""
    current_yaw, current_pitch = ms.player_orientation()

    # Normalize yaw range
    while target_yaw > 180:
        target_yaw -= 360
    while target_yaw < -180:
        target_yaw += 360

    for i in range(steps + 1):
        t = i / steps
        smooth_t = t * t * (3.0 - 2.0 * t)  # Smoothstep interpolation
        lerp_yaw = current_yaw + (target_yaw - current_yaw) * smooth_t
        lerp_pitch = current_pitch + (target_pitch - current_pitch) * smooth_t
        ms.player_set_orientation(lerp_yaw, lerp_pitch)
        if i < steps:
            time.sleep(delay)


def stop_all_movement():
    """Stop all player movement"""
    ms.player_press_left(False)
    ms.player_press_right(False)
    ms.player_press_forward(False)
    ms.player_press_backward(False)
    ms.player_press_attack(False)
    ms.player_press_use(False)


def get_inventory_hash():
    """Get a hash of current inventory for change detection"""
    inventory = ms.player_inventory()
    inv_string = ""
    for item in inventory:
        inv_string += f"{item.item}:{item.count}:{item.slot}|"
    return inv_string


def check_pause():
    """Check if paused and wait until resumed"""
    global paused
    if paused:
        ms.echo("=== Farm PAUSED - Press ] to resume ===")
        stop_all_movement()

        pause_start = time.time()
        while paused:
            time.sleep(0.1)

        pause_duration = time.time() - pause_start
        ms.echo("=== Farm RESUMED ===")
        return pause_duration
    return 0


# ==================== DISPLAY FUNCTIONS ====================


def fancy_echo(message, style="info"):
    """Display fancy messages"""
    styles = {
        "info": {"color": "aqua", "symbol": "ℹ"},
        "success": {"color": "green", "symbol": "✓"},
        "warning": {"color": "yellow", "symbol": "⚠"},
        "round": {"color": "light_purple", "symbol": "🔄"},
        "move": {"color": "gold", "symbol": "➜"},
        "finish": {"color": "green", "symbol": "★"},
    }

    s = styles.get(style, styles["info"])
    ms.echo_json(
        [
            {"text": f"{s['symbol']} ", "color": s["color"], "bold": True},
            {"text": message, "color": "white"},
        ]
    )


def celebrate_round(round_num):
    """Celebrate round completion"""
    ms.echo_json(
        [
            {"text": "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "color": "gold", "bold": True},
            {"text": "\n   🎉 ", "color": "yellow", "bold": True},
            {"text": f"Round {round_num} Complete!", "color": "green", "bold": True},
            {"text": " 🎉", "color": "yellow", "bold": True},
            {"text": "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n", "color": "gold", "bold": True},
        ]
    )


# ==================== INITIALIZATION ====================


def initialize_farm():
    """Initialize farm settings before starting"""

    # Adjust camera view
    ms.echo_json(
        [
            {"text": "📷 ", "color": "aqua", "bold": True},
            {
                "text": f"Adjusting camera (Yaw: {FARM_LOOK_YAW}°, Pitch: {FARM_LOOK_PITCH}°)...",
                "color": "white",
            },
        ]
    )
    smooth_look_at(FARM_LOOK_YAW, FARM_LOOK_PITCH, steps=15, delay=0.03)
    time.sleep(0.2)

    # Set max speed
    ms.echo_json(
        [
            {"text": "⚙ ", "color": "yellow", "bold": True},
            {"text": f"Setting max speed to {MAX_SPEED}...", "color": "white"},
        ]
    )
    ms.execute(f"/setmaxspeed {MAX_SPEED}")
    time.sleep(0.3)

    # Set spawn location
    ms.echo_json(
        [
            {"text": "📍 ", "color": "light_purple", "bold": True},
            {"text": "Setting spawn location...", "color": "white"},
        ]
    )
    ms.execute("/setspawnlocation")
    time.sleep(0.3)

    # Switch hotbar slot and switch back
    ms.echo_json(
        [
            {"text": "🎒 ", "color": "aqua", "bold": True},
            {"text": "Switching hotbar slot...", "color": "white"},
        ]
    )

    current_slot = ms.player_inventory_select_slot(1)
    time.sleep(0.3)

    ms.echo_json(
        [
            {"text": "🎒 ", "color": "aqua", "bold": True},
            {"text": "Switching back to original slot...", "color": "white"},
        ]
    )

    ms.player_inventory_select_slot(current_slot)
    time.sleep(0.3)

    # Wait 3 seconds before starting
    ms.echo_json(
        [
            {"text": "⏳ ", "color": "yellow", "bold": True},
            {"text": "Starting in 3 seconds...", "color": "white"},
        ]
    )
    time.sleep(3)

    fancy_echo("Ready to farm!", "success")


# ==================== CORE FARMING LOGIC ====================


def harvest_direction(direction_name, direction_key, movement_num):
    """
    Harvest in one direction until hitting a wall (detected by position check)

    Args:
        direction_name: Display name (e.g., "Left")
        direction_key: 'A' or 'D'
        movement_num: Movement number for display
    """
    global paused, is_running

    ms.echo_json(
        [
            {"text": "│ ", "color": "dark_aqua"},
            {"text": f"[{movement_num}] ", "color": "gray"},
            {
                "text": f"{'←' if direction_key == 'A' else '→'} ",
                "color": "yellow",
                "bold": True,
            },
            {"text": f"Moving {direction_name} ", "color": "white"},
            {"text": "(until wall)", "color": "aqua", "bold": True},
        ]
    )

    # Initialize tracking variables
    last_inventory = get_inventory_hash()
    last_inventory_change_time = time.time()

    # Get starting position
    player_data = ms.player()
    last_x, last_z = player_data.position[0], player_data.position[2]
    stuck_counter = 0

    # Stop everything first
    stop_all_movement()
    time.sleep(0.1)

    # Start movement and attack
    if direction_key == "A":
        ms.player_press_left(True)
    else:
        ms.player_press_right(True)

    time.sleep(0.1)
    ms.player_press_attack(True)
    time.sleep(0.1)

    check_interval = 0.2  # Check every 0.2 seconds
    last_check_time = time.time()

    while is_running:
        current_time = time.time()

        # Check pause
        pause_duration = check_pause()
        if pause_duration > 0:
            last_inventory_change_time += pause_duration
            # Resume movement
            if direction_key == "A":
                ms.player_press_left(True)
            else:
                ms.player_press_right(True)
            ms.player_press_attack(True)
            stuck_counter = 0
            last_check_time = current_time

        # Periodic checks
        if current_time - last_check_time >= check_interval:
            last_check_time = current_time

            # Check inventory change
            current_inventory = get_inventory_hash()
            if current_inventory != last_inventory:
                last_inventory = current_inventory
                last_inventory_change_time = current_time
                stuck_counter = 0  # Reset stuck counter on inventory change

            # Check for inventory timeout (auto-pause)
            time_since_change = current_time - last_inventory_change_time
            if time_since_change > INVENTORY_TIMEOUT:
                ms.echo(f"⚠ Inventory hasn't updated for {INVENTORY_TIMEOUT}s")
                ms.echo("=== Auto-paused: Press ] to resume ===")

                stop_all_movement()
                paused = True

                while paused:
                    time.sleep(0.1)

                # Resume after manual unpause
                last_inventory_change_time = time.time()
                last_inventory = get_inventory_hash()
                ms.echo("Resuming movement...")

                if direction_key == "A":
                    ms.player_press_left(True)
                else:
                    ms.player_press_right(True)
                ms.player_press_attack(True)
                stuck_counter = 0
                continue

            # Check position for wall detection
            player_data = ms.player()
            current_x, current_z = player_data.position[0], player_data.position[2]
            distance_moved = abs(current_x - last_x) + abs(current_z - last_z)

            if distance_moved < STUCK_CHECK_THRESHOLD:
                stuck_counter += 1
                if stuck_counter >= STUCK_CHECK_COUNT:
                    ms.echo(f"✓ Hit wall, switching direction")
                    break
            else:
                stuck_counter = 0

            last_x, last_z = current_x, current_z

        time.sleep(0.05)

    # Stop movement
    stop_all_movement()
    time.sleep(0.2)


# ==================== MAIN FARM LOOP ====================


def auto_farm():
    """Main auto farm system"""
    global is_running, paused, round_count

    # Welcome message
    ms.echo_json(
        [
            {
                "text": "\n╔════════════════════════════════════╗",
                "color": "aqua",
                "bold": True,
            },
            {"text": "\n║  ", "color": "aqua", "bold": True},
            {"text": "🚜 Smart Auto Farm v2.0 🚜", "color": "gold", "bold": True},
            {"text": "     ║", "color": "aqua", "bold": True},
            {
                "text": "\n╠════════════════════════════════════╣",
                "color": "aqua",
                "bold": True,
            },
            {"text": "\n║  ", "color": "aqua"},
            {"text": "Press F6", "color": "yellow", "bold": True},
            {"text": " to Start/Stop", "color": "white"},
            {"text": "           ║", "color": "aqua"},
            {"text": "\n║  ", "color": "aqua"},
            {"text": "Press ]", "color": "yellow", "bold": True},
            {"text": " to Pause/Resume", "color": "white"},
            {"text": "          ║", "color": "aqua"},
            {"text": "\n║  ", "color": "aqua"},
            {"text": "Press Ctrl+C", "color": "red", "bold": True},
            {"text": " to Exit Script", "color": "white"},
            {"text": "      ║", "color": "aqua"},
            {
                "text": "\n╠════════════════════════════════════╣",
                "color": "aqua",
                "bold": True,
            },
            {"text": "\n║  ", "color": "aqua"},
            {"text": "🎯 Wall Detection Enabled", "color": "green"},
            {"text": "       ║", "color": "aqua"},
            {"text": "\n║  ", "color": "aqua"},
            {"text": "📊 Auto-Pause on Stuck", "color": "green"},
            {"text": "          ║", "color": "aqua"},
            {
                "text": "\n╚════════════════════════════════════╝\n",
                "color": "aqua",
                "bold": True,
            },
        ]
    )

    initialized = False

    # Event queue for key detection
    event_queue = ms.EventQueue()
    event_queue.register_key_listener()

    def check_key_events():
        global is_running, paused
        while True:
            try:
                event = event_queue.get(block=False)
                if event.type == "key" and event.action == 1:  # Key press
                    if event.key == START_STOP_KEY:  # F6
                        is_running = not is_running
                        if is_running:
                            ms.echo_json(
                                [
                                    {
                                        "text": "╔═══════════════════════════════╗",
                                        "color": "green",
                                        "bold": True,
                                    },
                                    {"text": "\n║ ", "color": "green", "bold": True},
                                    {
                                        "text": "🌾 Farm System Started! 🌾",
                                        "color": "gold",
                                        "bold": True,
                                    },
                                    {"text": "    ║", "color": "green", "bold": True},
                                    {
                                        "text": "\n╚═══════════════════════════════╝",
                                        "color": "green",
                                        "bold": True,
                                    },
                                ]
                            )
                        else:
                            ms.echo_json(
                                [
                                    {
                                        "text": "╔═══════════════════════════════╗",
                                        "color": "red",
                                        "bold": True,
                                    },
                                    {"text": "\n║ ", "color": "red", "bold": True},
                                    {
                                        "text": "⏸ Farm System Stopped",
                                        "color": "yellow",
                                    },
                                    {"text": "        ║", "color": "red", "bold": True},
                                    {
                                        "text": "\n╚═══════════════════════════════╝",
                                        "color": "red",
                                        "bold": True,
                                    },
                                ]
                            )
                            stop_all_movement()

                    elif event.key == PAUSE_KEY:  # ]
                        if is_running:
                            paused = not paused
                            if paused:
                                ms.echo("⏸ PAUSED - Press ] to resume")
                            else:
                                ms.echo("▶ RESUMED")
            except:
                pass
            time.sleep(0.05)

    # Start key event thread
    key_thread = threading.Thread(target=check_key_events, daemon=True)
    key_thread.start()

    try:
        while True:
            # Wait if not running
            if not is_running:
                initialized = False
                time.sleep(0.1)
                continue

            # Initialize on first start
            if not initialized:
                initialize_farm()
                initialized = True

            # Start new round
            round_count += 1
            check_pause()

            # Round header
            ms.echo_json(
                [
                    {"text": f"\n┌─── ", "color": "dark_aqua", "bold": True},
                    {
                        "text": f"Round {round_count}",
                        "color": "light_purple",
                        "bold": True,
                    },
                    {"text": " ───┐", "color": "dark_aqua", "bold": True},
                ]
            )

            # Pattern: A D A D A D (until wall each time)
            movements = [
                ("Left", "A", 1),
                ("Right", "D", 2),
                ("Left", "A", 3),
                ("Right", "D", 4),
                ("Left", "A", 5),
                ("Right", "D", 6),
            ]

            for direction_name, direction_key, movement_num in movements:
                if not is_running:
                    break

                check_pause()
                harvest_direction(direction_name, direction_key, movement_num)

            if not is_running:
                continue

            # End of round - warp back
            ms.echo_json(
                [
                    {"text": "│ ", "color": "dark_aqua"},
                    {
                        "text": "🔚 Round complete, warping back...",
                        "color": "light_purple",
                        "bold": True,
                    },
                ]
            )

            stop_all_movement()
            ms.execute("/warp garden")
            time.sleep(2)

            ms.echo_json(
                [
                    {
                        "text": "└───────────────────────┘\n",
                        "color": "dark_aqua",
                        "bold": True,
                    }
                ]
            )

            # Celebrate round completion
            celebrate_round(round_count)

            time.sleep(1)

    except KeyboardInterrupt:
        ms.echo_json(
            [
                {
                    "text": "\n╔════════════════════════════════════╗",
                    "color": "red",
                    "bold": True,
                },
                {"text": "\n║ ", "color": "red", "bold": True},
                {"text": "🛑 Farm System Stopped", "color": "white", "bold": True},
                {"text": "            ║", "color": "red", "bold": True},
                {
                    "text": "\n╠════════════════════════════════════╣",
                    "color": "red",
                    "bold": True,
                },
                {"text": "\n║  ", "color": "red"},
                {"text": f"Rounds completed: ", "color": "white"},
                {"text": f"{round_count}", "color": "gold", "bold": True},
                {"text": "              ║", "color": "red"},
                {
                    "text": "\n╚════════════════════════════════════╝\n",
                    "color": "red",
                    "bold": True,
                },
            ]
        )
    finally:
        stop_all_movement()
        fancy_echo("All keys released ✓", "success")


if __name__ == "__main__":
    auto_farm()
