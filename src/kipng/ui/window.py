# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Preview window and the transition from export to an interactive viewport."""

import traceback
from contextlib import suppress
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from PySide6.QtCore import QByteArray, QSize, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMessageBox, QStackedLayout, QWidget

from ..contracts import BoardSnapshot, ImageRenderer, ModelExporter, PreviewCancelled, PreviewError
from .controls.panel import ControlsPanel
from .file_menu import FileMenuBar
from .loading import LOADER_SIZE, LoadingScreen, resize_centered, show_compact
from .viewport.pane import BoardViewport

VIEWPORT_TIMEOUT_MS = 30_000
PREVIEW_MINIMUM_SIZE = QSize(560, 300)


class PreviewWindow(QWidget):
    def __init__(
        self, model: Path, exporter: ModelExporter, renderer: ImageRenderer | None = None
    ) -> None:
        super().__init__()
        self.setWindowTitle("KiPng - 3D Preview")
        self.setMinimumSize(LOADER_SIZE)

        self.workspace = QWidget()
        self.split = QHBoxLayout(self.workspace)
        self.split.setContentsMargins(0, 0, 0, 0)
        self.split.setSpacing(0)
        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.VLine)
        self.cancelled = Event()
        self.viewer: BoardViewport | None = None
        self.renderer = renderer
        self.controls = self.create_controls()
        self.split.addStretch(1)
        self.split.addWidget(self.separator)
        self.split.addWidget(self.controls)

        # Let Qt initialize the viewport behind the loader without exposing the split.
        self.loading = LoadingScreen()
        self.stack = QStackedLayout(self)
        self.stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.menu_bar = FileMenuBar(
            self,
            lambda: self.controls.start_render(),
            self.reload_board,
            self.reset_settings,
            self.close,
        )
        self.stack.setMenuBar(self.menu_bar)
        self.menu_bar.hide()
        self.stack.addWidget(self.workspace)
        self.stack.addWidget(self.loading)
        self.stack.setCurrentWidget(self.loading)
        resize_centered(self, LOADER_SIZE)

        self.model = model
        self.exporter = exporter
        self.snapshot: BoardSnapshot | None = None
        self.board_ready = False
        self.workspace_geometry: QByteArray | None = None
        self.pending_model = model
        self.reload_count = 0
        self.results: Queue[BoardSnapshot | str | None] = Queue()
        self.worker: Thread | None = None
        self.poll = QTimer(self, interval=50)
        self.poll.timeout.connect(self.show_result)
        self.viewport_timeout = QTimer(self, singleShot=True, interval=VIEWPORT_TIMEOUT_MS)
        self.viewport_timeout.timeout.connect(self.show_viewport_timeout)
        self.update_menu()

    def create_controls(self) -> ControlsPanel:
        controls = ControlsPanel(lambda: self.viewer, self.renderer, self.cancelled)
        if controls.render_controls is not None:
            controls.render_controls.busy_changed.connect(self.update_menu)
        return controls

    def update_menu(self) -> None:
        render = self.controls.render_controls
        rendering = render is not None and render.busy
        loading = self.poll.isActive() or self.viewport_timeout.isActive()
        ready = self.board_ready and not loading and not rendering and not self.cancelled.is_set()
        self.menu_bar.set_availability(ready, render is not None and self.snapshot is not None)

    def start(self) -> None:
        self.start_export(self.model)

    def start_export(self, model: Path) -> None:
        self.pending_model = model
        self.controls.setEnabled(False)
        self.menu_bar.hide()
        show_compact(self)
        self.loading.show_progress()
        self.stack.setCurrentWidget(self.loading)
        self.loading.show()
        self.worker = Thread(target=self.prepare_model, args=(model,), name="board-preview")
        self.poll.start()
        self.update_menu()
        self.worker.start()

    def reload_board(self) -> None:
        if not self.menu_bar.reload_action.isEnabled():
            return

        # Keep the current geometry and GLB until the replacement export succeeds.
        self.workspace_geometry = self.saveGeometry()
        self.reload_count += 1
        replacement = self.model.with_name(f"reload-{self.reload_count}.glb")
        self.start_export(replacement)

    def reset_settings(self) -> None:
        if self.viewer is None or not self.menu_bar.reset_action.isEnabled():
            return

        self.viewer.reset_settings()
        previous = self.controls
        self.controls = self.create_controls()
        self.split.replaceWidget(previous, self.controls)
        previous.hide()
        previous.deleteLater()
        self.controls.set_ready(self.snapshot)

    def prepare_model(self, model: Path) -> None:
        # The worker only deals with files and IPC. Widgets are updated on the Qt thread.
        try:
            snapshot = self.exporter(model, self.cancelled)
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
        if self.worker is not None:
            self.worker.join()
        if isinstance(result, str):
            if self.pending_model != self.model:
                self.discard_model(self.pending_model)
            if self.board_ready:
                self.reveal_workspace()
                QMessageBox.warning(self, "Reload failed", result)
            else:
                self.show_error(result)
            return
        self.snapshot = result
        previous_model = self.model
        self.model = self.pending_model
        self.load_model(self.model)
        if previous_model != self.model:
            self.discard_model(previous_model)

    @staticmethod
    def discard_model(model: Path) -> None:
        # The application's temporary directory will retry cleanup at shutdown.
        with suppress(OSError):
            model.unlink(missing_ok=True)

    def load_model(self, model: Path) -> None:
        self.loading.message.setText("Opening 3D view…")
        self.board_ready = False
        if self.viewer is None:
            self.viewer = BoardViewport()
            self.viewer.ready.connect(self.show_workspace)
            self.viewer.failed.connect(self.show_error)
            self.split.takeAt(0)
            self.split.insertWidget(0, self.viewer, 1)
        else:
            self.viewer.release_model()
        self.viewport_timeout.start()
        self.update_menu()
        self.viewer.load_model(model)

    def show_workspace(self) -> None:
        if self.viewer is None or not self.viewport_timeout.isActive() or self.cancelled.is_set():
            return
        self.viewport_timeout.stop()
        self.board_ready = True
        self.reveal_workspace()
        # Refit after the compact loader has given way to the full viewport geometry.
        self.stack.activate()
        self.split.activate()
        self.viewer.fit_board()

    def reveal_workspace(self) -> None:
        self.setMinimumSize(PREVIEW_MINIMUM_SIZE)
        if self.workspace_geometry is None:
            resize_centered(self, self.expanded_size())
        else:
            self.restoreGeometry(self.workspace_geometry)
            self.workspace_geometry = None
        self.menu_bar.show()
        self.stack.setCurrentWidget(self.workspace)
        self.loading.hide()
        self.controls.set_ready(self.snapshot)
        self.update_menu()

    def expanded_size(self) -> QSize:
        screen = self.screen().availableGeometry()
        size = QSize(min(1120, int(screen.width() * 0.9)), min(650, int(screen.height() * 0.85)))
        return size.expandedTo(PREVIEW_MINIMUM_SIZE)

    def show_error(self, message: str) -> None:
        self.viewport_timeout.stop()
        self.controls.setEnabled(False)
        self.loading.show_error(message)
        self.loading.show()
        self.stack.setCurrentWidget(self.loading)
        self.board_ready = False
        self.menu_bar.hide()
        self.update_menu()

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
        if self.worker is not None:
            self.worker.join()
        self.controls.shutdown()
        if self.viewer is not None:
            self.viewer.release_model()
