# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render one PNG using the Qt Quick 3D viewport scene."""

from math import ceil
from pathlib import Path
from threading import Event

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage

from ...contracts import BoardSnapshot, PreviewCancelled, PreviewError, ViewportCamera
from ...contracts.colors import BoardColors
from ...export.render_image import save_image
from .pane import BoardViewport

CAPTURE_TIMEOUT_MS = 30_000


class ViewportCapture(BoardViewport):
    """Own a hidden render surface on the GUI thread until a frame is ready."""

    captured = Signal(QImage)

    def __init__(
        self,
        source: BoardViewport,
        camera: ViewportCamera,
        color_scheme: BoardColors,
        output_size: tuple[int, int],
    ) -> None:
        super().__init__()
        self.model = Path(source.rootObject().property("modelSource").toLocalFile())
        self.camera = camera
        self.set_color_scheme(color_scheme)
        self.set_output_size(output_size)
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        self.setScreen(source.screen())
        scale = self.devicePixelRatioF()
        self.resize(*(ceil(pixels / scale) for pixels in output_size))
        self.timeout = QTimer(self, singleShot=True, interval=CAPTURE_TIMEOUT_MS)
        self.timeout.timeout.connect(self.capture_timeout)
        self.ready.connect(self.grab_render)
        self.failed.connect(self.timeout.stop)

    def start(self) -> None:
        self.timeout.start()
        self.show()
        if self.timeout.isActive():
            self.load_model(self.model, capture=True)
            QTimer.singleShot(0, self.initialize_scene)

    def initialize_scene(self) -> None:
        # A hidden widget may need an explicit frame before Qt resolves the model bounds.
        if self.timeout.isActive():
            self.grabFramebuffer()

    def grab_render(self) -> None:
        if not self.timeout.isActive():
            return

        camera = self.camera
        self.rootObject().setRenderCamera(
            camera.pitch,
            camera.yaw,
            camera.distance,
            camera.pan_x,
            camera.pan_y,
            camera.frame_half_width,
        )
        frame = self.grabFramebuffer()
        if not self.timeout.isActive():
            return
        self.timeout.stop()
        if frame.isNull():
            self.failed.emit("The viewport renderer could not capture a frame.")
            return
        self.captured.emit(frame)

    def capture_timeout(self) -> None:
        self.failed.emit("The viewport renderer timed out while loading the 3D model.")

    def release(self) -> None:
        self.timeout.stop()
        self.release_model()
        self.close()
        self.deleteLater()


def save_viewport_render(
    frame: QImage,
    snapshot: BoardSnapshot,
    output_dir: Path,
    cancelled: Event,
    output_size: tuple[int, int],
) -> Path:
    """Encode the captured frame on a worker after releasing the render surface."""
    if cancelled.is_set():
        raise PreviewCancelled

    frame = frame.convertToFormat(QImage.Format.Format_RGB888)
    image = Image.frombytes(
        "RGB",
        (frame.width(), frame.height()),
        frame.constBits(),
        "raw",
        "RGB",
        frame.bytesPerLine(),
    )
    if image.getextrema() == ((255, 255),) * 3:
        raise PreviewError("No board is visible in the render frame. Check the viewport framing.")

    name = Path(snapshot.project_name).name or "board"
    try:
        return save_image(image, output_dir, name, cancelled, output_size)
    except OSError as error:
        raise PreviewError(f"Could not save the rendered PNG.\n\n{error}") from error
