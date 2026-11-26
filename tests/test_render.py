# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from PIL import Image

from kipng.contracts import BoardSnapshot, ViewportCamera
from kipng.contracts.colors import COLOR_SCHEMES
from kipng.contracts.render import DEFAULT_OUTPUT_SIZE
from kipng.export import render


def test_camera_tracks_orbit_zoom_and_pan():
    # A top-down GLB camera maps to KiCad's unrotated top view.
    camera = ViewportCamera(-90, 0, 0.2, 0, 0, 0.1, 0.08)
    args = render.camera_arguments(camera, 3968, 2160)
    assert args[args.index("--rotate") + 1] == "0,0,0"

    # Orbit to the underside, double the image scale, and drag left and down.
    moved = replace(
        camera, pitch=70, yaw=-40, distance=0.1, frame_half_width=0.04, pan_x=0.002, pan_y=0.004
    )
    moved_args = render.camera_arguments(moved, 3968, 2160)
    assert moved_args[moved_args.index("--rotate") + 1] == "200,0,40"
    assert moved_args[moved_args.index("--light-bottom") + 1] == "0.2"
    assert float(moved_args[moved_args.index("--zoom") + 1]) == pytest.approx(
        2 * float(args[args.index("--zoom") + 1])
    )
    assert moved_args[moved_args.index("--pan") + 1] == "-0.256,-0.512,0"

    # Wrapping a top-facing camera through 360 degrees keeps its rotation and key light.
    wrapped_args = render.camera_arguments(replace(camera, pitch=270, yaw=360), 3968, 2160)
    assert wrapped_args == args


@pytest.mark.parametrize(
    ("output_size", "canvas_size"),
    [(DEFAULT_OUTPUT_SIZE, (2304, 3968)), ((2880, 2160), (3024, 2288))],
)
def test_render_stages_live_board_and_saves_selected_png(
    monkeypatch, tmp_path, output_size, canvas_size
):
    # Keep an existing render and supply edited text to an isolated CLI run.
    snapshot = BoardSnapshot("edited PCB", tmp_path, "project")
    camera = ViewportCamera(-55, -25, 0.2, 0, 0, 0.1, 0.08)
    cancelled = Event()
    dimensions = f"{output_size[0]}x{output_size[1]}"
    existing = tmp_path / f"project-render-{dimensions}.png"
    existing.write_bytes(b"previous output")
    cli = tmp_path / "kicad-cli.exe"
    monkeypatch.setattr(render, "find_cli", lambda *_: cli)

    def run_cli(args, cancel_event, timeout, *, env):
        # Confirm the renderer uses the staged snapshot and isolated reference settings.
        assert args[:5] == [str(cli), "pcb", "render", "--quality", "user"]
        assert cancel_event is cancelled
        assert timeout == render.RENDER_TIMEOUT_SECONDS
        assert Path(args[-1]).read_text(encoding="utf-8") == snapshot.text
        config = Path(env["KICAD_CONFIG_HOME"]) / "10.0"
        assert (config / "3d_viewer.json").is_file()

        # Apply all palette materials to both sides without overriding them from the stackup.
        assert "--use-board-stackup-colors" not in args
        theme = json.loads((config / "colors/user.json").read_text(encoding="utf-8"))
        assert theme["3d_viewer"] == {
            "board": "rgba(224, 222, 218, 1)",
            "copper": "rgb(168, 138, 76)",
            "soldermask_top": "rgba(195, 198, 204, 0.73)",
            "soldermask_bottom": "rgba(195, 198, 204, 0.73)",
            "silkscreen_top": "rgba(17, 19, 22, 1)",
            "silkscreen_bottom": "rgba(17, 19, 22, 1)",
        }

        # Supply a transparent raytrace with the board panned right of center.
        width = int(args[args.index("--width") + 1])
        height = int(args[args.index("--height") + 1])
        assert (width, height) == canvas_size
        raw = Image.new("RGBA", (width, height))
        raw.paste("green", (width // 2 + 80, height // 2 - 50, width // 2 + 280, height // 2 + 50))
        raw.save(args[args.index("--output") + 1])

    # Save one PNG at the selected resolution and preserve the previous export.
    monkeypatch.setattr(render, "run_cli", run_cli)
    output = render.render_board_image(
        snapshot,
        camera,
        tmp_path,
        cancelled,
        color_scheme=COLOR_SCHEMES["White"],
        output_size=output_size,
    )
    assert output.name == f"project-render-2-{dimensions}.png"
    assert existing.read_bytes() == b"previous output"
    assert set(tmp_path.iterdir()) == {existing, output}

    # Verify output dimensions and that the board remains right of center.
    with Image.open(output) as png:
        assert png.mode == "RGB"
        assert png.size == output_size
        assert png.getpixel((0, 0)) == (255, 255, 255)
        center_x, center_y = (side // 2 for side in png.size)
        assert png.getpixel((center_x, center_y)) == (255, 255, 255)
        assert png.getpixel((center_x + 120, center_y))[1] in range(136, 140)
