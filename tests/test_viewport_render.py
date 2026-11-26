# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

from threading import Event
from unittest.mock import Mock

from PIL import Image
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox

from kipng.contracts import BoardSnapshot, ViewportCamera
from kipng.contracts.colors import COLOR_SCHEMES
from kipng.ui.controls import render
from kipng.ui.controls.panel import ControlsPanel
from kipng.ui.viewport.pane import BoardViewport


def test_viewport_engine_captures_selected_settings_and_saves_png(app, monkeypatch, tmp_path):
    # Replace the GPU with a frame that can be saved by the real worker.
    viewport = BoardViewport()
    camera = ViewportCamera(-55, 40, 0.2, -0.01, 0.02, 0.1, 0.07)
    monkeypatch.setattr(viewport, "capture_camera", lambda: camera)
    monkeypatch.setattr(render.QFileDialog, "getExistingDirectory", lambda *_: str(tmp_path))
    released = []

    class Capture(QObject):
        captured = Signal(QImage)
        failed = Signal(str)

        def __init__(self, view, pose, colors, size):
            super().__init__()
            # The renderer receives the selected view, color, and portrait dimensions.
            assert (view, pose, colors, size) == (
                viewport,
                camera,
                COLOR_SCHEMES["Blue"],
                (1080, 1440),
            )

        def start(self):
            # Only the GUI thread may capture the viewport.
            assert QThread.currentThread() == app.thread()
            image = QImage(1080, 1440, QImage.Format.Format_RGB32)
            image.fill(QColor("blue"))
            self.captured.emit(image)

        def release(self):
            released.append(True)

    monkeypatch.setattr(render, "ViewportCapture", Capture)
    ray_tracer = Mock()
    panel = ControlsPanel(lambda: viewport, ray_tracer, Event())
    panel.set_ready(BoardSnapshot("board", tmp_path, "project"))
    engine, palette, _, aspect_ratio = panel.findChildren(QComboBox)
    controls = panel.render_controls
    try:
        # Switch engines, export one PNG, and wait for the save worker.
        engine.setCurrentText("Viewport")
        palette.setCurrentText("Blue")
        aspect_ratio.setCurrentText("3:4")
        controls.button.click()
        for _ in range(100):
            if controls.button.isEnabled():
                break
            QTest.qWait(20)

        # The capture was released and the ray tracer was bypassed.
        assert controls.button.isEnabled()
        assert released == [True]
        ray_tracer.assert_not_called()
        (png,) = tmp_path.glob("*.png")
        with Image.open(png) as image:
            assert image.size == (1080, 1440)
            assert image.getpixel((0, 0)) == (0, 0, 255)
    finally:
        panel.shutdown()
        viewport.close()
