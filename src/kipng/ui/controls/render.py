# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Save an image from the current viewport camera without blocking the GUI."""

import traceback
from collections.abc import Callable
from functools import partial
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ...contracts import BoardSnapshot, ImageRenderer, PreviewCancelled, PreviewError
from ...contracts.render import RenderEngine
from ..viewport.pane import BoardViewport
from ..viewport.render import ViewportCapture, save_viewport_render


class RenderControls(QWidget):
    def __init__(self, renderer: ImageRenderer, cancelled: Event) -> None:
        super().__init__()
        self.renderer = renderer
        self.cancelled = cancelled
        self.worker: Thread | None = None
        self.capture: ViewportCapture | None = None
        self.results: Queue[Path | str] = Queue()
        self.poll = QTimer(self, interval=50)
        self.poll.timeout.connect(self.show_result)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.hide()
        self.button = QPushButton("Render")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.status)
        layout.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignRight)

    def start(self, snapshot: BoardSnapshot, view: BoardViewport) -> None:
        if self.worker is not None or self.capture is not None or self.cancelled.is_set():
            return

        camera = view.capture_camera()
        color_scheme = view.color_scheme
        output_size = view.output_size
        engine = view.render_engine
        initial_dir = snapshot.project_dir or Path.home()
        destination = QFileDialog.getExistingDirectory(self, "Save rendered PNG", str(initial_dir))
        if not destination or self.cancelled.is_set():
            return
        if engine is RenderEngine.VIEWPORT and min(camera.distance, camera.frame_half_width) <= 0:
            QMessageBox.warning(
                self,
                "Render failed",
                "The board is behind the camera. Pan back to the board and zoom out.",
            )
            return

        self.status.hide()
        self.button.setEnabled(False)
        self.button.setText("Rendering…")
        output_dir = Path(destination)
        if engine is RenderEngine.VIEWPORT:
            self.capture = ViewportCapture(view, camera, color_scheme, output_size)
            self.capture.captured.connect(
                lambda frame: self.save_capture(frame, snapshot, output_dir, output_size),
                Qt.ConnectionType.QueuedConnection,
            )
            self.capture.failed.connect(self.capture_failed, Qt.ConnectionType.QueuedConnection)
            self.capture.start()
            return

        self.start_worker(
            partial(
                self.renderer,
                snapshot,
                camera,
                output_dir,
                self.cancelled,
                color_scheme=color_scheme,
                output_size=output_size,
            )
        )

    def start_worker(self, render: Callable[[], Path]) -> None:
        self.worker = Thread(target=self.render, args=(render,), name="board-render")
        self.worker.start()
        self.poll.start()

    def save_capture(
        self,
        frame: QImage,
        snapshot: BoardSnapshot,
        output_dir: Path,
        output_size: tuple[int, int],
    ) -> None:
        self.release_capture()
        if not self.cancelled.is_set():
            self.start_worker(
                partial(
                    save_viewport_render, frame, snapshot, output_dir, self.cancelled, output_size
                )
            )

    def capture_failed(self, message: str) -> None:
        if self.capture is not None and not self.cancelled.is_set():
            self.results.put(message)
            self.show_result()

    def render(self, render: Callable[[], Path]) -> None:
        try:
            self.results.put(render())
        except PreviewCancelled:
            pass
        except PreviewError as error:
            self.results.put(str(error))
        except Exception:
            traceback.print_exc()
            self.results.put(
                "An unexpected rendering error occurred. Check the KiCad plugin output."
            )

    def show_result(self) -> None:
        try:
            result = self.results.get_nowait()
        except Empty:
            return
        self.shutdown()
        self.button.setText("Render")
        self.button.setEnabled(True)
        if isinstance(result, str):
            QMessageBox.warning(self, "Render failed", result)
            return

        self.status.setText("Saved PNG.")
        self.status.setToolTip(str(result))
        self.status.show()

    def release_capture(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def shutdown(self) -> None:
        self.poll.stop()
        self.release_capture()
        if self.worker is not None:
            self.worker.join()
            self.worker = None
