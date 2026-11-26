# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Qt widget that translates QML readiness and failures into Python signals."""

from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtQuickWidgets import QQuickWidget

from ..contracts import ViewportCamera

VIEWPORT_QML = Path(__file__).parent / "qml" / "Viewport.qml"


class BoardViewport(QQuickWidget):
    ready = Signal()
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setClearColor(QColor("white"))
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.sceneGraphError.connect(self.show_graphics_error)

    def show_graphics_error(self, _error, message: str) -> None:
        self.failed.emit(f"Could not start the 3D viewport.\n\n{message}")

    def load_model(self, model: Path, framing_aspect: float) -> None:
        self.setSource(QUrl.fromLocalFile(str(VIEWPORT_QML)))
        scene = self.rootObject()
        if scene is None:
            errors = "\n".join(error.description() for error in self.errors())
            self.failed.emit(f"Could not load the 3D viewport.\n\n{errors}")
            return

        # Defer switching pages while Qt handles the camera and bounds update.
        scene.framedChanged.connect(lambda: QTimer.singleShot(0, self.ready.emit))
        scene.loadFailed.connect(self.failed)
        scene.setProperty("framingAspect", framing_aspect)
        scene.setProperty("modelSource", QUrl.fromLocalFile(str(model)))

    def release_model(self) -> None:
        self.setSource(QUrl())

    def capture_camera(self) -> ViewportCamera:
        """Read the framed camera on the GUI thread."""
        scene = self.rootObject()
        angles = scene.property("cameraAngles")
        pan = scene.property("cameraPan")
        return ViewportCamera(
            pitch=angles.x(),
            yaw=angles.y(),
            distance=scene.property("cameraDistance"),
            pan_x=pan.x(),
            pan_y=pan.y(),
            board_span=scene.property("boardSpan"),
            frame_half_width=scene.property("frameHalfWidth"),
        )
