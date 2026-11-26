# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import struct
from threading import Event

from kipng.export import exporter
from kipng.export.board import FileBoardSource


def test_export_restores_vrml_opacity_for_only_the_matching_footprint(
    tmp_path, monkeypatch, write_glb
):
    # Give glass and invisible geometry distinct colors, plus an ambiguous red finish.
    source = tmp_path / "board.kicad_pcb"
    source.write_text(
        '(kicad_pcb (footprint "Lamp" (property "Reference" "U1")'
        ' (model "${KIPRJMOD}/lamp.wrl")) (footprint "Other" (property "Reference" "U2")'
        ' (model "other.step")))',
        encoding="utf-8",
    )
    (tmp_path / "lamp.wrl").write_text(
        "#VRML V2.0 utf8\n"
        "# Material { transparency 0.9 diffuseColor 0.5 0.5 0.5 }\n"
        "Material { diffuseColor 0.5, 0.5, 0.5 transparency 7.5e-1 }\n"
        "Material { diffuseColor 1 1 1 transparency 1 }\n"
        "Material { diffuseColor 1 0 0 transparency 0.3 }\n"
        "Material { diffuseColor 1 0 0 }\n",
        encoding="utf-8",
    )
    gray = 0.21404114
    original = [[gray, gray, gray, 1], [1, 1, 1, 1], [1, 0, 0, 1]]
    materials = [{"pbrMetallicRoughness": {"baseColorFactor": color}} for color in original]
    meshes = [{"primitives": [{"material": index} for index in range(3)]}]
    nodes = [{"name": "U1", "children": [1]}, {"mesh": 0}, {"name": "U2", "mesh": 0}]
    output = tmp_path / "board.glb"
    binary_chunk = None

    def run_cli(args, _cancelled, _timeout):
        # Simulate KiCad exporting opaque materials and sharing one mesh between footprints.
        nonlocal binary_chunk
        if args[3] == "glb":
            binary_chunk = write_glb(output, materials, meshes, nodes=nodes)

    monkeypatch.setattr(exporter, "find_cli", lambda *_: tmp_path / "kicad-cli")
    monkeypatch.setattr(exporter, "run_cli", run_cli)

    # Run the normal model export path and decode its GLB.
    exporter.export_board_model(output, Event(), source=FileBoardSource(source))
    data = output.read_bytes()
    json_size = struct.unpack_from("<I", data, 12)[0]
    scene = json.loads(data[20 : 20 + json_size])
    assert data[20 + json_size :] == binary_chunk

    # Only the lamp receives the two unambiguous source opacities.
    lamp_mesh = scene["meshes"][scene["nodes"][1]["mesh"]]
    for primitive, opacity in zip(lamp_mesh["primitives"][:2], [0.25, 0], strict=True):
        material = scene["materials"][primitive["material"]]
        assert material["alphaMode"] == "BLEND"
        assert material["pbrMetallicRoughness"]["baseColorFactor"][3] == opacity
    assert lamp_mesh["primitives"][2]["material"] == 2
    assert scene["nodes"][2]["mesh"] == 0
    assert scene["meshes"][0] == meshes[0]
    assert [
        material["pbrMetallicRoughness"]["baseColorFactor"] for material in scene["materials"][:3]
    ] == original
