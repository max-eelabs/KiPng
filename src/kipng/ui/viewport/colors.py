# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Convert shared board palettes to Qt material colors."""

from PySide6.QtGui import QColor

from ...contracts.colors import COLOR_SCHEMES as COLOR_SCHEMES
from ...contracts.colors import BoardColors


def layer_colors(scheme: BoardColors) -> dict[str, QColor]:
    mask = QColor(scheme.solder_mask)
    mask.setAlphaF(scheme.mask_opacity)
    return {
        "PCB": QColor(scheme.dielectric),
        "soldermask": mask,
        "silkscreen": QColor(scheme.silkscreen),
    }
