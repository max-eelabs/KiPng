# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Save an image from the current viewport camera without blocking the GUI."""

import traceback
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ...contracts import (
    BoardSnapshot,
    ImageRenderer,
    PreviewCancelled,
    PreviewError,
    ViewportCamera,
)
from ...contracts.colors import BoardColors


class RenderControls(QWidget):
    def __init__(self, renderer: ImageRenderer, cancelled: Event) -> None:
        super().__init__()
        self.renderer = renderer
        self.cancelled = cancelled
        self.worker: Thread | None = None
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

    def start(
        self,
        snapshot: BoardSnapshot,
        camera: ViewportCamera,
        color_scheme: BoardColors,
        output_size: tuple[int, int],
    ) -> None:
        if self.worker is not None or self.cancelled.is_set():
            return

        initial_dir = snapshot.project_dir or Path.home()
        destination = QFileDialog.getExistingDirectory(self, "Save rendered PNG", str(initial_dir))
        if not destination or self.cancelled.is_set():
            return

        self.status.hide()
        self.button.setEnabled(False)
        self.button.setText("Rendering…")
        self.worker = Thread(
            target=self.render,
            args=(snapshot, camera, Path(destination), color_scheme, output_size),
            name="board-render",
        )
        self.worker.start()
        self.poll.start()

    def render(
        self,
        snapshot: BoardSnapshot,
        camera: ViewportCamera,
        output_dir: Path,
        color_scheme: BoardColors,
        output_size: tuple[int, int],
    ) -> None:
        try:
            self.results.put(
                self.renderer(
                    snapshot,
                    camera,
                    output_dir,
                    self.cancelled,
                    color_scheme=color_scheme,
                    output_size=output_size,
                )
            )
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

    def shutdown(self) -> None:
        self.poll.stop()
        if self.worker is not None:
            self.worker.join()
            self.worker = None
