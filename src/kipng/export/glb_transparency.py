# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Restore component opacity that KiCad omits from its viewport GLB."""

from collections.abc import Iterator
from copy import deepcopy
from math import isclose

from .vrml import SourceMaterial

COLOR_TOLERANCE = 0.0001


def matching_opacity(material: dict, sources: tuple[SourceMaterial, ...]) -> float | None:
    pbr = material.get("pbrMetallicRoughness", {})
    rgba = pbr.get("baseColorFactor")
    if (
        material.get("alphaMode", "OPAQUE") != "OPAQUE"
        or "baseColorTexture" in pbr
        or not rgba
        or rgba[3] != 1.0
    ):
        return None

    matches = {
        source.opacity
        for source in sources
        if all(
            isclose(rendered, original, rel_tol=0, abs_tol=COLOR_TOLERANCE)
            for rendered, original in zip(rgba[:3], source.color, strict=True)
        )
    }
    if len(matches) == 1 and (opacity := matches.pop()) < 1.0:
        return opacity
    return None


def mesh_nodes(component: dict, nodes: list[dict]) -> Iterator[dict]:
    pending = [component]
    while pending:
        node = pending.pop()
        if "mesh" in node:
            yield node
        pending.extend(nodes[index] for index in node.get("children", []))


def restore_component_opacity(scene: dict, palettes: dict[str, tuple[SourceMaterial, ...]]) -> bool:
    if not palettes:
        return False

    nodes = scene.get("nodes", [])
    meshes = scene.get("meshes", [])
    materials = scene.get("materials", [])
    blended = {}
    adjusted = {}

    def blended_index(index: int, opacity: float) -> int:
        key = (index, opacity)
        if key not in blended:
            material = deepcopy(materials[index])
            material["alphaMode"] = "BLEND"
            pbr = material["pbrMetallicRoughness"]
            pbr["baseColorFactor"][3] = opacity
            pbr.setdefault("metallicFactor", 0)
            blended[key] = len(materials)
            materials.append(material)
        return blended[key]

    for component in nodes:
        sources = palettes.get(component.get("name"))
        if sources is None:
            continue

        replacements = {}
        for node in mesh_nodes(component, nodes):
            mesh_index = node["mesh"]
            mesh = meshes[mesh_index]
            primitives = mesh["primitives"]
            indexes = [primitive.get("material") for primitive in primitives]
            for index in indexes:
                if index is not None and index not in replacements:
                    opacity = matching_opacity(materials[index], sources)
                    replacements[index] = None if opacity is None else blended_index(index, opacity)

            new_indexes = tuple(replacements.get(index) for index in indexes)
            if all(index is None for index in new_indexes):
                continue

            # GLB components can share meshes and materials. Reuse their buffers only.
            key = (mesh_index, new_indexes)
            if key not in adjusted:
                adjusted[key] = len(meshes)
                meshes.append(
                    {
                        **mesh,
                        "primitives": [
                            {**primitive, "material": index} if index is not None else primitive
                            for primitive, index in zip(primitives, new_indexes, strict=True)
                        ],
                    }
                )
            node["mesh"] = adjusted[key]
    return bool(adjusted)
