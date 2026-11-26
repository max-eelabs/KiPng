# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import struct

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
