# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Data and interfaces shared by the preview UI and KiCad adapters."""

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Protocol


class PreviewError(Exception):
    """An actionable error to display in the preview window."""


class PreviewCancelled(Exception):
    """The preview closed before preparation completed."""


@dataclass(frozen=True)
class BoardSnapshot:
    text: str
    project_dir: Path | None
    project_name: str
    preferred_cli: str | None = None


class BoardSource(Protocol):
    def read(self, cancelled: Event) -> BoardSnapshot:
        """Read the current PCB without saving it."""
        ...


class ModelExporter(Protocol):
    def __call__(self, output: Path, cancelled: Event) -> BoardSnapshot | None:
        """Write the preview model and return its source snapshot when available."""
        ...


@dataclass(frozen=True)
class ViewportCamera:
    """Orbit angles in degrees and camera-space dimensions in GLB units."""

    pitch: float
    yaw: float
    distance: float
    pan_x: float
    pan_y: float
    board_span: float
    frame_half_width: float


class ImageRenderer(Protocol):
    def __call__(
        self, snapshot: BoardSnapshot, camera: ViewportCamera, output_dir: Path, cancelled: Event
    ) -> Path:
        """Save a PNG in the selected directory and return its path."""
        ...
