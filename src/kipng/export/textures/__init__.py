# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Register the procedural texture tile generators shared by both renderers."""

from ...contracts.background import BackgroundTexture
from . import crinkled_paper, fabric_grain

# Each entry maps a grayscale tile generator to its maximum RGB channel offset.
TEXTURES = {
    BackgroundTexture.FABRIC_GRAIN: (fabric_grain.tile, 23),
    BackgroundTexture.CRINKLED_PAPER: (crinkled_paper.tile, 29),
}
