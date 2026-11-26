# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assemble the preview and own its temporary model directory."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .export.exporter import export_board_model
from .export.render import render_board_image
from .ui.taskbar import APP_ID, TaskbarIcon
from .ui.window import PreviewWindow


def plugin_asset(name: str) -> Path:
    root = Path(__file__).resolve().parent.parent
    installed = root / name
    if installed.is_file():
        return installed
    return root.parent / "plugin" / name


def create_application() -> QApplication:
    """Set KiPng's Windows taskbar identity and default window icon."""
    if sys.platform == "win32":
        from ctypes import windll

        windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    app = QApplication(sys.argv)
    app.setApplicationName("KiPng")
    # The installed SVG sits beside the manifest, outside the kipng package.
    app.setWindowIcon(QIcon(str(plugin_asset("kipng-logo.svg"))))
    return app


def main() -> int:
    app = create_application()
    with TemporaryDirectory(prefix="kipng-") as directory:
        window = PreviewWindow(
            Path(directory) / "board.glb", export_board_model, render_board_image
        )
        if sys.platform == "win32" and app.platformName() == "windows":
            window.taskbar_icon = TaskbarIcon(window, plugin_asset("kipng-logo.ico"))
        window.show()
        window.start()
        try:
            return app.exec()
        finally:
            # Release the QML scene before the temporary GLB is removed on Windows.
            window.shutdown()
