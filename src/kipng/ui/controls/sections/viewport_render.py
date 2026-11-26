# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Color scheme and PNG format settings for the Render section."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QSlider, QVBoxLayout, QWidget

from ....contracts.render import (
    DEFAULT_SHADOW,
    FHD_SIZES,
    RESOLUTION_SCALES,
    SLIDER_MAX,
    RenderEngine,
    ShadowSettings,
)
from ...viewport.colors import COLOR_SCHEMES
from ...viewport.pane import BoardViewport
from ._background import add_background_controls


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

    engine = QComboBox()
    engine.addItems([engine.value for engine in RenderEngine])
    engine.currentTextChanged.connect(apply_engine)

    def apply_color_scheme(name: str) -> None:
        viewport = get_viewport()
        if viewport is not None:
            viewport.set_color_scheme(COLOR_SCHEMES[name])

    color_scheme = QComboBox()
    color_scheme.addItems(list(COLOR_SCHEMES))
    color_scheme.currentTextChanged.connect(apply_color_scheme)

    resolution = QComboBox()
    resolution.addItems(list(RESOLUTION_SCALES))
    aspect_ratio = QComboBox()
    aspect_ratio.addItems(list(FHD_SIZES))

    def apply_output_size() -> None:
        viewport = get_viewport()
        if viewport is not None:
            scale = RESOLUTION_SCALES[resolution.currentText()]
            width, height = FHD_SIZES[aspect_ratio.currentText()]
            viewport.set_output_size((width * scale, height * scale))

    resolution.currentTextChanged.connect(apply_output_size)
    aspect_ratio.currentTextChanged.connect(apply_output_size)
    options = QFormLayout()
    options.addRow("Engine", engine)
    options.addRow("Color Scheme", color_scheme)
    add_background_controls(options, get_viewport)
    options.addRow("Resolution", resolution)
    options.addRow("Aspect Ratio", aspect_ratio)
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

    for label, slider, minimum, default in (
        ("Light X", light_x, -SLIDER_MAX, DEFAULT_SHADOW.light_x),
        ("Light Y", light_y, -SLIDER_MAX, DEFAULT_SHADOW.light_y),
        ("Shadow", shadow, 0, DEFAULT_SHADOW.strength),
    ):
        slider.setRange(minimum, SLIDER_MAX)
        slider.setValue(default)
        slider.setAccessibleName(label)
        slider.valueChanged.connect(apply_shadow)
        options.addRow(label, slider)
