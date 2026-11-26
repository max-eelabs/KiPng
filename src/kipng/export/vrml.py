# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Recover source VRML material opacity for footprint models."""

import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from ..contracts import BoardSnapshot, PreviewCancelled
from .board import QUOTED_TEXT

BOARD_FIELDS = re.compile(
    rf"(?P<footprint>\((?:footprint|module)\s)"
    rf'|\((?:property\s+"Reference"|fp_text\s+reference)\s+"(?P<reference>{QUOTED_TEXT})"'
    rf'|\(model\s+"(?P<path>{QUOTED_TEXT})"'
    rf'|"{QUOTED_TEXT}"|[()]'
)
MODEL_VARIABLE = re.compile(r"\$\{(\w+)\}|\$\((\w+)\)")
VRML_TEXT = re.compile(rf'"{QUOTED_TEXT}"|#[^\r\n]*')
MATERIAL = re.compile(r"\bMaterial\s*\{([^{}]*)\}")
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
DIFFUSE_COLOR = re.compile(rf"\bdiffuseColor\s+({NUMBER})[\s,]+({NUMBER})[\s,]+({NUMBER})")
TRANSPARENCY = re.compile(rf"\btransparency\s+({NUMBER})")
SUBSTITUTE_SUFFIXES = (".step", ".stp", ".iges", ".igs")


@dataclass(frozen=True)
class SourceMaterial:
    color: tuple[float, float, float]
    opacity: float


def footprint_models(text: str) -> Iterator[tuple[str, list[str]]]:
    """Read direct footprint model fields from a saved or live PCB."""
    depth = 0
    reference = None
    paths = None
    for match in BOARD_FIELDS.finditer(text):
        token = match[0]
        if token == ")":
            if depth == 2 and paths is not None:
                if reference is not None:
                    yield reference, paths
                paths = None
            depth -= 1
        elif token.startswith("("):
            if depth == 1 and match["footprint"]:
                reference, paths = None, []
            if depth == 2 and paths is not None:
                if match["reference"] is not None:
                    reference = match["reference"]
                if match["path"] is not None:
                    paths.append(match["path"])
            depth += 1


def model_path(escaped: str, project_dir: Path | None) -> Path | None:
    """Resolve model paths with the project directory and process environment."""
    try:
        filename = json.loads(f'"{escaped}"')
    except ValueError:
        return None

    def expand(match: re.Match[str]) -> str:
        variable = match[1] or match[2]
        if variable == "KIPRJMOD" and project_dir is not None:
            return project_dir.as_posix()
        return os.environ.get(variable, match[0])

    filename = MODEL_VARIABLE.sub(expand, filename)
    path = Path(filename)
    if path.suffix.lower() != ".wrl" or MODEL_VARIABLE.search(filename):
        return None
    if path.is_absolute():
        return path
    return project_dir / path if project_dir is not None else None


def linear_channel(value: float) -> float:
    # KiCad's GLB exporter converts VRML diffuse colors from sRGB to linear RGB.
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def read_materials(path: Path) -> tuple[SourceMaterial, ...]:
    try:
        # A substitute CAD model may have a different surface despite matching colors.
        if any(path.with_suffix(suffix).is_file() for suffix in SUBSTITUTE_SUFFIXES):
            return ()
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except (OSError, ValueError):
        return ()
    if not text.startswith("#VRML V2.0") or "transparency" not in text:
        return ()

    materials = []
    for body in MATERIAL.findall(VRML_TEXT.sub("", text)):
        color = DIFFUSE_COLOR.search(body)
        transparency = TRANSPARENCY.search(body)
        red, green, blue = map(float, color.groups()) if color else (0.8, 0.8, 0.8)
        opacity = 1 - float(transparency[1]) if transparency else 1.0
        if all(0 <= value <= 1 for value in (red, green, blue, opacity)):
            linear = (linear_channel(red), linear_channel(green), linear_channel(blue))
            materials.append(SourceMaterial(linear, opacity))
    return tuple(materials)


def footprint_materials(
    snapshot: BoardSnapshot, cancelled: Event
) -> dict[str, tuple[SourceMaterial, ...]]:
    """Identify footprint materials whose opacity can be matched unambiguously."""
    if ".wrl" not in snapshot.text.lower():
        return {}

    cache: dict[Path, tuple[SourceMaterial, ...]] = {}
    palettes: dict[str, tuple[SourceMaterial, ...]] = {}
    seen = set()
    for reference, paths in footprint_models(snapshot.text):
        if cancelled.is_set():
            raise PreviewCancelled
        if reference in seen:
            palettes.pop(reference, None)
            continue
        seen.add(reference)

        # The GLB gives footprint references but no reliable ID for each source model.
        if len(paths) != 1:
            continue
        path = model_path(paths[0], snapshot.project_dir)
        if path is None:
            continue
        if path not in cache:
            cache[path] = read_materials(path)
        if any(material.opacity < 1 for material in cache[path]):
            palettes[reference] = cache[path]
    return palettes
