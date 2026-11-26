# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build a shell command that reproduces the current render settings."""

import shlex
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from ..contracts import BoardSnapshot, ViewportCamera
from ..contracts.options import RenderOptions
from .viewport.pane import BoardViewport


def powershell_quote(value: str) -> str:
    # PowerShell also recognizes the typographic single quotation marks.
    escaped = "".join(char * 2 if char in "'‘’‚‛" else char for char in value)
    return f"'{escaped}'"


def render_command(
    python: Path,
    launcher: Path,
    snapshot: BoardSnapshot,
    camera: ViewportCamera,
    settings: RenderOptions,
    *,
    windows: bool = sys.platform == "win32",
) -> str:
    pose = ",".join(
        str(value)
        for value in (
            camera.pitch,
            camera.yaw,
            camera.distance,
            camera.pan_x,
            camera.pan_y,
            camera.board_span,
            camera.frame_half_width,
            *(camera.pivot or ()),
        )
    )
    args = [str(python), str(launcher), str(snapshot.board_path), f"--camera={pose}"]
    args.extend(settings.cli_arguments())
    if snapshot.preferred_cli:
        args.extend(("--kicad-cli", snapshot.preferred_cli))
    if windows:
        # A KiCad venv can launch pythonw.exe, which needs a pipe to receive stdout.
        return "& " + " ".join(map(powershell_quote, args)) + " | Write-Output"
    return shlex.join(args)


def copy_cli(view: BoardViewport | None, snapshot: BoardSnapshot | None) -> None:
    if view is None or snapshot is None:
        return
    if snapshot.board_path is None or not snapshot.board_path.is_file():
        QMessageBox.warning(
            view,
            "Copy CLI",
            "Save the PCB in KiCad, then choose File > Reload Board and try again.",
        )
        return

    root = Path(__file__).resolve().parents[2]
    launcher = root / "render.py"
    if not launcher.is_file():
        launcher = root.parent / "plugin" / "render.py"
    python = Path(sys.executable)
    console_python = python.with_name("python.exe")
    if python.name.lower() == "pythonw.exe" and console_python.is_file():
        python = console_python
    settings = RenderOptions.from_render(
        view.render_engine, view.color_scheme, view.output_size, view.background, view.shadow
    )
    camera = view.capture_camera(snapshot.pcb_geometry)
    command = render_command(python, launcher, snapshot, camera, settings)
    QApplication.clipboard().setText(command)
