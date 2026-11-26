# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Adjust preview materials while keeping the exported model geometry intact."""

import json
import os
import shutil
import struct
from math import isclose
from pathlib import Path

LED_HOUSING_RGB = (0.778, 0.770, 0.626)


def prepare_preview_materials(model: Path) -> None:
    updated = model.with_suffix(".tmp")
    with model.open("rb") as source:
        magic, version, length = struct.unpack("<4sII", source.read(12))
        chunk_length, chunk_type = struct.unpack("<I4s", source.read(8))
        if (
            magic != b"glTF"
            or version != 2
            or chunk_type != b"JSON"
            or length != os.fstat(source.fileno()).st_size
            or chunk_length > length - 20
        ):
            raise ValueError("Expected a GLB 2.0 scene.")
        scene = json.loads(source.read(chunk_length))
        if not adjust_materials(scene.get("materials", [])):
            return

        # Only the JSON chunk changes. Stream the remaining GLB chunks verbatim.
        data = json.dumps(scene, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        data += b" " * (-len(data) % 4)
        with updated.open("xb") as target:
            header = struct.pack(
                "<4sIII4s", magic, version, length - chunk_length + len(data), len(data), chunk_type
            )
            target.write(header)
            target.write(data)
            shutil.copyfileobj(source, target)
    updated.replace(model)


def adjust_materials(materials: list[dict]) -> bool:
    changed = False
    copper_rgb = (0.7, 0.61, 0.0)
    for material in materials:
        pbr = material.get("pbrMetallicRoughness")
        if not pbr or "metallicRoughnessTexture" in pbr:
            continue

        metalness = pbr.get("metallicFactor")
        roughness = pbr.get("roughnessFactor", 1)
        color = pbr.get("baseColorFactor")
        # Make KiCad's blended silkscreen opaque so it always sits above the solder mask.
        if (
            metalness == 0
            and isclose(roughness, 0.9, abs_tol=1e-6)
            and color
            and material.get("alphaMode") == "BLEND"
        ):
            color[3] = 1
            material["alphaMode"] = "OPAQUE"
        # KiCad 10 exports board pads in gray and other PCB copper in gold.
        elif (
            metalness == 1
            and color
            and isclose(roughness, 0.4, abs_tol=1e-6)
            and tuple(round(channel, 3) for channel in color[:3]) in (copper_rgb, (0.5, 0.5, 0.5))
        ):
            color[:3] = copper_rgb
            pbr["roughnessFactor"] = 0.65
        # KiCad's library uses this cream plastic across multiple white LED housings.
        # Match the exported linear RGB so lenses, metal, and painted parts keep their colors.
        elif (
            metalness in (None, 0)
            and material.get("alphaMode", "OPAQUE") == "OPAQUE"
            and "baseColorTexture" not in pbr
            and color
            and all(
                isclose(channel, housing, abs_tol=0.005)
                for channel, housing in zip(color[:3], LED_HOUSING_RGB, strict=True)
            )
        ):
            white = (color[0] + color[1]) / 2
            color[:3] = [white] * 3
            pbr["metallicFactor"] = 0
        # Imported STEP colors can omit metalness, which glTF treats as fully metallic.
        elif metalness is None:
            pbr["metallicFactor"] = 0
        else:
            continue
        changed = True
    return changed
