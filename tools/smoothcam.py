import math
import time
from system.lib import minescript

def _wrap_angle(deg: float) -> float:
    return deg % 360

def _shortest_diff(target: float, current: float) -> float:
    return (target - current + 180) % 360 - 180

def _cubic_smooth(t: float) -> float:
    """S-curve easing 0->1"""
    return 3 * t**2 - 2 * t**3

def look(yaw: float, pitch: float, duration: float = 1):
    """
    Smoothly rotate camera toward given yaw & pitch.
    """
    start_time = time.time()
    while True:
        now = time.time()
        elapsed = now - start_time
        t = min(elapsed / duration, 1.0)
        factor = _cubic_smooth(t)

        current_yaw, current_pitch = minescript.player_orientation()

        dyaw = _shortest_diff(yaw, current_yaw)
        yaw_now = _wrap_angle(current_yaw + dyaw * factor)

        dpitch = _shortest_diff(pitch, current_pitch)
        pitch_now = max(-90.0, min(90.0, current_pitch + dpitch * factor))

        minescript.player_set_orientation(yaw_now, pitch_now)

        if t >= 1.0:
            break

        time.sleep(0.001)

def look_tick(yaw: float, pitch: float, factor: float = 0.2):
    """
    Apply a single incremental rotation step toward target yaw & pitch.
    factor: 0 < factor <= 1, proportion of remaining angle to rotate this tick.
    """
    current_yaw, current_pitch = minescript.player_orientation()

    dyaw = _shortest_diff(yaw, current_yaw)
    yaw_now = _wrap_angle(current_yaw + dyaw * factor)

    dpitch = _shortest_diff(pitch, current_pitch)
    pitch_now = max(-90.0, min(90.0, current_pitch + dpitch * factor))

    minescript.player_set_orientation(yaw_now, pitch_now)

def lookat(x: float, y: float, z: float, duration: float = 0.8):
    """
    Smoothly rotate camera to look at a block position (x, y, z).
    """
    px, py, pz = minescript.player_position()
    dx, dy, dz = (x + 0.5 - px, y - 1 - py, z + 0.5 - pz)
    horiz_dist = math.hypot(dx, dz)

    target_yaw = _wrap_angle(math.degrees(math.atan2(dz, dx)) - 90)
    target_pitch = max(-90.0, min(90.0, -math.degrees(math.atan2(dy, horiz_dist))))

    look(target_yaw, target_pitch, duration)

def lookat_tick(x: float, y: float, z: float, factor: float = 0.2):
    """
    Apply a single incremental rotation step to look at a block position.
    """
    px, py, pz = minescript.player_position()
    dx, dy, dz = (x + 0.5 - px, y - 1 - py, z + 0.5 - pz)
    horiz_dist = math.hypot(dx, dz)

    target_yaw = _wrap_angle(math.degrees(math.atan2(dz, dx)) - 90)
    target_pitch = max(-90.0, min(90.0, -math.degrees(math.atan2(dy, horiz_dist))))

    look_tick(target_yaw, target_pitch, factor)