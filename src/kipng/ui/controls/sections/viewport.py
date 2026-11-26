# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Camera presets and framing guide for the viewport."""

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....contracts.render import CAMERA_PRESETS
from ...viewport.pane import BoardViewport


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

    def show_render_frame(visible: bool) -> None:
        viewport = get_viewport()
        if viewport is not None:
            viewport.show_render_frame(visible)

    guide = QCheckBox("Show Render Frame")
    guide.toggled.connect(show_render_frame)
    layout.addWidget(guide)
    return section
