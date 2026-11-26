# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

from threading import Event
from unittest.mock import Mock

import pytest
from PIL import Image
from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox, QSlider

from kipng.contracts import BoardSnapshot, ViewportCamera
from kipng.contracts.background import BackgroundSettings
from kipng.contracts.colors import COLOR_SCHEMES
from kipng.contracts.render import DEFAULT_SHADOW, ShadowSettings
from kipng.ui.controls import render
from kipng.ui.controls.panel import ControlsPanel
from kipng.ui.viewport.pane import VIEWPORT_QML, BoardViewport
from kipng.ui.viewport.render import save_viewport_render


def test_viewport_engine_captures_selected_settings_and_saves_png(app, monkeypatch, tmp_path):
    # Replace the GPU with a frame that can be saved by the real worker.
    viewport = BoardViewport()
    viewport.setSource(QUrl.fromLocalFile(str(VIEWPORT_QML)))
    camera = ViewportCamera(-55, 40, 0.2, -0.01, 0.02, 0.1, 0.07)
    monkeypatch.setattr(viewport, "capture_camera", lambda *_: camera)
    monkeypatch.setattr(render.QFileDialog, "getExistingDirectory", lambda *_: str(tmp_path))
    released = []

    class Capture(QObject):
        captured = Signal(QImage)
        failed = Signal(str)

        def __init__(self, view, pose, colors, size, *, shadow):
            super().__init__()
            # The renderer receives the selected view, color, dimensions, and shadow.
            assert (view, pose, colors, size, shadow) == (
                viewport,
                camera,
                COLOR_SCHEMES["Blue"],
                (1080, 1440),
                ShadowSettings(100, 100, 100),
            )

        def start(self):
            # Only the GUI thread may capture the viewport.
            assert QThread.currentThread() == app.thread()
            image = QImage(1080, 1440, QImage.Format.Format_RGBA8888_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            with QPainter(image) as painter:
                painter.fillRect(-10, 10, 40, 20, QColor("blue"))
                painter.fillRect(30, 30, 20, 20, QColor(0, 0, 0, 76))
            self.captured.emit(image)

        def release(self):
            released.append(True)

    monkeypatch.setattr(render, "ViewportCapture", Capture)
    ray_tracer = Mock()
    panel = ControlsPanel(lambda: viewport, ray_tracer, Event())
    panel.set_ready(BoardSnapshot("board", tmp_path, "project"))
    engine, palette, background, _, _, aspect_ratio = panel.findChildren(QComboBox)
    controls = panel.render_controls
    try:
        # Start centered, then update the live QML shadow using the sliders.
        light_x, light_y, shadow = panel.findChildren(QSlider)
        assert viewport.shadow == DEFAULT_SHADOW
        scene = viewport.rootObject()
        assert scene.property("shadowOffsetX") == 3
        assert scene.property("shadowOffsetY") == 4
        assert scene.property("shadowOpacity") == pytest.approx(0.1798)
        assert scene.property("shadowBlurFactor") == 1
        for slider in (light_x, light_y, shadow):
            assert slider.value() * 2 == slider.minimum() + slider.maximum()
            slider.setValue(slider.maximum())
        assert scene.property("shadowOffsetX") == -13
        assert scene.property("shadowOffsetY") == 20
        assert scene.property("shadowOpacity") == pytest.approx(0.1798)
        assert scene.property("shadowBlurFactor") == 0

        # Switch engines, export one PNG, and wait for the save worker.
        engine.setCurrentText("Viewport")
        palette.setCurrentText("Blue")
        background.setCurrentText("Transparent")
        aspect_ratio.setCurrentText("3:4")
        controls.button.click()
        background.setCurrentText("Warm Stone")
        shadow.setValue(0)
        assert scene.property("shadowOpacity") == 0
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
            assert image.mode == "RGBA"
            assert image.getpixel((0, 0)) == (0, 0, 0, 0)
            assert image.getpixel((0, 10)) == (0, 0, 255, 255)
            assert image.getpixel((30, 30)) == (0, 0, 0, 76)
    finally:
        panel.shutdown()
        viewport.close()


@pytest.mark.parametrize(("color", "pixel"), [(None, (0, 0, 0, 0)), ("#FFFFFF", (255, 255, 255))])
def test_viewport_exports_background_when_the_board_is_outside_the_crop(tmp_path, color, pixel):
    # Simulate a valid capture with the camera panned entirely away from the board.
    frame = QImage(80, 60, QImage.Format.Format_RGBA8888)
    frame.fill(Qt.GlobalColor.transparent)

    # Preserve the chosen background throughout the exported frame.
    png = save_viewport_render(
        frame,
        BoardSnapshot("board", None, "test"),
        tmp_path,
        Event(),
        (80, 60),
        background=BackgroundSettings(color),
    )
    with Image.open(png) as image:
        assert image.size == (80, 60)
        assert image.getextrema() == tuple((channel, channel) for channel in pixel)
