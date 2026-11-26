# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Raytrace the preview snapshot with the reference renderer's KiCad settings."""

import json
import os
from math import pi, tan
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from PIL import Image

from ..contracts import BoardSnapshot, PreviewCancelled, PreviewError, ViewportCamera
from ..contracts.colors import COLOR_SCHEMES, DEFAULT_COLOR_SCHEME, PREVIEW_COPPER_RGB, BoardColors
from .board import stage_board
from .cli import find_cli, run_cli
from .render_image import COMPOSITE_SIZE, composite, save_image

CANVAS_SIZE = (2304, 3968)
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


def camera_arguments(camera: ViewportCamera) -> tuple[list[str], tuple[int, int]]:
    if min(camera.distance, camera.board_span, camera.frame_half_width) <= 0:
        raise PreviewError("The board is behind the camera. Pan back to the board and zoom out.")

    # The inverse of Qt's Y-X orbit, followed by the Z-up to Y-up GLB basis change,
    # gives KiCad's X-Z rotation from its top view.
    tilt = (-camera.pitch - 90) % 360
    twist = -camera.yaw
    top_visible = tilt <= 90 or tilt >= 270

    # KiCad normalizes the longest board edge to 12.8 and starts at distance 16.
    # Match the shorter viewport axis to the usable width of the portrait crop.
    units_per_glb = 12.8 / camera.board_span
    half_width = camera.frame_half_width * units_per_glb
    focal_pixels = CANVAS_SIZE[1] / (2 * tan(pi / 8))
    distance = half_width * (2 * focal_pixels / COMPOSITE_SIZE[0])
    zoom = 16 / distance

    pan_x = -camera.pan_x * units_per_glb
    pan_y = -camera.pan_y * units_per_glb
    # Keep the screen-space translation when the reference crop recenters the silhouette.
    translation = (round(pan_x * focal_pixels / distance), round(-pan_y * focal_pixels / distance))
    return [
        "--side",
        "top",
        "--rotate",
        f"{tilt:.9g},0,{twist % 360:.9g}",
        "--perspective",
        "--zoom",
        f"{zoom:.9g}",
        # A signed vector must be a separate CLI argument.
        "--pan",
        f"{pan_x:.9g},{pan_y:.9g},0",
        "--light-top",
        KEY_LIGHT if top_visible else "0",
        "--light-bottom",
        "0" if top_visible else KEY_LIGHT,
    ], translation


def render_board_image(
    snapshot: BoardSnapshot,
    camera: ViewportCamera,
    output_dir: Path,
    cancelled: Event,
    *,
    color_scheme: BoardColors = COLOR_SCHEMES[DEFAULT_COLOR_SCHEME],
) -> Path:
    camera_args, translation = camera_arguments(camera)
    cli = find_cli(snapshot.preferred_cli, cancelled)
    try:
        with TemporaryDirectory(prefix="kipng-render-") as directory:
            work = Path(directory)
            env = render_environment(work, cli, color_scheme)
            target = work / "board.png"
            width, height = CANVAS_SIZE
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
                master = composite(raw.convert("RGBA"), translation)
            name = Path(snapshot.project_name).name or "board"
            return save_image(master, output_dir, name, cancelled)
    except (OSError, ValueError) as error:
        raise PreviewError(f"Could not render the board.\n\n{error}") from error
