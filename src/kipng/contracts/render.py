# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render engines and supported PNG dimensions."""

from dataclasses import dataclass
from enum import Enum


class RenderEngine(Enum):
    RAY_TRACING = "Ray Tracing"
    VIEWPORT = "Viewport"


# The front pose assumes the board lies lengthwise along Z.
FRONT_PITCH = -82
FRONT_YAW = -34
# Turning both angles by 180 flips to the underside and mirrors the view.
CAMERA_PRESETS = (
    ("Default Front", FRONT_PITCH, FRONT_YAW, True),
    ("Default Back", FRONT_PITCH + 180, FRONT_YAW + 180, True),
    ("Straight Top", -90, 0, False),
    ("Straight Bottom", 90, 180, False),
)

DEFAULT_OUTPUT_SIZE = (1080, 1920)
FHD_SIZES = {
    "9:16": DEFAULT_OUTPUT_SIZE,
    "3:4": (1080, 1440),
    "16:9": (1920, 1080),
    "4:3": (1440, 1080),
    "1:1": (1080, 1080),
}
RESOLUTION_SCALES = {"FHD": 1, "4K": 2}

SLIDER_MAX = 100
SHADOW_MIDPOINT = SLIDER_MAX // 2
LIGHT_TRAVEL = 16


@dataclass(frozen=True)
class ShadowSettings:
    """Light coordinates in [-100, 100] and shadow strength in [0, 100]."""

    light_x: int = 0
    light_y: int = 0
    strength: int = SHADOW_MIDPOINT

    @property
    def offset_x(self) -> float:
        """Horizontal shadow offset in FHD pixels, positive to the right."""
        return 3 - LIGHT_TRAVEL * self.light_x / SLIDER_MAX

    @property
    def offset_y(self) -> float:
        """Vertical shadow offset in FHD pixels, positive down the image."""
        return 4 + LIGHT_TRAVEL * self.light_y / SLIDER_MAX

    @property
    def opacity(self) -> float:
        return 0.1798 * min(1.0, self.strength / SHADOW_MIDPOINT)

    @property
    def blur_factor(self) -> float:
        return min(1.0, (SLIDER_MAX - self.strength) / SHADOW_MIDPOINT)


DEFAULT_SHADOW = ShadowSettings()
