# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

from threading import Event

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

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

    # The discovered section receives the same viewport accessor as the built-in section.
    viewport = pane.BoardViewport()
    panel = ControlsPanel(lambda: viewport, None, Event())
    assert [label.text() for label in panel.findChildren(QLabel)] == [
        "Discovered section",
        "Viewport",
    ]


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
