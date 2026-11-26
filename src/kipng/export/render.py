# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Raytrace the preview snapshot with the reference renderer's KiCad settings."""

import json
import os
from math import ceil, pi, tan
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from PIL import Image

from ..contracts import BoardSnapshot, PreviewCancelled, PreviewError, ViewportCamera
from ..contracts.background import DEFAULT_BACKGROUND, BackgroundSettings
from ..contracts.colors import COLOR_SCHEMES, DEFAULT_COLOR_SCHEME, PREVIEW_COPPER_RGB, BoardColors
from ..contracts.render import DEFAULT_OUTPUT_SIZE, DEFAULT_SHADOW, FHD_SIZES, ShadowSettings
from .board import stage_board
from .cli import find_cli, run_cli
from .render_image import SCALE, composite, save_image

# Leave room around the PNG crop for the shadow and edge checks.
CANVAS_PADDING = (144, 128)
RAY_HALF_ANGLE_TANGENT = tan(pi / 8)
RENDER_TIMEOUT_SECONDS = 600
KEY_LIGHT = "0.2"
RENDER_SETTINGS = {
    "material_mode": 0,
    "raytrace_anti_aliasing": True,
    "raytrace_backfloor": False,
    "raytrace_post_processing": False,
    "raytrace_procedural_textures": False,
    "raytrace_shadows": True,
    "raytrace_reflections": True,
    "raytrace_refractions": True,
    "raytrace_nrsamples_shadows": 1,
    "raytrace_nrsamples_reflections": 1,
    "raytrace_nrsamples_refractions": 1,
    "raytrace_spread_shadows": 0.0,
    "raytrace_spread_reflections": 0.0,
    "raytrace_spread_refractions": 0.0,
}


def theme_color(color: str, opacity: float = 1.0) -> str:
    red, green, blue = bytes.fromhex(color.removeprefix("#"))
    return f"rgba({red}, {green}, {blue}, {opacity:g})"


def render_environment(work: Path, cli: Path, color_scheme: BoardColors) -> dict[str, str]:
    # Isolate the raytracer's settings from the running KiCad editor.
    config_root = work / "config"
    config = config_root / "10.0"
    config.mkdir(parents=True)
    (config / "3d_viewer.json").write_text(
        json.dumps({"meta": {"version": 4}, "render": RENDER_SETTINGS}), encoding="utf-8"
    )
    (config / "kicad_advanced").write_text("MaximumThreads=1\n", encoding="ascii")

    # When no stackup override is requested, KiCad 10 reads the 3D colors from user.json.
    colors = config / "colors"
    colors.mkdir()
    mask = theme_color(color_scheme.solder_mask, color_scheme.mask_opacity)
    silk = theme_color(color_scheme.silkscreen)
    red, green, blue = (round(channel * 255) for channel in PREVIEW_COPPER_RGB)
    theme = {
        "meta": {"name": "KiPng", "version": 5},
        "3d_viewer": {
            "board": theme_color(color_scheme.dielectric),
            "copper": f"rgb({red}, {green}, {blue})",
            "soldermask_top": mask,
            "soldermask_bottom": mask,
            "silkscreen_top": silk,
            "silkscreen_bottom": silk,
        },
    }
    (colors / "user.json").write_text(json.dumps(theme), encoding="utf-8")

    env = dict(os.environ, KICAD_CONFIG_HOME=str(config_root))
    if "KICAD10_3DMODEL_DIR" not in env:
        models = cli.resolve().parent.parent / "share/kicad/3dmodels"
        if models.is_dir():
            env["KICAD10_3DMODEL_DIR"] = str(models)
    return env


def vector_argument(x: float, y: float, z: float) -> str:
    # KiCad's CLI recognises a leading minus on decimal vectors, including when
    # tiny differences between GLB coordinates would usually use scientific notation.
    return ",".join(f"{value:.9f}".rstrip("0").rstrip(".") for value in (x, y, z))


def camera_arguments(
    camera: ViewportCamera, canvas_height: int, frame_width: int, *, exact_distance: bool = False
) -> list[str]:
    if min(camera.distance, camera.board_span, camera.frame_half_width) <= 0:
        raise PreviewError("The board is behind the camera. Pan back to the board and zoom out.")

    # The inverse of Qt's Y-X orbit, followed by the Z-up to Y-up GLB basis change,
    # gives KiCad's X-Z rotation from its top view.
    tilt = (-camera.pitch - 90) % 360
    twist = -camera.yaw
    top_visible = tilt <= 90 or tilt >= 270

    # KiCad normalizes the longest board edge to 12.8 and starts at distance 16.
    # Older poses have no PCB-relative pivot and fit the crop at the PCB plane.
    units_per_glb = 12.8 / camera.board_span
    distance = camera.distance
    if not exact_distance:
        distance = camera.frame_half_width * canvas_height / (RAY_HALF_ANGLE_TANGENT * frame_width)
    distance *= units_per_glb
    zoom = 16 / distance

    pan_x = -camera.pan_x * units_per_glb
    pan_y = -camera.pan_y * units_per_glb
    pivot = []
    if camera.pivot is not None:
        # KiCad's pivot is relative to the PCB center in centimetres, with Z up.
        x, y, z = camera.pivot
        pivot = ["--pivot", vector_argument(100 * x, -100 * z, 100 * y)]
    return [
        "--side",
        "top",
        "--rotate",
        vector_argument(tilt, 0, twist % 360),
        *pivot,
        "--perspective",
        "--zoom",
        f"{zoom:.9g}",
        # A signed vector must be a separate CLI argument.
        "--pan",
        vector_argument(pan_x, pan_y, 0),
        "--light-top",
        KEY_LIGHT if top_visible else "0",
        "--light-bottom",
        "0" if top_visible else KEY_LIGHT,
    ]


def raytrace_canvas(
    camera: ViewportCamera, frame_size: tuple[int, int]
) -> tuple[int, int, float | None]:
    """Match the viewport lens while keeping the padded KiCad canvas bounded."""
    width = frame_size[0] + CANVAS_PADDING[0]
    height = frame_size[1] + CANVAS_PADDING[1]
    if camera.pivot is None or min(camera.distance, camera.frame_half_width) <= 0:
        return width, height, None

    optical_height = (
        camera.distance * frame_size[0] * RAY_HALF_ANGLE_TANGENT / camera.frame_half_width
    )
    if optical_height < frame_size[1]:
        # An explicit pose wider than KiCad's 45-degree lens needs a distance adjustment.
        return width, height, None
    scale = optical_height / height
    return max(width, 2 * ceil(width / (2 * scale))), height, scale


def match_focal_length(raw: Image.Image, frame_size: tuple[int, int], scale: float) -> Image.Image:
    """Remap around the optical center before applying the centered crop and shadow."""
    width = frame_size[0] + CANVAS_PADDING[0]
    height = frame_size[1] + CANVAS_PADDING[1]
    inverse = 1 / scale
    left = (raw.width - width * inverse) / 2
    top = (raw.height - height * inverse) / 2
    return raw.transform(
        (width, height),
        Image.Transform.AFFINE,
        (inverse, 0, left, 0, inverse, top),
        Image.Resampling.BICUBIC,
    )


def render_board_image(
    snapshot: BoardSnapshot,
    camera: ViewportCamera,
    output_dir: Path,
    cancelled: Event,
    *,
    color_scheme: BoardColors = COLOR_SCHEMES[DEFAULT_COLOR_SCHEME],
    output_size: tuple[int, int] = DEFAULT_OUTPUT_SIZE,
    background: BackgroundSettings = DEFAULT_BACKGROUND,
    shadow: ShadowSettings = DEFAULT_SHADOW,
) -> Path:
    # Supersample FHD. The same raytrace canvas provides native pixels for 4K.
    composite_size = (
        (output_size[0] * SCALE, output_size[1] * SCALE)
        if output_size in FHD_SIZES.values()
        else output_size
    )
    width, height, focal_scale = raytrace_canvas(camera, composite_size)
    camera_args = camera_arguments(
        camera, height, composite_size[0], exact_distance=focal_scale is not None
    )
    cli = find_cli(snapshot.preferred_cli, cancelled)
    try:
        with TemporaryDirectory(prefix="kipng-render-") as directory:
            work = Path(directory)
            env = render_environment(work, cli, color_scheme)
            target = work / "board.png"
            with stage_board(snapshot, work) as staged_board:
                args = [
                    str(cli),
                    "pcb",
                    "render",
                    "--quality",
                    "user",
                    "--width",
                    str(width),
                    "--height",
                    str(height),
                    "--background",
                    "transparent",
                    *camera_args,
                    "--light-camera",
                    "1",
                    "--light-side",
                    "0",
                    "--output",
                    str(target),
                    str(staged_board),
                ]
                run_cli(args, cancelled, RENDER_TIMEOUT_SECONDS, env=env)

            if cancelled.is_set():
                raise PreviewCancelled
            if not target.is_file():
                raise PreviewError("KiCad finished without producing a render.")
            with Image.open(target) as raw:
                if "A" not in raw.getbands() and "transparency" not in raw.info:
                    raise PreviewError("KiCad did not render a board on a transparent background.")
                canvas = raw.convert("RGBA")
                if focal_scale is not None:
                    canvas = match_focal_length(canvas, composite_size, focal_scale)
                master = composite(canvas, composite_size, shadow_settings=shadow)
            name = Path(snapshot.project_name).name or "board"
            return save_image(
                master, output_dir, name, cancelled, output_size, background=background
            )
    except (OSError, ValueError) as error:
        raise PreviewError(f"Could not render the board.\n\n{error}") from error
