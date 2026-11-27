# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import shutil
import struct
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


@pytest.fixture
def write_glb():
    def write(path, materials=None, meshes=None, *, nodes=None):
        # Pad the JSON chunk to the four-byte GLB boundary.
        scene = {"asset": {"version": "2.0"}, "materials": materials or []}
        if meshes is not None:
            scene["meshes"] = meshes
        if nodes is not None:
            scene["nodes"] = nodes
        data = json.dumps(scene).encode("utf-8")
        data += b" " * (-len(data) % 4)

        # Include a binary chunk so tests can check that geometry bytes survive a rewrite.
        binary_chunk = struct.pack("<I4s4s", 4, b"BIN\x00", bytes(range(4)))
        header = struct.pack(
            "<4sIII4s", b"glTF", 2, 20 + len(data) + len(binary_chunk), len(data), b"JSON"
        )
        path.write_bytes(header + data + binary_chunk)
        return binary_chunk

    return write


@pytest.fixture
def packaging_checkout(tmp_path):
    root = Path(__file__).resolve().parents[1]
    checkout = tmp_path / "KiPng checkout"
    checkout.mkdir()
    for name in ("install.cmd", "install.ps1", "metadata.json", "LICENSE", "VERSION"):
        shutil.copyfile(root / name, checkout / name)
    for name in ("plugin", "resources", "src"):
        shutil.copytree(root / name, checkout / name, ignore=shutil.ignore_patterns("__pycache__"))
    script = Path(".github/scripts/build_release.py")
    (checkout / script).parent.mkdir(parents=True)
    shutil.copyfile(root / script, checkout / script)
    return checkout
