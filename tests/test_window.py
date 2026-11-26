# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

from threading import Event
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, QPoint, QUrl, Signal
from PySide6.QtGui import QVector3D
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QWidget

from kipng.contracts import BoardSnapshot, PreviewError, ViewportCamera
from kipng.contracts.colors import COLOR_SCHEMES
from kipng.ui import window
from kipng.ui.controls.sections.viewport import CAMERA_PRESETS
from kipng.ui.viewport.pane import VIEWPORT_QML, BoardViewport


class FakeViewport(QWidget):
    ready = Signal()
    failed = Signal(str)

    def load_model(self, model):
        self.model = model

    def fit_board(self):
        self.fitted_size = self.size()

    def set_color_scheme(self, scheme):
        self.color_scheme = scheme

    def release_model(self):
        self.released = True


def wait_for(condition):
    for _ in range(100):
        if condition():
            return
        QTest.qWait(20)
    pytest.fail("The preview did not reach the expected state.")


def test_loading_covers_split_until_viewport_is_ready(app, monkeypatch, tmp_path):
    # Hold the export open so the test can inspect the first loading stage.
    monkeypatch.setattr(window, "BoardViewport", FakeViewport)
    release_export = Event()
    model = tmp_path / "board.glb"

    def export(output, cancelled):
        release_export.wait(2)
        if not cancelled.is_set():
            output.touch()

    preview = window.PreviewWindow(model, export)
    preview.show()
    preview.start()
    try:
        # While the board exports, the compact loader covers both panes.
        assert preview.size() == window.LOADER_SIZE
        assert preview.stack.currentWidget() is preview.loading
        assert preview.loading.geometry() == preview.rect()
        assert preview.childAt(QPoint(preview.width() - 10, 10)) is preview.loading
        assert preview.loading.progress.minimum() == preview.loading.progress.maximum() == 0

        # After export, load the model while keeping the compact loader visible.
        release_export.set()
        wait_for(lambda: preview.viewer is not None)
        assert preview.viewer.model == model
        assert preview.loading.message.text() == "Opening 3D view…"
        assert preview.stack.currentWidget() is preview.loading
        assert preview.size() == window.LOADER_SIZE

        # Fit the board at the expanded size and reveal the viewport presets.
        expanded = preview.expanded_size()
        monkeypatch.setattr(preview.viewer, "set_camera_view", Mock(), raising=False)
        assert not preview.controls.isEnabled()
        preview.viewer.ready.emit()
        assert preview.stack.currentWidget() is preview.workspace
        assert preview.loading.isHidden()
        assert preview.size() == expanded
        assert preview.viewer.fitted_size == preview.viewer.size()
        assert preview.viewer.fitted_size.height() == expanded.height()
        assert preview.size().width() > window.LOADER_SIZE.width()
        assert preview.controls.width() == 240
        assert preview.controls.findChild(QLabel).text() == "Viewport"
        buttons = {button.text(): button for button in preview.controls.findChildren(QPushButton)}
        expected = {
            "Default Front": (-82, -34, True),
            "Default Back": (98, 146, True),
            "Straight Top": (-90, 0, False),
            "Straight Bottom": (90, 180, False),
        }
        for label, angles in expected.items():
            buttons[label].click()
            preview.viewer.set_camera_view.assert_called_with(*angles)
    finally:
        # Unblock the worker even if an assertion fails before export finishes.
        release_export.set()
        preview.close()
        preview.shutdown()

    # Shutdown releases the model and joins the worker.
    assert preview.viewer.released
    assert not preview.worker.is_alive()


def test_export_error_stays_on_loading_screen(app, tmp_path):
    # Simulate a board that KiCad cannot read.
    def export(output, cancelled):
        raise PreviewError("The board could not be read.")

    # Surface the error in the compact loader before creating a viewport.
    preview = window.PreviewWindow(tmp_path / "board.glb", export)
    preview.show()
    preview.start()
    try:
        wait_for(lambda: preview.loading.progress.isHidden())
        assert preview.stack.currentWidget() is preview.loading
        assert preview.size() == window.LOADER_SIZE
        assert preview.loading.error_details.toPlainText() == "The board could not be read."
        assert preview.viewer is None
    finally:
        preview.close()
        preview.shutdown()


def test_render_captures_current_camera_palette_and_snapshot(app, monkeypatch, tmp_path):
    # Provide a preview snapshot and a camera to capture after the model opens.
    snapshot = BoardSnapshot("edited board", tmp_path, "project")
    camera = ViewportCamera(-55, 40, 0.2, -0.01, 0.02, 0.1, 0.07)
    output = tmp_path / "project-render-1080x1920.png"
    renderer = Mock(return_value=output)
    monkeypatch.setattr(window, "BoardViewport", FakeViewport)
    monkeypatch.setattr(FakeViewport, "capture_camera", lambda self: camera, raising=False)
    monkeypatch.setattr(
        "kipng.ui.controls.render.QFileDialog.getExistingDirectory",
        lambda *args: str(tmp_path),
    )
    preview = window.PreviewWindow(tmp_path / "board.glb", lambda *_: snapshot, renderer)
    preview.show()
    preview.start()
    try:
        # Enable the render button only once the preview is ready.
        render = preview.controls.render_controls
        wait_for(lambda: preview.viewer is not None)
        assert not render.button.isEnabled()
        preview.viewer.ready.emit()
        assert render.button.isEnabled()

        # Clicking Render captures the palette even if the next selection changes.
        selector = preview.controls.findChild(QComboBox)
        selector.setCurrentText("White")
        render.button.click()
        selector.setCurrentText("Blue")
        assert not render.button.isEnabled()
        wait_for(render.button.isEnabled)
        renderer.assert_called_once_with(
            snapshot, camera, tmp_path, preview.cancelled, color_scheme=COLOR_SCHEMES["White"]
        )
        assert not render.status.isHidden()
        assert render.status.toolTip() == str(output)
    finally:
        preview.close()
        preview.shutdown()


def test_viewport_error_prevents_a_late_ready_signal(app, monkeypatch, tmp_path):
    # Load a fake viewport and provide enough error detail to require scrolling.
    monkeypatch.setattr(window, "BoardViewport", FakeViewport)
    model = tmp_path / "board.glb"
    details = "The viewport could not load the model.\n" + "Diagnostic details.\n" * 40
    preview = window.PreviewWindow(model, lambda output, cancelled: None)
    try:
        # Emit the load error, then simulate a readiness signal that arrives too late.
        preview.load_model(model)
        preview.viewer.failed.emit(details)
        preview.viewer.ready.emit()

        # Keep the compact loader open with the full diagnostic and progress stopped.
        assert preview.stack.currentWidget() is preview.loading
        assert preview.loading.progress.isHidden()
        assert preview.size() == window.LOADER_SIZE
        assert preview.loading.error_details.toPlainText() == details
        assert preview.loading.error_details.verticalScrollBar().maximum() > 0
    finally:
        preview.close()
        preview.shutdown()


def test_qml_viewport_loads_without_a_gpu(app):
    # Instantiate the scene without asking the Qt renderer to draw a model.
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(VIEWPORT_QML)))
    root = component.create()

    # The empty viewport starts white and has no framed board.
    assert root is not None, [error.toString() for error in component.errors()]
    assert root.property("color").name() == "#ffffff"
    assert not root.property("framed")


def test_viewport_orbit_passes_both_poles(app):
    # Load the QML controls without a board or a graphics context.
    view = BoardViewport()
    view.load_model(VIEWPORT_QML.parent / "unused.glb")
    try:
        root = view.rootObject()
        controls = root.findChild(QObject, "orbitControls")

        # Default Front turns a wide board without waiting for user input.
        assert view.capture_camera().yaw == -34
        root.setProperty("boardExtent", QVector3D(2, 0, 1))
        assert view.capture_camera().yaw == 56

        # Drag past the top-down pole and keep the camera angle past the old limit.
        controls.orbit(0, 200)
        assert view.capture_camera().pitch == pytest.approx(208)

        # Continue to the underside and then complete a full orbit.
        controls.orbit(0, 414.2857142857)
        assert view.capture_camera().pitch == pytest.approx(63)
        controls.orbit(0, 414.2857142857)
        assert view.capture_camera().pitch == pytest.approx(278)

        # Rotate only the angled presets when the board's long axis changes.
        for extent, turn in ((QVector3D(1, 0, 2), 0), (QVector3D(2, 0, 1), 90)):
            view.rootObject().setProperty("boardExtent", extent)
            for _, pitch, yaw, align in CAMERA_PRESETS:
                view.set_camera_view(pitch, yaw, align)
                camera = view.capture_camera()
                assert (camera.pitch, camera.yaw) == (pitch, yaw + (turn if align else 0))
    finally:
        view.release_model()
        view.close()
