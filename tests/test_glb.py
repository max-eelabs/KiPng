# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import struct
from copy import deepcopy

import pytest

from kipng.export.glb import prepare_preview_materials


def test_preview_materials_keep_geometry_and_unify_copper(tmp_path, write_glb):
    # Build a model with both PCB finishes, translucent layers, and component materials.
    board_copper = {
        "baseColorFactor": [0.7, 0.61, 0, 1],
        "metallicFactor": 1,
        "roughnessFactor": 0.4,
    }
    pad = {**board_copper, "baseColorFactor": [0.5, 0.5, 0.5, 1]}
    unrelated_metal = {**board_copper, "baseColorFactor": [0.1, 0.2, 0.3, 1]}
    silkscreen = {"baseColorFactor": [1, 1, 1, 0.9], "metallicFactor": 0, "roughnessFactor": 0.9}
    mask = {**silkscreen, "baseColorFactor": [0.1, 0.3, 0.1, 0.83], "roughnessFactor": 0.6}
    step_color = {"baseColorFactor": [0.2, 0.2, 0.2, 1]}
    named_finishes = {
        "board copper": board_copper,
        "pad": pad,
        "unrelated metal": unrelated_metal,
        "silkscreen": silkscreen,
        "solder mask": mask,
        "STEP color": step_color,
    }
    materials = [
        {"name": name, "pbrMetallicRoughness": finish} for name, finish in named_finishes.items()
    ]
    for material in materials:
        if material["name"] in ("silkscreen", "solder mask"):
            material["alphaMode"] = "BLEND"
    original = {material["name"]: deepcopy(material) for material in materials}
    model = tmp_path / "board.glb"
    binary_chunk = write_glb(model, materials)

    # Prepare the model and verify that the GLB header and geometry survived the rewrite.
    prepare_preview_materials(model)
    result = model.read_bytes()
    magic, version, length, json_size, tag = struct.unpack("<4sIII4s", result[:20])
    assert (magic, version, length, tag) == (b"glTF", 2, len(result), b"JSON")
    assert result[20 + json_size :] == binary_chunk
    scene = json.loads(result[20 : 20 + json_size])
    updated = {material["name"]: material for material in scene["materials"]}

    # Both PCB copper materials get the same finish.
    expected_finish = {**board_copper, "roughnessFactor": 0.65}
    assert updated["board copper"]["pbrMetallicRoughness"] == expected_finish
    assert updated["pad"]["pbrMetallicRoughness"] == expected_finish

    # Opaque silkscreen remains legible above the translucent solder mask.
    assert updated["silkscreen"]["alphaMode"] == "OPAQUE"
    assert updated["silkscreen"]["pbrMetallicRoughness"]["baseColorFactor"][3] == 1
    assert updated["solder mask"] == original["solder mask"]

    # Preserve explicit component metals and supply a default for STEP colors.
    assert updated["unrelated metal"] == original["unrelated metal"]
    assert updated["STEP color"]["pbrMetallicRoughness"]["metallicFactor"] == 0

    # Preparing the same model again leaves identical bytes and no temporary files.
    prepare_preview_materials(model)
    assert model.read_bytes() == result
    assert list(tmp_path.iterdir()) == [model]


def test_invalid_glb_is_rejected_without_overwriting_it(tmp_path):
    # Write a GLB header with an unsupported version.
    model = tmp_path / "invalid.glb"
    invalid = struct.pack("<4sIII4s", b"glTF", 1, 20, 0, b"JSON")
    model.write_bytes(invalid)

    # Reject the file and preserve its original bytes.
    with pytest.raises(ValueError, match="GLB 2.0"):
        prepare_preview_materials(model)
    assert model.read_bytes() == invalid


def test_preview_neutralizes_white_led_housing_and_preserves_lens_colors(tmp_path, write_glb):
    # Use the linear RGB exported for KiCad's LED housing, amber diffuser, and blue lens.
    housing = [0.777554274, 0.769720018, 0.626096785, 1.0]
    amber = [0.708704174, 0.504022241, 0.210357457, 1.0]
    blue = [0.016753944, 0.134274319, 0.487405360, 1.0]
    materials = [
        {"pbrMetallicRoughness": {"baseColorFactor": color, "metallicFactor": 0}}
        for color in (housing, amber, blue)
    ]
    materials.append(
        {
            "pbrMetallicRoughness": {
                "baseColorFactor": housing,
                "baseColorTexture": {"index": 0},
                "metallicFactor": 0,
            }
        }
    )
    model = tmp_path / "led.glb"
    write_glb(model, materials)

    # Update the housing in the preview GLB and read back the serialized materials.
    prepare_preview_materials(model)
    result = model.read_bytes()
    json_size = struct.unpack_from("<I", result, 12)[0]
    updated = json.loads(result[20 : 20 + json_size])["materials"]

    # Restore neutral white without changing either lens or the textured material.
    white = (housing[0] + housing[1]) / 2
    assert updated[0]["pbrMetallicRoughness"]["baseColorFactor"] == [white, white, white, 1.0]
    assert updated[1:] == materials[1:]
