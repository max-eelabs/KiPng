# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assemble the right panel and discover source modules for its control sections."""

import logging
from collections.abc import Callable
from importlib import import_module
from pkgutil import iter_modules
from threading import Event

from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from ...contracts import BoardSnapshot, ImageRenderer
from ..viewport.pane import BoardViewport
from . import sections
from .render import RenderControls

LOGGER = logging.getLogger(__name__)


class ControlsPanel(QWidget):
    def __init__(
        self,
        get_viewport: Callable[[], BoardViewport | None],
        renderer: ImageRenderer | None,
        cancelled: Event,
    ) -> None:
        super().__init__()
        self.get_viewport = get_viewport
        self.snapshot: BoardSnapshot | None = None
        self.setFixedWidth(240)
        self.setEnabled(False)

        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        body = QWidget()
        section_layout = QVBoxLayout(body)
        section_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        for module in sorted(iter_modules(sections.__path__), key=lambda item: item.name):
            if module.ispkg or module.name.startswith("_"):
                continue
            try:
                factory = import_module(f"{sections.__name__}.{module.name}").create_section
                section_layout.addWidget(factory(get_viewport))
            except Exception:
                LOGGER.exception("Could not load controls section %s", module.name)

        section_layout.addStretch(1)
        self.render_controls = RenderControls(renderer, cancelled) if renderer else None
        if self.render_controls is not None:
            self.render_controls.button.setEnabled(False)
            self.render_controls.button.clicked.connect(self.start_render)
            layout.addWidget(self.render_controls)

    def set_ready(self, snapshot: BoardSnapshot | None) -> None:
        self.snapshot = snapshot
        self.setEnabled(True)
        if self.render_controls is not None:
            self.render_controls.button.setEnabled(snapshot is not None)

    def start_render(self) -> None:
        view = self.get_viewport()
        if self.render_controls is not None and self.snapshot is not None and view is not None:
            self.render_controls.start(self.snapshot, view.capture_camera())

    def stop_polling(self) -> None:
        if self.render_controls is not None:
            self.render_controls.poll.stop()

    def shutdown(self) -> None:
        if self.render_controls is not None:
            self.render_controls.shutdown()
