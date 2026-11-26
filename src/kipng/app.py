# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assemble the preview and own its temporary model directory."""

import logging
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .diagnostics import configure_logging
from .export.exporter import export_board_model
from .export.render import render_board_image
from .ui.taskbar import APP_ID, TaskbarIcon
from .ui.window import PreviewWindow

LOGGER = logging.getLogger(__name__)


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
    with configure_logging() as log:
        LOGGER.info("Starting 3D Preview.")
        try:
            result = run_preview(log)
        except Exception:
            LOGGER.exception("3D Preview stopped unexpectedly.")
            message = f" See {log}." if log is not None else ""
            print(f"KiPng: 3D Preview stopped unexpectedly.{message}", file=sys.stderr)
            return 1
        LOGGER.info("3D Preview closed with exit code %d.", result)
        return result


def run_preview(log: Path | None) -> int:
    app = create_application()
    with TemporaryDirectory(prefix="kipng-") as directory:
        window = PreviewWindow(
            Path(directory) / "board.glb", export_board_model, render_board_image, log=log
        )
        if sys.platform == "win32" and app.platformName() == "windows":
            window.taskbar_icon = TaskbarIcon(window, plugin_asset("kipng-logo.ico"))
        try:
            window.show()
            window.start()
            return app.exec()
        finally:
            # Release the QML scene before the temporary GLB is removed on Windows.
            window.shutdown()
