# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Preview window and the transition from export to an interactive viewport."""

import traceback
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QStackedLayout, QWidget

from ..contracts import BoardSnapshot, ImageRenderer, ModelExporter, PreviewCancelled, PreviewError
from .controls.panel import ControlsPanel
from .loading import LoadingScreen
from .viewport.pane import BoardViewport

VIEWPORT_TIMEOUT_MS = 30_000
LOADER_SIZE = QSize(360, 160)
PREVIEW_MINIMUM_SIZE = QSize(560, 300)


class PreviewWindow(QWidget):
    def __init__(
        self, model: Path, exporter: ModelExporter, renderer: ImageRenderer | None = None
    ) -> None:
        super().__init__()
        self.setWindowTitle("KiPng — 3D Preview")
        self.setMinimumSize(LOADER_SIZE)

        self.workspace = QWidget()
        self.split = QHBoxLayout(self.workspace)
        self.split.setContentsMargins(0, 0, 0, 0)
        self.split.setSpacing(0)
        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.VLine)
        self.cancelled = Event()
        self.viewer: BoardViewport | None = None
        self.controls = ControlsPanel(lambda: self.viewer, renderer, self.cancelled)
        self.split.addStretch(1)
        self.split.addWidget(self.separator)
        self.split.addWidget(self.controls)

        # Let Qt initialize the viewport behind the loader without exposing the split.
        self.loading = LoadingScreen()
        self.stack = QStackedLayout(self)
        self.stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.stack.addWidget(self.workspace)
        self.stack.addWidget(self.loading)
        self.stack.setCurrentWidget(self.loading)
        self.resize_centered(LOADER_SIZE)

        self.model = model
        self.exporter = exporter
        self.snapshot: BoardSnapshot | None = None
        self.results: Queue[BoardSnapshot | str | None] = Queue()
        self.worker = Thread(target=self.prepare_model, name="board-preview")
        self.poll = QTimer(self, interval=50)
        self.poll.timeout.connect(self.show_result)
        self.viewport_timeout = QTimer(self, singleShot=True, interval=VIEWPORT_TIMEOUT_MS)
        self.viewport_timeout.timeout.connect(self.show_viewport_timeout)

    def start(self) -> None:
        self.worker.start()
        self.poll.start()

    def prepare_model(self) -> None:
        # The worker only deals with files and IPC. Widgets are updated on the Qt thread.
        try:
            snapshot = self.exporter(self.model, self.cancelled)
            if not self.cancelled.is_set():
                self.results.put(snapshot)
        except PreviewCancelled:
            pass
        except PreviewError as error:
            self.results.put(str(error))
        except Exception:
            traceback.print_exc()
            self.results.put("An unexpected preview error occurred. Check the KiCad plugin output.")

    def show_result(self) -> None:
        try:
            result = self.results.get_nowait()
        except Empty:
            return
        self.poll.stop()
        if isinstance(result, str):
            self.show_error(result)
            return
        self.snapshot = result
        self.load_model(self.model)

    def load_model(self, model: Path) -> None:
        self.loading.message.setText("Opening 3D view…")
        self.viewer = BoardViewport()
        self.viewer.ready.connect(self.show_workspace)
        self.viewer.failed.connect(self.show_error)
        self.split.takeAt(0)
        self.split.insertWidget(0, self.viewer, 1)
        self.viewport_timeout.start()
        self.viewer.load_model(model)

    def show_workspace(self) -> None:
        if self.viewer is None or not self.viewport_timeout.isActive() or self.cancelled.is_set():
            return
        self.viewport_timeout.stop()
        self.setMinimumSize(PREVIEW_MINIMUM_SIZE)
        self.resize_centered(self.expanded_size())
        # Refit after the compact loader has given way to the full viewport geometry.
        self.split.activate()
        self.viewer.fit_board()
        self.stack.setCurrentWidget(self.workspace)
        self.loading.hide()
        self.controls.set_ready(self.snapshot)

    def expanded_size(self) -> QSize:
        screen = self.screen().availableGeometry()
        size = QSize(min(1120, int(screen.width() * 0.9)), min(650, int(screen.height() * 0.85)))
        return size.expandedTo(PREVIEW_MINIMUM_SIZE)

    def resize_centered(self, size: QSize) -> None:
        self.resize(size)
        available = self.screen().availableGeometry()
        self.move(available.center() - self.rect().center())

    def show_error(self, message: str) -> None:
        self.viewport_timeout.stop()
        self.controls.setEnabled(False)
        self.loading.show_error(message)
        self.loading.show()
        self.stack.setCurrentWidget(self.loading)

    def show_viewport_timeout(self) -> None:
        self.show_error(
            "The 3D view did not become ready. Close this window and reopen 3D Preview."
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self.cancelled.set()
        self.poll.stop()
        self.viewport_timeout.stop()
        self.controls.stop_polling()
        super().closeEvent(event)

    def shutdown(self) -> None:
        self.cancelled.set()
        if self.worker.ident is not None:
            self.worker.join()
        self.controls.shutdown()
        if self.viewer is not None:
            self.viewer.release_model()
