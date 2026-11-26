# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from PIL import Image

from kipng.contracts import BoardSnapshot, ViewportCamera
from kipng.contracts.background import BackgroundSettings
from kipng.contracts.colors import COLOR_SCHEMES
from kipng.contracts.render import DEFAULT_OUTPUT_SIZE, ShadowSettings
from kipng.export import render
from kipng.export.render_image import composite


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


@pytest.mark.parametrize("size", [(1440, 1080), (1080, 1440)], ids=["4-by-3", "3-by-4"])
def test_raytrace_calibrates_assembly_pivot_and_lens(size):
    # Capture the same camera distance with a crop fitted to each aspect ratio.
    width, height = size
    camera = ViewportCamera(
        -82,
        56,
        0.128,
        0.002,
        -0.003,
        0.04826,
        0.049 * width / height,
        pivot=(0.001, 0.02444, -0.002),
    )
    canvas_width, canvas_height, scale = render.raytrace_canvas(camera, size)
    args = render.camera_arguments(camera, canvas_height, width, exact_distance=True)

    # KiCad receives the actual camera distance and a Z-up, centimetre offset.
    assert args[args.index("--pivot") + 1] == "0.1,0.2,2.444"
    assert render.vector_argument(-0.0000005, 0, 2.444) == "-0.0000005,0,2.444"
    assert float(args[args.index("--zoom") + 1]) == pytest.approx(16 / (0.128 * 12.8 / 0.04826))
    assert scale > 0
    assert canvas_width * scale >= width
    assert scale * canvas_height / (2 * render.RAY_HALF_ANGLE_TANGENT) == pytest.approx(
        width * camera.distance / (2 * camera.frame_half_width)
    )

    # Lens correction keeps an off-center marker on its intended side of the crop.
    raw = Image.new("RGBA", (canvas_width, canvas_height))
    center_x, center_y = canvas_width // 2, canvas_height // 2
    raw.paste("green", (center_x + 60, center_y - 8, center_x + 80, center_y + 8))
    normalized = render.match_focal_length(raw, size, scale)
    framed = composite(normalized, size, shadow_settings=ShadowSettings(strength=0))
    assert framed.getpixel((width // 2, height // 2))[3] == 0
    assert framed.getpixel((width // 2 + round(70 * scale), height // 2))[3] == 255


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


def test_original_shadow_accepts_position_and_strength_settings():
    # Use an opaque silhouette with room for the original scaled shadow.
    board = Image.new("RGBA", (300, 300))
    board.paste("green", (100, 80, 180, 140))
    soft = composite(board, board.size).getchannel("A")
    faded = composite(board, board.size, shadow_settings=ShadowSettings(strength=25))
    off = composite(board, board.size, shadow_settings=ShadowSettings(strength=0))

    # The left half of the slider fades the shadow and eventually removes it.
    assert 0 < faded.getpixel((140, 145))[3] < soft.getpixel((140, 145))
    assert off.getchannel("A").tobytes() == board.getchannel("A").tobytes()

    # The right end preserves the scaled silhouette and removes the blur.
    sharp = composite(board, board.size, shadow_settings=ShadowSettings(strength=100))
    assert sharp.getpixel((140, 150))[3] == 46
    assert sharp.getpixel((140, 151))[3] == 0
    assert soft.getpixel((140, 151)) > 0

    # Both light sliders translate that same crisp silhouette.
    shifted = composite(board, board.size, shadow_settings=ShadowSettings(100, 100, 100))
    band = (0, 142, 300, 300)
    original_box, shifted_box = [
        image.getchannel("A").crop(band).getbbox() for image in (sharp, shifted)
    ]
    assert original_box[0] - shifted_box[0] == 32
    assert shifted_box[3] - original_box[3] == 32


@pytest.mark.parametrize(
    ("board_bounds", "visible_bounds"),
    [
        ((40, 85, 110, 120), (0, 21, 38, 56)),
        ((0, 0, 224, 188), (0, 0, 80, 60)),
        ((5, 80, 40, 100), None),
        (None, None),
    ],
)
def test_ray_tracing_exports_the_visible_crop(monkeypatch, tmp_path, board_bounds, visible_bounds):
    # Supply a CLI canvas that can show part of the board or no board at all.
    monkeypatch.setattr(render, "find_cli", lambda *_: tmp_path / "kicad-cli.exe")

    def run_cli(args, *_args, **_kwargs):
        raw = Image.new("RGBA", (224, 188))
        if board_bounds is not None:
            raw.paste("green", board_bounds)
        raw.save(args[args.index("--output") + 1])

    monkeypatch.setattr(render, "run_cli", run_cli)
    camera = ViewportCamera(-90, 0, 0.2, 0, 0, 0.1, 0.08)

    # Export exactly the selected frame, with transparency where nothing is visible.
    output = render.render_board_image(
        BoardSnapshot("PCB", None, "test"),
        camera,
        tmp_path,
        Event(),
        output_size=(80, 60),
        background=BackgroundSettings(None),
        shadow=ShadowSettings(strength=0),
    )
    with Image.open(output) as image:
        assert image.size == (80, 60)
        assert image.getchannel("A").getbbox() == visible_bounds


def test_ray_tracing_keeps_shadow_from_board_just_outside_crop():
    # Put the board just above the frame so only its shadow falls inside.
    board = Image.new("RGBA", (120, 120))
    board.paste("green", (40, 5, 80, 19))
    rendered = composite(board, (80, 80), shadow_settings=ShadowSettings(strength=100))
    assert rendered.getpixel((40, 0)) == (0, 0, 0, 46)
    assert rendered.getpixel((40, 30))[3] == 0
