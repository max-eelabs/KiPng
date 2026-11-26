# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import struct
from io import BytesIO

import pytest
from PIL import Image

from kipng.export.glb import prepare_preview_materials


def test_preview_adds_separate_paste_apertures_on_each_board_face(tmp_path):
    # The plot origin is the board origin, even when the outline is offset on the page.
    plots = {}
    for side, x in (("front", 55), ("back", 65)):
        plot = tmp_path / f"{side}.svg"
        plot.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 297 210">'
            f'<rect x="{x - 1}" y="64" width="2" height="2"/></svg>',
            encoding="utf-8",
        )
        plots[side] = plot

    # Create a GLB with a separate, globally positioned board mesh and existing BIN data.
    binary = b"\0" * 12
    scene = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [{"buffer": 0, "byteLength": len(binary)}],
        "accessors": [
            {
                "bufferView": 0,
                "type": "VEC3",
                "componentType": 5126,
                "count": 1,
                "min": [0.05, 0, 0.06],
                "max": [0.07, 0.0016, 0.07],
            }
        ],
        "materials": [{}],
        "meshes": [{"name": "board_PCB", "primitives": [{"attributes": {"POSITION": 0}}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
    }
    data = json.dumps(scene).encode()
    data += b" " * (-len(data) % 4)
    model = tmp_path / "board.glb"
    model.write_bytes(
        struct.pack("<4sIII4s", b"glTF", 2, 28 + len(data) + len(binary), len(data), b"JSON")
        + data
        + struct.pack("<I4s", len(binary), b"BIN\0")
        + binary
    )

    # The new chunks preserve the original buffer and add masked textures above and below.
    prepare_preview_materials(model, board_name="board", paste_plots=plots)
    raw = model.read_bytes()
    _, _, total, json_size, _ = struct.unpack_from("<4sIII4s", raw)
    bin_size, tag = struct.unpack_from("<I4s", raw, 20 + json_size)
    blob = raw[28 + json_size :]
    assert total == len(raw) and tag == b"BIN\0" and bin_size == len(blob)
    result = json.loads(raw[20 : 20 + json_size])
    assert blob.startswith(binary) and result["buffers"][0]["byteLength"] == len(blob)
    assert result["meshes"][0] == scene["meshes"][0]
    assert result["scenes"][0]["nodes"] == [0, 1, 2]

    # Each aperture appears at its original plot position. Its adjacent bare pad stays uncovered.
    for index, (side, x, direction) in enumerate((("front", 55, 1), ("back", 65, -1)), 1):
        assert result["meshes"][index]["name"] == f"Solder paste ({side})"
        assert result["materials"][index]["alphaMode"] == "MASK"
        primitive = result["meshes"][index]["primitives"][0]
        pos = result["accessors"][primitive["attributes"]["POSITION"]]
        expected_y = 0.001605 if direction > 0 else -0.000005
        assert pos["min"][1] == pytest.approx(expected_y)
        texture = result["images"][index - 1]
        view = result["bufferViews"][texture["bufferView"]]
        start = view["byteOffset"]
        with Image.open(BytesIO(blob[start : start + view["byteLength"]])) as png:
            assert png.getpixel((png.width // 2, png.height // 2))[3] == 255
            assert png.getpixel((0, 0))[3] == 0
        assert pos["min"][0] * 1000 == pytest.approx(x - 1, abs=0.03)
        assert pos["max"][0] * 1000 == pytest.approx(x + 1, abs=0.03)
        assert pos["min"][2] * 1000 == pytest.approx(64, abs=0.03)
        assert pos["max"][2] * 1000 == pytest.approx(66, abs=0.03)
