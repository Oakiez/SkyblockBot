from system.lib.minescript import (
    player_orientation,
    player_set_orientation,
    player_position,
)
from time import perf_counter
from math import sqrt, degrees, atan2, cos, pi


def linear(t: float):
    return t


def easeInOut(t: float):
    return -(cos(pi * t) - 1) / 2


def easeOutQuad(t: float):
    return -t * (t - 2)


def rotate_releative(
    x: float, y: float, speed: float = 1, func: classmethod = easeInOut
):
    o, start_time, time, t = (
        player_orientation(),
        perf_counter(),
        0 if speed == 0 else sqrt(x**2 + y**2) / (speed * 360),
        0,
    )
    while t < 1:
        t = (perf_counter() - start_time) / time
        player_set_orientation(o[0] + x * func(t), o[1] + y * func(t))
    player_set_orientation(o[0] + x, o[1] + y)


def rotate(x: float, y: float, speed: float = 1, func: classmethod = easeInOut):
    o = player_orientation()
    x, y = x - o[0], y - o[1]
    rotate_releative(x % 180 - (180 if x % 360 > 180 else 0), y, speed, func)


def look_at_releative(
    x: float, y: float, z: float, speed: float = 1, func: classmethod = easeInOut
):
    x, y = -degrees(atan2(x, z)) if z != 0 else 0, -degrees(
        atan2((y - 1.6), sqrt(x**2 + z**2))
    )
    rotate(x, y, speed, func)


def look_at(
    x: float, y: float, z: float, speed: float = 1, func: classmethod = easeInOut
):
    p = player_position()
    x, y, z = x - p[0], y - p[1], z - p[2]
    look_at_releative(x, y, z, speed, func)


def look_at_block(
    x: int, y: int, z: int, speed: float = 1, func: classmethod = easeInOut
):
    look_at(x + 0.5, y + 0.5, z + 0.5, speed, func)
