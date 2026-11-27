# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import shlex
import sys
from unittest.mock import Mock

from PySide6.QtCore import QUrl
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QSlider, QStyle

from kipng.contracts import BoardSnapshot, PreviewError, ViewportCamera
from kipng.contracts.background import DEFAULT_BACKGROUND
from kipng.contracts.colors import COLOR_SCHEMES, DEFAULT_COLOR_SCHEME
from kipng.contracts.render import DEFAULT_OUTPUT_SIZE, DEFAULT_SHADOW, RenderEngine
from kipng.ui import window
from kipng.ui.viewport.pane import VIEWPORT_QML, BoardViewport
from test_window import FakeViewport, wait_for


def test_file_menu_reload_preserves_settings_and_refreshes_snapshot(app, monkeypatch, tmp_path):
    # Fail one reload between two successful exports.
    model = tmp_path / "board.glb"
    first = BoardSnapshot("original board", tmp_path, "board")
    latest = BoardSnapshot("edited board", tmp_path, "board")
    snapshots = iter((first, PreviewError("Could not read the edited board."), latest))

    def export(path, _cancelled):
        # Record the staged output, even on failure, to check model cleanup.
        path.touch()
        result = next(snapshots)
        if isinstance(result, PreviewError):
            raise result
        return result

    warning = Mock()
    monkeypatch.setattr(window, "BoardViewport", FakeViewport)
    monkeypatch.setattr(window.QMessageBox, "warning", warning)
    preview = window.PreviewWindow(model, export, Mock(), log=tmp_path / "kipng.txt")
    preview.show()
    preview.start()
    try:
        # Check menu labels on every platform.
        file_menu = preview.menu_bar.file_menu
        assert preview.menu_bar.actions() == [file_menu.menuAction()]
        actions = [action for action in file_menu.actions() if not action.isSeparator()]
        assert file_menu.title() == "&File"
        assert [action.text() for action in actions] == [
            "&Render",
            "&Copy CLI",
            "Re&load Board",
            "Reset to &Default",
            "&Open Log",
            "E&xit",
        ]

        # Qt disables automatic menu mnemonics by default on macOS.
        if sys.platform != "darwin":
            labels = [file_menu.title(), *(action.text() for action in actions)]
            assert [QKeySequence.mnemonic(label).toString() for label in labels] == [
                "Alt+F",
                "Alt+R",
                "Alt+C",
                "Alt+L",
                "Alt+D",
                "Alt+O",
                "Alt+X",
            ]

        # The File menu is hidden through both loading stages.
        assert preview.menu_bar.isHidden()
        wait_for(lambda: preview.viewer is not None)
        assert preview.menu_bar.isHidden()
        view = preview.viewer

        # The ready window shows the menu with its mnemonic underlines enabled.
        view.ready.emit()
        assert preview.menu_bar.isVisible()
        assert all(action.isEnabled() for action in actions)
        hint = QStyle.StyleHint.SH_UnderlineShortcut
        assert preview.menu_bar.style().styleHint(hint)
        assert file_menu.style().styleHint(hint)
        preview.resize(720, 520)
        preview.controls.findChildren(QComboBox)[1].setCurrentText("Blue")

        # A failed reload returns to the current preview and leaves its model usable.
        preview.menu_bar.reload_action.trigger()
        assert not preview.menu_bar.reload_action.isEnabled()
        assert preview.menu_bar.isHidden()
        assert preview.size() == window.LOADER_SIZE
        assert preview.loading.message.text() == "Preparing board…"
        wait_for(lambda: warning.called)
        assert preview.stack.currentWidget() is preview.workspace
        assert preview.snapshot == first
        assert preview.menu_bar.isVisible()
        assert (preview.width(), preview.height()) == (720, 520)
        assert model.exists()
        assert not (tmp_path / "reload-1.glb").exists()

        # A successful reload reuses the viewport with fresh model data and settings.
        preview.menu_bar.reload_action.trigger()
        assert preview.menu_bar.isHidden()
        assert preview.size() == window.LOADER_SIZE
        wait_for(lambda: view.model != model)
        assert preview.menu_bar.isHidden()
        assert preview.size() == window.LOADER_SIZE
        view.ready.emit()
        assert preview.menu_bar.isVisible()
        assert (preview.width(), preview.height()) == (720, 520)
        assert preview.viewer is view
        assert preview.snapshot == preview.controls.snapshot == latest
        assert view.color_scheme == COLOR_SCHEMES["Blue"]
        assert not model.exists()
        assert view.model.is_file()

        # Exit closes the preview through the existing cancellation path.
        actions[-1].trigger()
        assert preview.isHidden()
        assert preview.cancelled.is_set()
    finally:
        preview.close()
        preview.shutdown()


def test_reset_restores_startup_camera_and_render_controls(app, monkeypatch, tmp_path):
    # Load the real QML without asking the offscreen backend to draw a board.
    def load_scene(self, _model):
        self.setSource(QUrl.fromLocalFile(str(VIEWPORT_QML)))
        self.rootObject().setProperty("boardRadius", 1.0)

    monkeypatch.setattr(BoardViewport, "load_model", load_scene)
    snapshot = BoardSnapshot("board", tmp_path, "board")
    preview = window.PreviewWindow(tmp_path / "board.glb", lambda *_: snapshot, Mock())
    preview.start()
    try:
        # Change every render setting and the camera before choosing Reset.
        wait_for(lambda: preview.viewer is not None)
        view = preview.viewer
        view.ready.emit()
        engine, palette, background, texture, resolution, ratio = preview.controls.findChildren(
            QComboBox
        )
        engine.setCurrentText("Ray Tracing")
        palette.setCurrentText("Blue")
        background.setCurrentText("Custom")
        preview.controls.findChild(QLineEdit).setText("#123456")
        texture.setCurrentText("Fabric Grain")
        resolution.setCurrentText("4K")
        ratio.setCurrentText("1:1")
        for slider in preview.controls.findChildren(QSlider):
            slider.setValue(slider.maximum())
        preview.controls.findChild(QCheckBox).setChecked(True)
        view.set_camera_view(-90, 0)

        # Reset keeps the current board while restoring the visible controls and state.
        preview.menu_bar.reset_action.trigger()
        combos = preview.controls.findChildren(QComboBox)
        assert combos[0].currentText() == "Viewport"
        assert [combo.currentIndex() for combo in combos[1:]] == [0] * (len(combos) - 1)
        assert preview.controls.findChild(QLineEdit).text() == "#E4DDD2"
        assert not preview.controls.findChild(QCheckBox).isChecked()
        for slider in preview.controls.findChildren(QSlider):
            assert slider.value() * 2 == slider.minimum() + slider.maximum()
        assert preview.controls.snapshot == snapshot
        assert view.render_engine is RenderEngine.VIEWPORT
        assert view.color_scheme == COLOR_SCHEMES[DEFAULT_COLOR_SCHEME]
        assert view.background == DEFAULT_BACKGROUND
        assert view.shadow == DEFAULT_SHADOW
        assert view.output_size == DEFAULT_OUTPUT_SIZE
        assert not view.render_frame_visible
        angles = view.rootObject().property("cameraAngles")
        assert (angles.x(), angles.y()) == (-82, -34)
    finally:
        preview.close()
        preview.shutdown()


def test_copy_cli_captures_the_effective_view(app, monkeypatch, tmp_path):
    # Load the renderer controls with a saved PCB whose path needs shell quoting.
    def load_scene(self, _model):
        self.setSource(QUrl.fromLocalFile(str(VIEWPORT_QML)))

    board = tmp_path / "Robin's PCB.kicad_pcb"
    board.touch()
    snapshot = BoardSnapshot("board", tmp_path, board.stem, board_path=board)
    camera = ViewportCamera(-55, 40, 0.2, -0.01, 0.02, 0.1, 0.07, pivot=(0, 0.025, -0.001))
    monkeypatch.setattr(BoardViewport, "load_model", load_scene)
    monkeypatch.setattr(BoardViewport, "capture_camera", lambda *_: camera)
    preview = window.PreviewWindow(tmp_path / "board.glb", lambda *_: snapshot, Mock())
    preview.start()
    try:
        # Choose a styled custom background and type an incomplete replacement.
        wait_for(lambda: preview.viewer is not None)
        preview.viewer.ready.emit()
        _, palette, background, texture, resolution, ratio = preview.controls.findChildren(
            QComboBox
        )
        palette.setCurrentText("Purple")
        background.setCurrentText("Custom")
        hex_color = preview.controls.findChild(QLineEdit)
        hex_color.setText("#123456")
        texture.setCurrentText("Fabric Grain")
        hex_color.setText("#12345")
        resolution.setCurrentText("4K")
        ratio.setCurrentText("16:9")
        for slider, value in zip(preview.controls.findChildren(QSlider), (-10, 25, 70)):
            slider.setValue(value)

        # The clipboard uses the last applied color and the current crop and lighting.
        preview.menu_bar.copy_cli_action.trigger()
        command = app.clipboard().text()
        expected = (
            "--camera=-55,40,0.2,-0.01,0.02,0.1,0.07,0,0.025,-0.001",
            "--engine=viewport",
            "--color-scheme=purple",
            "--background=#123456",
            "--texture=fabric-grain",
            "--resolution=4k",
            "--aspect-ratio=16:9",
            "--light-x=-10",
            "--light-y=25",
            "--shadow=70",
        )
        if sys.platform == "win32":
            assert command.startswith("& ")
            assert command.endswith(" | Write-Output")
            assert "Robin''s PCB.kicad_pcb'" in command
            assert all(f"'{arg}'" in command for arg in expected)
        else:
            args = shlex.split(command)
            assert args[2] == str(board)
            assert tuple(args[3:]) == expected
    finally:
        preview.close()
        preview.shutdown()
