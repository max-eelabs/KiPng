# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Expose the shared backdrop tiles to the Qt Quick scene."""

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from ...contracts.background import BackgroundTexture
from ...export.background import checker_tile, colored_texture_tile


class BackgroundImageProvider(QQuickImageProvider):
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:
        if image_id == "checker":
            tile = checker_tile()
        else:
            texture, color = image_id.split("/", 1)
            tile = colored_texture_tile(f"#{color}", BackgroundTexture(texture))
        width, height = tile.size
        size.setWidth(width)
        size.setHeight(height)
        # Copy the borrowed Pillow bytes before returning the image to Qt.
        return QImage(tile.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888).copy()
