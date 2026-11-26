# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render engines and supported PNG dimensions."""

from enum import Enum


class RenderEngine(Enum):
    RAY_TRACING = "Ray Tracing"
    VIEWPORT = "Viewport"


DEFAULT_OUTPUT_SIZE = (1080, 1920)
FHD_SIZES = {
    "9:16": DEFAULT_OUTPUT_SIZE,
    "3:4": (1080, 1440),
    "16:9": (1920, 1080),
    "4:3": (1440, 1080),
    "1:1": (1080, 1080),
}
RESOLUTION_SCALES = {"FHD": 1, "4K": 2}
