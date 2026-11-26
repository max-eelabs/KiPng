# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Adjust preview materials while preserving the original model geometry."""

import json
import os
import shutil
import struct
from copy import deepcopy
from math import isclose
from pathlib import Path

from ..contracts import BOARD_MATERIAL_TAGS
from .paste import add_paste_surfaces

LED_HOUSING_RGB = (0.778, 0.770, 0.626)
KICAD_COPPER_RGB = (0.7, 0.61, 0.0)
PREVIEW_COPPER_RGB = (0.66, 0.54, 0.30)


def prepare_preview_materials(
    model: Path, *, board_name: str = "", paste_plots: dict[str, Path] | None = None
) -> None:
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
        tagged = tag_board_materials(scene, board_name)
        changed = adjust_materials(scene.get("materials", []))
        binary_start = source.tell()
        extra = b""
        if paste_plots:
            binary_size, binary_tag = struct.unpack("<I4s", source.read(8))
            # KiCad exports a single embedded buffer in a GLB BIN chunk.
            if binary_tag != b"BIN\0" or binary_start + 8 + binary_size != length:
                raise ValueError("Expected an embedded KiCad GLB buffer.")
            extra = add_paste_surfaces(scene, board_name, paste_plots, binary_size)
            if extra:
                scene["buffers"][0]["byteLength"] = binary_size + len(extra)
            else:
                source.seek(binary_start)
        if not tagged and not changed and not extra:
            return

        data = json.dumps(scene, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        data += b" " * (-len(data) % 4)
        with updated.open("xb") as target:
            total_size = length - chunk_length + len(data) + len(extra)
            target.write(struct.pack("<4sIII4s", magic, version, total_size, len(data), chunk_type))
            target.write(data)
            if extra:
                target.write(struct.pack("<I4s", binary_size + len(extra), b"BIN\0"))
            shutil.copyfileobj(source, target)
            target.write(extra)
    updated.replace(model)


def tag_board_materials(scene: dict, board_name: str) -> bool:
    """Mark KiCad's board layers for live recoloring in Qt Quick 3D."""
    if not board_name:
        return False

    tags = {f"{board_name}_{layer}": tag for layer, tag in BOARD_MATERIAL_TAGS.items()}
    materials = scene.get("materials", [])
    board_primitives: dict[tuple[int, float], list[dict]] = {}
    claimed = set()
    for mesh in scene.get("meshes", []):
        tag = tags.get(mesh.get("name"))
        for primitive in mesh["primitives"]:
            if "material" not in primitive:
                continue
            index = primitive["material"]
            if tag is None:
                claimed.add(index)
            else:
                board_primitives.setdefault((index, tag), []).append(primitive)

    changed = False
    for (index, tag), primitives in board_primitives.items():
        material = materials[index]
        if material.get("alphaMode") == "MASK":
            continue
        # KiCad can reuse one material for meshes with identical finishes.
        if index in claimed:
            material = deepcopy(material)
            for primitive in primitives:
                primitive["material"] = len(materials)
            materials.append(material)
            changed = True
        claimed.add(index)
        if material.get("alphaCutoff") != tag:
            material["alphaCutoff"] = tag
            changed = True
    return changed


def adjust_materials(materials: list[dict]) -> bool:
    changed = False
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
        # Unify KiCad's gray pads and gold copper with a warmer, less saturated
        # finish that shows through the mask without shifting its hue as much.
        elif (
            metalness == 1
            and color
            and isclose(roughness, 0.4, abs_tol=1e-6)
            and tuple(round(channel, 3) for channel in color[:3])
            in (KICAD_COPPER_RGB, (0.5, 0.5, 0.5))
        ):
            color[:3] = PREVIEW_COPPER_RGB
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
