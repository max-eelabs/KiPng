# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Composite KiCad's solder-paste plots onto the two faces of a GLB board."""

import struct
from io import BytesIO
from math import ceil
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

# Separate paste from the copper and solder mask to prevent depth fighting.
PASTE_OFFSET = 0.000005
BOARD_MESHES = {"PCB", "pad", "via", "copper", "soldermask"}


def add_paste_surfaces(
    scene: dict, board_name: str, plots: dict[str, Path], binary_offset: int
) -> bytes:
    """Extend the scene and return bytes to append to its embedded buffer."""
    accessors = scene.get("accessors", [])
    board_meshes = {f"{board_name}_{suffix}" for suffix in BOARD_MESHES}
    positions = [
        accessors[primitive["attributes"]["POSITION"]]
        for mesh in scene.get("meshes", [])
        if mesh.get("name") in board_meshes
        for primitive in mesh["primitives"]
    ]
    if not positions:
        return b""

    lo = tuple(min(item["min"][axis] for item in positions) for axis in range(3))
    hi = tuple(max(item["max"][axis] for item in positions) for axis in range(3))
    # KiCad GLB uses metres and maps board (X, Y) to (X, Z). The SVG uses millimetres.
    bounds = QRectF(lo[0] * 1000, lo[2] * 1000, (hi[0] - lo[0]) * 1000, (hi[2] - lo[2]) * 1000)
    if bounds.isEmpty():
        return b""
    bounds.adjust(-1, -1, 1, 1)

    extra = bytearray()
    for side, y, normal in (("front", hi[1] + PASTE_OFFSET, 1), ("back", lo[1] - PASTE_OFFSET, -1)):
        plot = plots.get(side)
        if plot is None:
            continue
        texture = paste_texture(plot, bounds)
        if texture is not None:
            area, image = texture
            append_surface(scene, side, area, y, normal, image, binary_offset, extra)
    return bytes(extra)


def paste_texture(plot: Path, bounds: QRectF) -> tuple[QRectF, bytes] | None:
    """Rasterize the apertures to a white texture with transparent gaps."""
    svg = QSvgRenderer(str(plot))
    if not svg.isValid():
        raise ValueError(f"Invalid solder-paste plot {plot.name}.")
    svg.setViewBox(bounds)
    # Preserve small apertures while bounding texture memory on large boards.
    scale = min(80, 4096 / max(bounds.width(), bounds.height()))
    size = (ceil(bounds.width() * scale), ceil(bounds.height() * scale))
    mask = QImage(*size, QImage.Format.Format_RGBA8888)
    if mask.isNull():
        raise ValueError("Could not allocate a solder-paste texture.")
    mask.fill(Qt.GlobalColor.transparent)
    painter = QPainter(mask)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        svg.render(painter, QRectF(0, 0, *size))
    finally:
        painter.end()
    alpha = Image.frombytes("RGBA", size, mask.constBits().tobytes()).getchannel("A")
    paint_bounds = alpha.getbbox()
    if paint_bounds is None:
        return None

    # Keep a transparent pixel around the apertures and exclude the unused page from the mesh.
    left, top, right, bottom = paint_bounds
    left, top = max(0, left - 1), max(0, top - 1)
    right, bottom = min(size[0], right + 1), min(size[1], bottom + 1)
    alpha = alpha.crop((left, top, right, bottom))
    pixel_width, pixel_height = bounds.width() / size[0], bounds.height() / size[1]
    texture_bounds = QRectF(
        bounds.x() + left * pixel_width,
        bounds.y() + top * pixel_height,
        alpha.width * pixel_width,
        alpha.height * pixel_height,
    )
    texture = Image.new("RGBA", alpha.size, "white")
    texture.putalpha(alpha)
    output = BytesIO()
    texture.save(output, format="PNG")
    return texture_bounds, output.getvalue()


def append_surface(
    scene: dict,
    side: str,
    bounds: QRectF,
    y: float,
    normal: int,
    image: bytes,
    binary_offset: int,
    extra: bytearray,
) -> None:
    def add_view(data: bytes, **properties: int) -> int:
        views = scene["bufferViews"]
        index = len(views)
        views.append(
            {
                "buffer": 0,
                "byteOffset": binary_offset + len(extra),
                "byteLength": len(data),
                **properties,
            }
        )
        extra.extend(data)
        extra.extend(b"\0" * (-len(data) % 4))
        return index

    x0, x1 = bounds.left() / 1000, bounds.right() / 1000
    z0, z1 = bounds.top() / 1000, bounds.bottom() / 1000
    corners = ((x0, z0, 0, 0), (x1, z0, 1, 0), (x0, z1, 0, 1), (x1, z1, 1, 1))
    order = (0, 2, 1, 1, 2, 3) if normal == 1 else (0, 1, 2, 1, 3, 2)
    vertices = b"".join(
        struct.pack("<8f", x, y, z, 0, normal, 0, u, v)
        for x, z, u, v in (corners[i] for i in order)
    )
    vertex_view = add_view(vertices, byteStride=32, target=34962)
    accessors = scene["accessors"]
    first = len(accessors)
    attributes = {"bufferView": vertex_view, "componentType": 5126, "count": 6}
    accessors.extend(
        [
            {**attributes, "type": "VEC3", "min": [x0, y, z0], "max": [x1, y, z1]},
            {**attributes, "type": "VEC3", "byteOffset": 12},
            {**attributes, "type": "VEC2", "byteOffset": 24},
        ]
    )

    images = scene.setdefault("images", [])
    textures = scene.setdefault("textures", [])
    textures.append({"source": len(images)})
    images.append({"bufferView": add_view(image), "mimeType": "image/png"})
    name = f"Solder paste ({side})"
    materials = scene["materials"]
    material_index = len(materials)
    materials.append(
        {
            "name": name,
            "alphaMode": "MASK",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.42, 0.42, 0.42, 1],
                "baseColorTexture": {"index": len(textures) - 1},
                "metallicFactor": 0.15,
                "roughnessFactor": 0.72,
            },
        }
    )
    meshes, nodes = scene["meshes"], scene["nodes"]
    nodes.append({"name": name, "mesh": len(meshes)})
    scene["scenes"][scene.get("scene", 0)]["nodes"].append(len(nodes) - 1)
    meshes.append(
        {
            "name": name,
            "primitives": [
                {
                    "attributes": {"POSITION": first, "NORMAL": first + 1, "TEXCOORD_0": first + 2},
                    "material": material_index,
                }
            ],
        }
    )
