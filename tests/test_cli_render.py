# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import shlex
import sys
from io import StringIO
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest

from kipng import cli, diagnostics
from kipng.cli import create_parser, render
from kipng.contracts import BoardSnapshot, ViewportCamera
from kipng.contracts.background import BackgroundSettings, BackgroundTexture
from kipng.contracts.colors import COLOR_SCHEMES
from kipng.contracts.options import RenderOptions
from kipng.contracts.render import RenderEngine, ShadowSettings
from kipng.export import render as ray_tracing
from kipng.ui.copy_cli import render_command


def test_cli_flushes_the_saved_png_path_to_stdout(tmp_path, monkeypatch):
    # Record when the CLI flushes stdout after a successful render.
    png = tmp_path / "board render.png"
    stdout = StringIO()
    flush = Mock(wraps=stdout.flush)
    monkeypatch.setattr(stdout, "flush", flush)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(cli, "render", Mock(return_value=png))
    monkeypatch.setattr(diagnostics, "log_path", lambda: tmp_path / "kipng.txt")
    monkeypatch.delenv("KIPNG_LOG_LEVEL", raising=False)

    # The CLI reports the path before process shutdown.
    assert cli.main(["board.kicad_pcb"]) == 0
    assert stdout.getvalue() == f"{png}\n"
    flush.assert_called_once_with()
    assert "Saved PNG" in (tmp_path / "kipng.txt").read_text(encoding="utf-8")


def test_cli_passes_render_settings_and_saved_board_to_ray_tracer(tmp_path, monkeypatch):
    # Set a pose and change every render control from its default.
    board = tmp_path / "board.kicad_pcb"
    board.write_text("(kicad_pcb)", encoding="utf-8")
    output = tmp_path / "render folder"
    png = output / "result.png"
    camera = ViewportCamera(-55, 40, 0.2, -0.01, 0.02, 0.1, 0.07)
    backdrop = BackgroundSettings("#123456", BackgroundTexture.FABRIC_GRAIN)
    lighting = ShadowSettings(-21, 78, 65)
    settings = RenderOptions.from_render(
        RenderEngine.RAY_TRACING, COLOR_SCHEMES["Blue"], (3840, 2160), backdrop, lighting
    )
    renderer = Mock(return_value=png)
    monkeypatch.setattr(ray_tracing, "render_board_image", renderer)

    # Parse a command using the same settings serialization as Copy CLI.
    args = create_parser().parse_args(
        [
            str(board),
            "--output-dir",
            str(output),
            "--camera=-55,40,0.2,-0.01,0.02,0.1,0.07",
            *settings.cli_arguments(),
        ]
    )
    cancelled = Event()
    assert render(args, cancelled) == png

    # The output location and active settings reach the renderer unchanged.
    assert output.is_dir()
    renderer.assert_called_once_with(
        BoardSnapshot("(kicad_pcb)", tmp_path, "board", board_path=board),
        camera,
        output,
        cancelled,
        color_scheme=COLOR_SCHEMES["Blue"],
        output_size=(3840, 2160),
        background=backdrop,
        shadow=lighting,
    )


@pytest.mark.parametrize(
    "options",
    [
        ["--camera=-90,0,nan,0,0,1,1"],
        ["--camera=-90,0,1,0,0,1,0"],
        ["--light-x=-101"],
        ["--background=not-a-color"],
        ["--log-level=verbose"],
    ],
)
def test_cli_rejects_invalid_control_values(options):
    with pytest.raises(SystemExit) as error:
        create_parser().parse_args(["board.kicad_pcb", *options])
    assert error.value.code == 2


def test_copied_posix_command_preserves_shell_metacharacters():
    # Use paths that need quoting and settings that include a color and a negative value.
    python = Path("/virtual env/bin/python")
    launcher = Path("/KiPng checkout/plugin/render.py")
    board = Path("/projects/Robin's ${board}.kicad_pcb")
    snapshot = BoardSnapshot("", board.parent, board.stem, board_path=board)
    camera = ViewportCamera(-90, 0, 1, 0, 0, 1, 1, pivot=(0, 0.025, -0.001))
    settings = RenderOptions(background="#123456", light_x=-25)

    # The POSIX shell and the CLI read back the same paths, pose, and control values.
    command = render_command(python, launcher, snapshot, camera, settings, windows=False)
    executable, script, *args = shlex.split(command)
    assert (Path(executable), Path(script)) == (python, launcher)
    parsed = create_parser().parse_args(args)
    assert parsed.board == board
    assert parsed.camera == camera
    assert RenderOptions.from_cli(parsed) == settings
