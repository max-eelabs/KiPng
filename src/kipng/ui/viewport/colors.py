# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Board color schemes for the interactive viewport."""

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class BoardColors:
    dielectric: str
    solder_mask: str
    mask_opacity: float
    silkscreen: str = "#f5f5f5"

    def layer_colors(self) -> dict[str, QColor]:
        mask = QColor(self.solder_mask)
        mask.setAlphaF(self.mask_opacity)
        return {
            "PCB": QColor(self.dielectric),
            "soldermask": mask,
            "silkscreen": QColor(self.silkscreen),
        }


# The linear RGB values and opacity are tuned together so masked copper
# stays distinct from the surrounding laminate in each palette.
DEFAULT_COLOR_SCHEME = "Green"
COLOR_SCHEMES = {
    DEFAULT_COLOR_SCHEME: BoardColors("#374334", "#064324", 0.64),
    "Red": BoardColors("#4a2424", "#8c1325", 0.68),
    "White": BoardColors("#e0deda", "#c3c6cc", 0.73, "#111316"),
    "Black": BoardColors("#15171d", "#111730", 0.73),
    "Blue": BoardColors("#202f5a", "#153986", 0.68),
    "Purple": BoardColors("#2f1d49", "#501e83", 0.69),
    "Yellow": BoardColors("#d7ad47", "#af7914", 0.66),
}
