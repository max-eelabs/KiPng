# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Color scheme and PNG format settings for the Render section."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QSlider, QVBoxLayout, QWidget

from ....contracts.options import (
    ASPECT_RATIO,
    COLOR_SCHEME,
    ENGINE,
    LIGHT_X,
    LIGHT_Y,
    RESOLUTION,
    SHADOW,
    Control,
    RenderOptions,
)
from ....contracts.render import RenderEngine, ShadowSettings
from ...viewport.colors import COLOR_SCHEMES
from ...viewport.pane import BoardViewport
from ._background import add_background_controls


def combo_box(control: Control) -> QComboBox:
    combo = QComboBox()
    combo.addItems(control.labels)
    combo.setCurrentText(control.default)
    return combo


def create_section(get_viewport: Callable[[], BoardViewport | None]) -> QWidget:
    section = QWidget()
    layout = QVBoxLayout(section)
    layout.setContentsMargins(0, 0, 0, 0)
    heading = QLabel("Render")
    font = heading.font()
    font.setBold(True)
    heading.setFont(font)
    layout.addWidget(heading)

    def apply_engine(name: str) -> None:
        viewport = get_viewport()
        if viewport is not None:
            viewport.render_engine = RenderEngine(name)

    engine = combo_box(ENGINE)
    engine.currentTextChanged.connect(apply_engine)

    def apply_color_scheme(name: str) -> None:
        viewport = get_viewport()
        if viewport is not None:
            viewport.set_color_scheme(COLOR_SCHEMES[name])

    color_scheme = combo_box(COLOR_SCHEME)
    color_scheme.currentTextChanged.connect(apply_color_scheme)

    resolution = combo_box(RESOLUTION)
    aspect_ratio = combo_box(ASPECT_RATIO)

    def apply_output_size() -> None:
        viewport = get_viewport()
        if viewport is not None:
            settings = RenderOptions(
                resolution=resolution.currentText(), aspect_ratio=aspect_ratio.currentText()
            )
            viewport.set_output_size(settings.output_size)

    resolution.currentTextChanged.connect(apply_output_size)
    aspect_ratio.currentTextChanged.connect(apply_output_size)
    options = QFormLayout()
    options.addRow(ENGINE.label, engine)
    options.addRow(COLOR_SCHEME.label, color_scheme)
    add_background_controls(options, get_viewport)
    options.addRow(RESOLUTION.label, resolution)
    options.addRow(ASPECT_RATIO.label, aspect_ratio)
    add_shadow_controls(options, get_viewport)
    layout.addLayout(options)
    return section


def add_shadow_controls(
    options: QFormLayout, get_viewport: Callable[[], BoardViewport | None]
) -> None:
    light_x = QSlider(Qt.Orientation.Horizontal)
    light_y = QSlider(Qt.Orientation.Horizontal)
    shadow = QSlider(Qt.Orientation.Horizontal)
    light_x.setToolTip("Move the light left or right to shift the drop shadow.")
    light_y.setToolTip("Move the light down or up to shift the drop shadow.")
    shadow.setToolTip("Off at the left, soft at the center, and sharp at the right.")

    def apply_shadow() -> None:
        viewport = get_viewport()
        if viewport is not None:
            viewport.set_shadow(ShadowSettings(light_x.value(), light_y.value(), shadow.value()))

    for control, slider in ((LIGHT_X, light_x), (LIGHT_Y, light_y), (SHADOW, shadow)):
        slider.setRange(*control.limits)
        slider.setValue(control.default)
        slider.setAccessibleName(control.label)
        slider.valueChanged.connect(apply_shadow)
        options.addRow(control.label, slider)
