# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Qt widget that translates QML readiness and failures into Python signals."""

from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QVector2D
from PySide6.QtQuick3D import QQuick3DObject
from PySide6.QtQuickWidgets import QQuickWidget

from ...contracts import BOARD_MATERIAL_TAGS, ViewportCamera
from ...contracts.background import DEFAULT_BACKGROUND, WHITE, BackgroundSettings, BackgroundTexture
from ...contracts.colors import COLOR_SCHEMES, DEFAULT_COLOR_SCHEME, BoardColors
from ...contracts.render import DEFAULT_OUTPUT_SIZE, RenderEngine
from .background import BackgroundImageProvider
from .colors import layer_colors

VIEWPORT_QML = Path(__file__).parent / "qml" / "Viewport.qml"
FEATURES_DIR = VIEWPORT_QML.with_name("features")
# The front pose assumes the board lies lengthwise along Z.
FRONT_PITCH = -82
FRONT_YAW = -34


class BoardViewport(QQuickWidget):
    ready = Signal()
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setClearColor(QColor("white"))
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.engine().addImageProvider("backdrop", BackgroundImageProvider())
        self.sceneGraphError.connect(self.show_graphics_error)
        self.board_materials: list[tuple[QQuick3DObject, str]] = []
        self.color_scheme = COLOR_SCHEMES[DEFAULT_COLOR_SCHEME]
        self.background = DEFAULT_BACKGROUND
        self.output_size = DEFAULT_OUTPUT_SIZE
        self.render_engine = RenderEngine.RAY_TRACING
        self.render_frame_visible = False

    def show_graphics_error(self, _error, message: str) -> None:
        self.failed.emit(f"Could not start the 3D viewport.\n\n{message}")

    def load_model(self, model: Path, *, capture: bool = False) -> None:
        self.board_materials.clear()
        self.setSource(QUrl.fromLocalFile(str(VIEWPORT_QML)))
        scene = self.rootObject()
        if scene is None:
            errors = "\n".join(error.description() for error in self.errors())
            self.failed.emit(f"Could not load the 3D viewport.\n\n{errors}")
            return

        # Defer switching pages while Qt handles the camera and bounds update.
        scene.framedChanged.connect(lambda: QTimer.singleShot(0, self.ready.emit))
        scene.loadFailed.connect(self.failed)
        scene.setProperty("defaultAngles", QVector2D(FRONT_PITCH, FRONT_YAW))
        self.set_output_size(self.output_size)
        self.show_render_frame(self.render_frame_visible)
        scene.setProperty("captureMode", capture)
        self.set_background(self.background)
        if not capture:
            sources = [QUrl.fromLocalFile(str(path)) for path in sorted(FEATURES_DIR.glob("*.qml"))]
            scene.setProperty("featureSources", sources)
        scene.setProperty("modelSource", QUrl.fromLocalFile(str(model)))

        layers_by_tag = {tag: layer for layer, tag in BOARD_MATERIAL_TAGS.items()}
        for material in scene.findChildren(QQuick3DObject):
            layer = layers_by_tag.get(material.property("alphaCutoff"))
            if layer is not None:
                self.board_materials.append((material, layer))
        self.set_color_scheme(self.color_scheme)

    def release_model(self) -> None:
        self.board_materials.clear()
        self.setSource(QUrl())

    def set_color_scheme(self, scheme: BoardColors) -> None:
        """Apply a palette to the loaded board."""
        self.color_scheme = scheme
        colors = layer_colors(scheme)
        for material, layer in self.board_materials:
            material.setProperty("baseColor", colors[layer])

    def fit_board(self) -> None:
        """Center and fit the board using the viewport's current size."""
        self.rootObject().fitBoard()

    def set_background(self, background: BackgroundSettings) -> None:
        """Update the live backdrop while retaining settings before a scene is loaded."""
        self.background = background
        scene = self.rootObject()
        if scene is None:
            return

        pattern = QUrl()
        texture = background.effective_texture
        if background.color is None:
            pattern = QUrl("image://backdrop/checker")
        elif texture is not BackgroundTexture.NONE:
            pattern = QUrl(f"image://backdrop/{texture.value}/{background.color[1:]}")
        scene.setProperty("backgroundColor", QColor(background.color or WHITE))
        scene.setProperty("backgroundPattern", pattern)
        scene.setProperty("backgroundTextured", texture is not BackgroundTexture.NONE)

    def set_output_size(self, size: tuple[int, int]) -> None:
        """Update the output dimensions and the viewport guide's aspect ratio."""
        self.output_size = size
        scene = self.rootObject()
        if scene is not None:
            scene.setProperty("renderAspectRatio", size[0] / size[1])

    def show_render_frame(self, visible: bool) -> None:
        self.render_frame_visible = visible
        scene = self.rootObject()
        if scene is not None:
            scene.setProperty("renderFrameVisible", visible)

    def set_camera_view(self, pitch: float, yaw: float, align_long_axis: bool = False) -> None:
        """Apply the view angles and refit the board to the current viewport."""
        self.rootObject().setCameraView(pitch, yaw, align_long_axis)

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
