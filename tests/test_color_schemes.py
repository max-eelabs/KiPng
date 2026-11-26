# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import struct

from PySide6.QtGui import QColor
from PySide6.QtQuick3D import QQuick3DObject
from PySide6.QtWidgets import QComboBox

from kipng.export.glb import prepare_preview_materials
from kipng.ui.controls.sections.viewport_render import create_section
from kipng.ui.viewport.pane import BoardViewport


def write_layered_model(path):
    # Both mask faces have different tints, and the component shares the laminate material.
    layers = ("PCB", "soldermask", "soldermask", "silkscreen", "component")
    materials = [
        {
            "alphaMode": mode,
            "pbrMetallicRoughness": {"baseColorFactor": color, "metallicFactor": 0},
        }
        for color, mode in (
            ([0.4, 0.45, 0.3, 1], "OPAQUE"),
            ([0.06, 0.16, 0.11, 0.83], "BLEND"),
            ([0.05, 0.17, 0.12, 0.83], "BLEND"),
            ([0.96, 0.96, 0.96, 1], "OPAQUE"),
        )
    ]
    # Give each layer a real mesh so Qt's runtime importer creates its material.
    binary = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 0, 1)
    scene = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [{"buffer": 0, "byteLength": len(binary)}],
        "accessors": [
            {
                "bufferView": 0,
                "type": "VEC3",
                "componentType": 5126,
                "count": 3,
                "min": [0, 0, 0],
                "max": [1, 0, 1],
            }
        ],
        "materials": materials,
        "meshes": [
            {
                "name": f"board_{layer}",
                "primitives": [{"attributes": {"POSITION": 0}, "material": i}],
            }
            for layer, i in zip(layers, (0, 1, 2, 3, 0), strict=True)
        ],
        "nodes": [{"mesh": i} for i in range(len(layers))],
        "scenes": [{"nodes": list(range(len(layers)))}],
    }
    data = json.dumps(scene).encode()
    data += b" " * (-len(data) % 4)
    path.write_bytes(
        struct.pack("<4sIII4s", b"glTF", 2, 28 + len(data) + len(binary), len(data), b"JSON")
        + data
        + struct.pack("<I4s", len(binary), b"BIN\0")
        + binary
    )


def test_color_scheme_switches_live_board_materials_and_restores_green(app, tmp_path):
    # Open a prepared model in the same widget and controls used by the plugin.
    model = tmp_path / "board.glb"
    write_layered_model(model)
    prepare_preview_materials(model, board_name="board")
    view = BoardViewport()
    section = create_section(lambda: view)
    _, selector, _, _, _, _ = section.findChildren(QComboBox)
    try:
        view.load_model(model)
        view.set_camera_view(-60, 30)
        camera = view.capture_camera()
        assert [selector.itemText(i) for i in range(selector.count())] == [
            "Green",
            "Red",
            "White",
            "Black",
            "Blue",
            "Purple",
            "Yellow",
        ]
        assert selector.currentText() == "Green"

        # Both mask faces are available, and the component still has its own material.
        assert sorted(layer for _, layer in view.board_materials) == [
            "PCB",
            "silkscreen",
            "soldermask",
            "soldermask",
        ]
        (component,) = [
            item
            for item in view.rootObject().findChildren(QQuick3DObject)
            if item.property("alphaCutoff") == 0.5
        ]
        component_color = component.property("baseColor")
        assert component_color == QColor.fromRgbF(0.4, 0.45, 0.3)

        # Green applies its more transparent mask immediately on both board faces.
        green_colors = [material.property("baseColor") for material, _ in view.board_materials]
        assert all(
            material.property("baseColor").alphaF() < 0.70
            for material, layer in view.board_materials
            if layer == "soldermask"
        )

        # White updates all board layers, including the silkscreen, in the current view.
        selector.setCurrentText("White")
        for (material, layer), green in zip(view.board_materials, green_colors, strict=True):
            color = material.property("baseColor")
            assert color != green
            if layer == "silkscreen":
                assert color.lightness() < 64
            if layer == "soldermask":
                assert color.lightness() > 170
                assert color.alphaF() < 0.75
        assert component.property("baseColor") == component_color
        assert view.capture_camera() == camera

        # Each palette keeps both mask faces translucent enough to reveal copper.
        for name in ("Red", "Black", "Blue", "Purple", "Yellow"):
            selector.setCurrentText(name)
            assert all(
                material.property("baseColor").alphaF() < 0.75
                for material, layer in view.board_materials
                if layer == "soldermask"
            )

        # Green restores the same material colors and mask transparency as startup.
        selector.setCurrentText("Green")
        restored_colors = [material.property("baseColor") for material, _ in view.board_materials]
        assert restored_colors == green_colors
    finally:
        view.release_model()
        view.close()
