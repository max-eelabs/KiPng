# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Background settings shared by the preview and PNG renderers."""

from dataclasses import dataclass
from enum import Enum

WHITE = "#FFFFFF"
BACKGROUND_COLORS = {
    "White": WHITE,
    "Transparent": None,
    "Warm Stone": "#E4DDD2",
    "Mist Blue": "#DCE5EB",
    "Sage Gray": "#D8E0D6",
    "Dusty Rose": "#EADDDD",
    "Soft Slate": "#AAB5C2",
}


class BackgroundTexture(Enum):
    NONE = "none"
    FABRIC_GRAIN = "fabric-grain"
    CRINKLED_PAPER = "crinkled-paper"

    @property
    def label(self) -> str:
        return self.value.replace("-", " ").title()


@dataclass(frozen=True)
class BackgroundSettings:
    """An opaque RGB hex color or None for transparency, with an optional texture."""

    color: str | None = WHITE
    texture: BackgroundTexture = BackgroundTexture.NONE

    @property
    def allows_texture(self) -> bool:
        return self.color is not None and self.color.upper() != WHITE

    @property
    def effective_texture(self) -> BackgroundTexture:
        return self.texture if self.allows_texture else BackgroundTexture.NONE


DEFAULT_BACKGROUND = BackgroundSettings()
