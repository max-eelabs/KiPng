# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render one PNG using the Qt Quick 3D viewport scene."""

from math import ceil
from pathlib import Path
from threading import Event

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QScreen

from ...contracts import BoardSnapshot, PreviewCancelled, PreviewError, ViewportCamera
from ...contracts.background import DEFAULT_BACKGROUND, BackgroundSettings
from ...contracts.colors import BoardColors
from ...contracts.render import DEFAULT_SHADOW, ShadowSettings
from ...export.render_image import save_image
from .pane import BoardViewport

CAPTURE_TIMEOUT_MS = 30_000


class RenderSurface(BoardViewport):
    """Load a model into a hidden Qt Quick 3D surface on the GUI thread."""

    loaded = Signal()

    def __init__(
        self,
        model: Path,
        color_scheme: BoardColors,
        output_size: tuple[int, int],
        *,
        shadow: ShadowSettings = DEFAULT_SHADOW,
        screen: QScreen | None = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.set_color_scheme(color_scheme)
        self.set_output_size(output_size)
        self.set_shadow(shadow)
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        surface_format = self.format()
        surface_format.setAlphaBufferSize(8)
        self.setFormat(surface_format)
        self.setClearColor(QColor("transparent"))
        if screen is not None:
            self.setScreen(screen)
        scale = self.devicePixelRatioF()
        self.resize(*(ceil(pixels / scale) for pixels in output_size))
        self.timeout = QTimer(self, singleShot=True, interval=CAPTURE_TIMEOUT_MS)
        self.failure: str | None = None
        self.timeout.timeout.connect(self.capture_timeout)
        self.ready.connect(self.model_ready)
        self.failed.connect(self.record_failure)

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

    def model_ready(self) -> None:
        if self.timeout.isActive():
            self.timeout.stop()
            self.loaded.emit()

    def capture_timeout(self) -> None:
        self.failed.emit("The viewport renderer timed out while loading the 3D model.")

    def record_failure(self, message: str) -> None:
        self.failure = message
        self.timeout.stop()

    def release(self) -> None:
        self.timeout.stop()
        self.release_model()
        self.close()
        self.deleteLater()

    def grab_render(self, camera: ViewportCamera | None) -> QImage:
        """Render the requested crop or use the camera already fitted to the model."""
        if camera is not None:
            self.rootObject().setRenderCamera(
                camera.pitch,
                camera.yaw,
                camera.distance,
                camera.pan_x,
                camera.pan_y,
                camera.frame_half_width,
            )
        frame = self.grabFramebuffer()
        if self.failure is not None:
            raise PreviewError(self.failure)
        if frame.isNull():
            raise PreviewError("The viewport renderer could not capture a frame.")
        return frame


class ViewportCapture(RenderSurface):
    """Capture one PNG frame asynchronously for the preview controls."""

    captured = Signal(QImage)

    def __init__(
        self,
        source: BoardViewport,
        camera: ViewportCamera,
        color_scheme: BoardColors,
        output_size: tuple[int, int],
        *,
        shadow: ShadowSettings = DEFAULT_SHADOW,
    ) -> None:
        model = Path(source.rootObject().property("modelSource").toLocalFile())
        super().__init__(model, color_scheme, output_size, shadow=shadow, screen=source.screen())
        self.camera = camera
        self.loaded.connect(self.capture_frame)

    def capture_frame(self) -> None:
        try:
            frame = self.grab_render(self.camera)
        except PreviewError as error:
            if self.failure is None:
                self.failed.emit(str(error))
        else:
            self.captured.emit(frame)


def save_viewport_render(
    frame: QImage,
    snapshot: BoardSnapshot,
    output_dir: Path,
    cancelled: Event,
    output_size: tuple[int, int],
    *,
    background: BackgroundSettings = DEFAULT_BACKGROUND,
) -> Path:
    """Encode the captured frame on a worker after releasing the render surface."""
    if cancelled.is_set():
        raise PreviewCancelled

    if not frame.hasAlphaChannel():
        raise PreviewError("The viewport renderer could not capture transparency.")
    # Pillow composites straight alpha. Qt's framebuffer may be premultiplied.
    frame = frame.convertToFormat(QImage.Format.Format_RGBA8888)
    image = Image.frombytes(
        "RGBA",
        (frame.width(), frame.height()),
        frame.constBits(),
        "raw",
        "RGBA",
        frame.bytesPerLine(),
    )

    name = Path(snapshot.project_name).name or "board"
    try:
        return save_image(image, output_dir, name, cancelled, output_size, background=background)
    except OSError as error:
        raise PreviewError(f"Could not save the rendered PNG.\n\n{error}") from error
