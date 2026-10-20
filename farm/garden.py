# -*- coding: utf-8 -*-
"""
garden.py — Layout ของ Garden และ plot centers
"""

GARDEN_MIN_X, GARDEN_MAX_X = -239, 239
GARDEN_MIN_Z, GARDEN_MAX_Z = -239, 239
PLOT_SIZE = (GARDEN_MAX_X - GARDEN_MIN_X) / 5
PLOT_HALF = PLOT_SIZE / 2

GARDEN_LAYOUT = [
    [21, 13,  9, 14, 22],
    [15,  5,  1,  6, 16],
    [10,  2, 25,  3, 11],
    [17,  7,  4,  8, 18],
    [23, 19, 12, 20, 24],
]

PLOT_CENTERS: dict[int, tuple[float, float]] = {
    plot: (
        GARDEN_MIN_X + col * PLOT_SIZE + PLOT_HALF,
        GARDEN_MIN_Z + row * PLOT_SIZE + PLOT_HALF,
    )
    for row, cols in enumerate(GARDEN_LAYOUT)
    for col, plot in enumerate(cols)
}
