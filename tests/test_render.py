# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from PIL import Image

from kipng.contracts import BoardSnapshot, ViewportCamera
from kipng.export import render


def test_camera_tracks_orbit_zoom_and_pan():
    # A top-down GLB camera maps to KiCad's unrotated top view.
    camera = ViewportCamera(-90, 0, 0.2, 0, 0, 0.1, 0.08)
    args, translation = render.camera_arguments(camera)
    assert args[args.index("--rotate") + 1] == "0,0,0"
    assert translation == (0, 0)

    # Orbit to the underside, double the image scale, and drag left and down.
    moved = replace(
        camera, pitch=70, yaw=-40, distance=0.1, frame_half_width=0.04, pan_x=0.002, pan_y=0.004
    )
    moved_args, translation = render.camera_arguments(moved)
    assert moved_args[moved_args.index("--rotate") + 1] == "200,0,40"
    assert moved_args[moved_args.index("--light-bottom") + 1] == "0.2"
    assert float(moved_args[moved_args.index("--zoom") + 1]) == pytest.approx(
        2 * float(args[args.index("--zoom") + 1])
    )
    assert moved_args[moved_args.index("--pan") + 1] == "-0.256,-0.512,0"
    assert translation == (-54, 108)

    # Wrapping a top-facing camera through 360 degrees keeps its rotation and key light.
    wrapped_args, _ = render.camera_arguments(replace(camera, pitch=270, yaw=360))
    assert wrapped_args == args


def test_render_stages_live_board_and_saves_one_portrait_png(monkeypatch, tmp_path):
    # Keep an existing render and supply edited text to an isolated CLI run.
    snapshot = BoardSnapshot("edited PCB", tmp_path, "project")
    camera = ViewportCamera(-55, -25, 0.2, 0, 0, 0.1, 0.08)
    cancelled = Event()
    existing = tmp_path / "project-render-1080x1920.png"
    existing.write_bytes(b"previous output")
    cli = tmp_path / "kicad-cli.exe"
    monkeypatch.setattr(render, "find_cli", lambda *_: cli)

    def run_cli(args, cancel_event, timeout, *, env):
        # Confirm the renderer uses the staged snapshot and isolated reference settings.
        assert args[:5] == [str(cli), "pcb", "render", "--quality", "user"]
        assert cancel_event is cancelled
        assert timeout == render.RENDER_TIMEOUT_SECONDS
        assert Path(args[-1]).read_text(encoding="utf-8") == snapshot.text
        assert (Path(env["KICAD_CONFIG_HOME"]) / "10.0/3d_viewer.json").is_file()

        # Supply a transparent raytrace with an opaque board silhouette.
        raw = Image.new("RGBA", render.CANVAS_SIZE)
        raw.paste("green", (750, 1500, 1550, 2450))
        raw.save(args[args.index("--output") + 1])

    # Save one portrait PNG and preserve the previous export.
    monkeypatch.setattr(render, "run_cli", run_cli)
    output = render.render_board_image(snapshot, camera, tmp_path, cancelled)
    assert output.name == "project-render-2-1080x1920.png"
    assert existing.read_bytes() == b"previous output"
    assert set(tmp_path.iterdir()) == {existing, output}

    # Verify the portrait dimensions, white background, and color lift.
    with Image.open(output) as png:
        assert png.mode == "RGB"
        assert png.size == (1080, 1920)
        assert png.getpixel((0, 0)) == (255, 255, 255)
        assert png.getpixel((540, 960))[1] in range(136, 140)
