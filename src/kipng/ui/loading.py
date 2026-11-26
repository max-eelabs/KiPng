# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""A full-window loading surface shared by progress and error states."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QFrame, QLabel, QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget

LOADER_SIZE = QSize(360, 160)
PREPARING_BOARD = "Preparing board…"


def resize_centered(window: QWidget, size: QSize) -> None:
    window.resize(size)
    available = window.screen().availableGeometry()
    window.move(available.center() - window.rect().center())


def show_compact(window: QWidget) -> None:
    """Return the window to the compact size even when the preview was maximized."""
    window.setWindowState(Qt.WindowState.WindowNoState)
    window.setMinimumSize(LOADER_SIZE)
    resize_centered(window, LOADER_SIZE)


class LoadingScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("white"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#222222"))
        palette.setColor(QPalette.ColorRole.Base, QColor("white"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#222222"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self.message = QLabel(PREPARING_BOARD)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.progress = QProgressBar()
        self.progress.setAccessibleName("Loading 3D preview")
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(240)

        self.error_details = QPlainTextEdit()
        self.error_details.setReadOnly(True)
        self.error_details.setFrameShape(QFrame.Shape.NoFrame)
        self.error_details.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(12)
        layout.addStretch()
        layout.addWidget(self.message)
        layout.addWidget(self.progress, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        layout.addWidget(self.error_details, 1)

    def show_progress(self) -> None:
        self.message.setText(PREPARING_BOARD)
        self.error_details.hide()
        self.message.show()
        self.progress.show()

    def show_error(self, message: str) -> None:
        self.message.hide()
        self.progress.hide()
        self.error_details.setPlainText(message)
        self.error_details.show()
