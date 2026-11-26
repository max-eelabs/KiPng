# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Camera presets and board colors for the viewport."""

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....contracts.render import FHD_SIZES, RESOLUTION_SCALES
from ...viewport.colors import COLOR_SCHEMES
from ...viewport.pane import FRONT_PITCH, FRONT_YAW, BoardViewport

# Turning both angles by 180 flips to the underside and mirrors the view.
CAMERA_PRESETS = (
    ("Default Front", FRONT_PITCH, FRONT_YAW, True),
    ("Default Back", FRONT_PITCH + 180, FRONT_YAW + 180, True),
    ("Straight Top", -90, 0, False),
    ("Straight Bottom", 90, 180, False),
)


def create_section(get_viewport: Callable[[], BoardViewport | None]) -> QWidget:
    section = QWidget()
    layout = QVBoxLayout(section)
    layout.setContentsMargins(0, 0, 0, 0)
    heading = QLabel("Viewport")
    font = heading.font()
    font.setBold(True)
    heading.setFont(font)
    layout.addWidget(heading)

    def apply_view(pitch: float, yaw: float, align_long_axis: bool) -> None:
        viewport = get_viewport()
        if viewport is not None:
            viewport.set_camera_view(pitch, yaw, align_long_axis)

    presets = QGridLayout()
    for index, (label, *view) in enumerate(CAMERA_PRESETS):
        button = QPushButton(label)
        button.clicked.connect(lambda _checked=False, view=view: apply_view(*view))
        presets.addWidget(button, index // 2, index % 2)
    layout.addLayout(presets)

    def apply_color_scheme(name: str) -> None:
        viewport = get_viewport()
        if viewport is not None:
            viewport.set_color_scheme(COLOR_SCHEMES[name])

    color_scheme = QComboBox()
    color_scheme.addItems(list(COLOR_SCHEMES))
    color_scheme.currentTextChanged.connect(apply_color_scheme)
    options = QFormLayout()
    options.addRow("Color Scheme", color_scheme)

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
    options.addRow("Resolution", resolution)
    options.addRow("Aspect Ratio", aspect_ratio)
    layout.addLayout(options)

    def show_render_frame(visible: bool) -> None:
        viewport = get_viewport()
        if viewport is not None:
            viewport.show_render_frame(visible)

    guide = QCheckBox("Show Render Frame")
    guide.toggled.connect(show_render_frame)
    layout.addWidget(guide)
    return section
