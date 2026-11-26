# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Background presets, custom color input, and texture selection."""

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit

from ....contracts.background import BACKGROUND_COLORS, BackgroundSettings, BackgroundTexture
from ....contracts.options import BACKGROUND, RGB_HEX, TEXTURE, slug
from ...viewport.pane import BoardViewport

CUSTOM = "Custom"
DEFAULT_CUSTOM_COLOR = "#E4DDD2"


def swatch(color: str | None) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor(color or "#F4F5F6"))
    painter = QPainter(pixmap)
    if color is None:
        checker = QColor("#E4E6E8")
        painter.fillRect(0, 0, 8, 8, checker)
        painter.fillRect(8, 8, 8, 8, checker)
    painter.setPen(QColor("#70757A"))
    painter.drawRect(0, 0, 15, 15)
    painter.end()
    return QIcon(pixmap)


def add_background_controls(
    options: QFormLayout, get_viewport: Callable[[], BoardViewport | None]
) -> None:
    selector = QComboBox(objectName="backgroundSelector")
    for name in BACKGROUND.labels:
        selector.addItem(swatch(BACKGROUND_COLORS[name]), name)
    selector.setCurrentText(BACKGROUND.default)
    selector.addItem(swatch(DEFAULT_CUSTOM_COLOR), CUSTOM)
    custom_index = selector.count() - 1

    custom = QLineEdit(DEFAULT_CUSTOM_COLOR, objectName="backgroundHex")
    custom.setPlaceholderText("#RRGGBB")
    hint = QLabel(wordWrap=True, objectName="backgroundHexHint")
    texture = QComboBox(objectName="backgroundTexture")
    for label in TEXTURE.labels:
        texture.addItem(label, slug(label))
    options.addRow(BACKGROUND.label, selector)
    options.addRow("Hex Color", custom)
    options.addRow(hint)
    options.addRow(TEXTURE.label, texture)
    custom_color = DEFAULT_CUSTOM_COLOR
    preferred_texture = BackgroundTexture(slug(TEXTURE.default))

    def apply_background() -> None:
        nonlocal custom_color
        is_custom = selector.currentText() == CUSTOM
        match = RGB_HEX.fullmatch(custom.text().strip()) if is_custom else None
        if match:
            color = f"#{match[1].upper()}"
            if color != custom_color:
                custom_color = color
                selector.setItemIcon(custom_index, swatch(custom_color))

        options.setRowVisible(custom, is_custom)
        show_hint = is_custom and match is None
        if show_hint:
            hint.setText(f"Enter 6 hex digits. Using {custom_color}.")
        options.setRowVisible(hint, show_hint)
        color = custom_color if is_custom else BACKGROUND_COLORS[selector.currentText()]
        settings = BackgroundSettings(color, preferred_texture)
        active_texture = settings.effective_texture
        texture.setEnabled(settings.allows_texture)
        with QSignalBlocker(texture):
            texture.setCurrentIndex(texture.findData(active_texture.value))
        viewport = get_viewport()
        if viewport is not None:
            viewport.set_background(BackgroundSettings(color, active_texture))

    def select_background() -> None:
        if selector.currentText() == CUSTOM:
            custom.setText(custom_color)
        apply_background()

    def select_texture() -> None:
        nonlocal preferred_texture
        preferred_texture = BackgroundTexture(texture.currentData())
        apply_background()

    selector.currentTextChanged.connect(select_background)
    custom.textChanged.connect(apply_background)
    texture.currentIndexChanged.connect(select_texture)
    apply_background()
