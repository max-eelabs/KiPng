# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assemble the preview and own its temporary model directory."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication

from .export.exporter import export_board_model
from .export.render import render_board_image
from .ui.window import PreviewWindow


def main() -> int:
    app = QApplication(sys.argv)
    with TemporaryDirectory(prefix="kipng-") as directory:
        window = PreviewWindow(
            Path(directory) / "board.glb", export_board_model, render_board_image
        )
        window.show()
        window.start()
        try:
            return app.exec()
        finally:
            # Release the QML scene before the temporary GLB is removed on Windows.
            window.shutdown()
