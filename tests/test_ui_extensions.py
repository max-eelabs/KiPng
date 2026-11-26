# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

from threading import Event

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QPushButton

from kipng.ui.controls import sections
from kipng.ui.controls.panel import ControlsPanel
from kipng.ui.viewport import pane


def test_controls_panel_discovers_new_section(app, monkeypatch, tmp_path):
    # Add a section module without changing the panel or its package initializer.
    (tmp_path / "test_section.py").write_text(
        "from PySide6.QtWidgets import QLabel\n"
        "def create_section(get_viewport):\n"
        '    return QLabel("Discovered section" if get_viewport() else "Missing viewport")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sections, "__path__", [*sections.__path__, str(tmp_path)])

    # The discovered section receives the same viewport accessor as the built-in sections.
    viewport = pane.BoardViewport()
    panel = ControlsPanel(lambda: viewport, None, Event())
    labels = panel.findChildren(QLabel)
    assert [label.text() for label in labels] == [
        "Discovered section",
        "Viewport",
        "Render",
        "Engine",
        "Color Scheme",
        "Resolution",
        "Aspect Ratio",
    ]

    # Keep the presets and guide in Viewport and all three selectors in Render.
    viewport_section = labels[1].parentWidget()
    render_section = labels[2].parentWidget()
    assert len(viewport_section.findChildren(QPushButton)) == 4
    assert viewport_section.findChild(QCheckBox).text() == "Show Render Frame"
    assert render_section.findChildren(QComboBox) == panel.findChildren(QComboBox)


def test_viewport_discovers_new_qml_overlay(app, monkeypatch, tmp_path):
    # Add a QML overlay with a required reference back to the host viewport.
    (tmp_path / "TestFeature.qml").write_text(
        "import QtQuick\n"
        "Item {\n"
        "    required property Item viewport\n"
        '    objectName: "testFeature"\n'
        "    property real pitch: viewport.cameraAngles.x\n"
        "}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pane, "FEATURES_DIR", tmp_path)
    view = pane.BoardViewport()
    view.load_model(tmp_path / "unused.glb")
    try:
        # Mount the overlay once the scene is framed and check its live camera binding.
        root = view.rootObject()

        def overlays():
            return [
                child
                for item in root.childItems()
                for child in item.childItems()
                if child.objectName() == "testFeature"
            ]

        assert not overlays()
        root.setProperty("boardRadius", 1.0)
        QTest.qWait(20)
        (feature,) = overlays()
        view.set_camera_view(-82, -34)
        assert feature.property("pitch") == -82
    finally:
        view.release_model()
        view.close()


def test_viewport_forwards_qml_failure(app, tmp_path):
    # Observe the Python widget's error signal.
    view = pane.BoardViewport()
    messages = []
    view.failed.connect(messages.append)
    try:
        # Load the QML scene through the viewport widget.
        view.load_model(tmp_path / "board.glb")
        root = view.rootObject()
        assert root is not None, [error.toString() for error in view.errors()]

        # Forward the QML error text to the Python signal consumer.
        root.loadFailed.emit("Model could not be opened.")
        assert messages[-1] == "Model could not be opened."
    finally:
        view.release_model()
        view.close()


def test_render_frame_follows_aspect_ratio_and_viewport_size(app, tmp_path):
    # Load the viewport and connect the actual format controls.
    view = pane.BoardViewport()
    view.resize(800, 600)
    view.load_model(tmp_path / "unused.glb")
    panel = ControlsPanel(lambda: view, None, Event())
    panel.set_ready(None)
    engine, _, resolution, ratio = panel.findChildren(QComboBox)
    checkbox = panel.findChild(QCheckBox)
    try:
        # The overlay starts hidden and the default guide is portrait.
        root = view.rootObject()
        root.setProperty("boardRadius", 1.0)
        QTest.qWait(20)
        (frame,) = [
            child
            for item in root.childItems()
            for child in item.childItems()
            if child.objectName() == "renderFrame"
        ]
        assert not frame.property("visible")
        assert engine.currentText() == "Ray Tracing"
        assert (resolution.currentText(), ratio.currentText()) == ("FHD", "9:16")
        assert ratio.itemText(1) == "3:4"
        assert root.property("renderFrameWidth") / root.property("renderFrameHeight") == 9 / 16

        # Show the guide and check every aspect ratio at 4K.
        checkbox.click()
        assert frame.property("visible")
        resolution.setCurrentText("4K")
        for label, size in (
            ("9:16", (2160, 3840)),
            ("3:4", (2160, 2880)),
            ("16:9", (3840, 2160)),
            ("4:3", (2880, 2160)),
            ("1:1", (2160, 2160)),
        ):
            ratio.setCurrentText(label)
            assert view.output_size == size
            width = root.property("renderFrameWidth")
            height = root.property("renderFrameHeight")
            assert width / height == pytest.approx(size[0] / size[1])
            assert width <= root.width() - 32
            assert height <= root.height() - 32

        # Resize the viewport and hide the guide without changing the output size.
        root.setWidth(400)
        assert root.property("renderFrameWidth") < width
        checkbox.click()
        assert not frame.property("visible")
        assert view.output_size == (2160, 2160)
    finally:
        view.release_model()
        view.close()
