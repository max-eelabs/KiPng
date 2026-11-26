# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render a saved PCB without opening the KiCad editor."""

import logging
import signal
import sys
from argparse import ArgumentParser, ArgumentTypeError, Namespace
from math import isfinite
from pathlib import Path
from threading import Event

from .contracts import PreviewCancelled, PreviewError, ViewportCamera
from .contracts.options import RENDER_CONTROLS, RenderOptions, slug
from .contracts.render import CAMERA_PRESETS, RenderEngine
from .diagnostics import LOG_LEVELS, configure_logging

LOGGER = logging.getLogger(__name__)


def parse_camera(value: str) -> ViewportCamera:
    try:
        values = [float(part) for part in value.split(",")]
    except ValueError as error:
        raise ArgumentTypeError("expected seven or ten comma-separated numbers") from error
    if len(values) not in (7, 10):
        raise ArgumentTypeError("expected seven or ten comma-separated numbers")
    if not all(isfinite(number) for number in values):
        raise ArgumentTypeError("camera values must be finite")
    camera = ViewportCamera(*values[:7], pivot=tuple(values[7:]) if len(values) == 10 else None)
    if min(camera.distance, camera.board_span, camera.frame_half_width) <= 0:
        raise ArgumentTypeError("distance, board span, and frame half-width must be positive")
    return camera


def create_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="KiPng", description=__doc__, allow_abbrev=False)
    parser.add_argument("board", type=Path, metavar="BOARD.kicad_pcb")
    parser.add_argument("--output-dir", type=Path, help="PNG folder. Defaults to the PCB folder.")
    parser.add_argument("--kicad-cli", type=Path, help="Preferred path to KiCad 10.0 kicad-cli.")
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=LOG_LEVELS,
        help="Override KIPNG_LOG_LEVEL. Default INFO.",
    )
    for control in RENDER_CONTROLS:
        control.add_argument(parser)

    camera = parser.add_mutually_exclusive_group()
    camera.add_argument(
        "--view",
        choices=[slug(label) for label, *_ in CAMERA_PRESETS],
        default=slug(CAMERA_PRESETS[0][0]),
        help="Fit a camera preset. Default default-front.",
    )
    camera.add_argument(
        "--camera",
        type=parse_camera,
        metavar="POSE",
        help=(
            "Use --camera=PITCH,YAW,DISTANCE,PAN_X,PAN_Y,BOARD_SPAN,FRAME_HALF_WIDTH"
            "[,PIVOT_X,PIVOT_Y,PIVOT_Z]."
        ),
    )
    return parser


def render(args: Namespace, cancelled: Event) -> Path:
    from .export.board import FileBoardSource
    from .export.render import render_board_image

    board = args.board.resolve()
    if board.suffix.lower() != ".kicad_pcb":
        raise PreviewError(f"Expected a .kicad_pcb file: {board}")
    preferred_cli = str(args.kicad_cli.resolve()) if args.kicad_cli else None
    source = FileBoardSource(board, preferred_cli)
    snapshot = source.read(cancelled)
    output_dir = args.output_dir.resolve() if args.output_dir else board.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = RenderOptions.from_cli(args)
    camera = args.camera
    engine = RenderEngine(settings.engine)
    if engine is RenderEngine.VIEWPORT or camera is None:
        from .ui.viewport.cli_render import open_render_surface

        preset = next(tuple(pose) for label, *pose in CAMERA_PRESETS if slug(label) == args.view)
        with open_render_surface(snapshot, settings, cancelled) as (surface, geometry):
            if camera is None:
                surface.set_camera_view(*preset)
                camera = surface.capture_camera(geometry)
            if engine is RenderEngine.VIEWPORT:
                from .ui.viewport.render import save_viewport_render

                frame = surface.grab_render(camera)
        if engine is RenderEngine.VIEWPORT:
            return save_viewport_render(
                frame,
                snapshot,
                output_dir,
                cancelled,
                settings.output_size,
                background=settings.backdrop,
            )

    return render_board_image(
        snapshot,
        camera,
        output_dir,
        cancelled,
        color_scheme=settings.palette,
        output_size=settings.output_size,
        background=settings.backdrop,
        shadow=settings.lighting,
    )


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    with configure_logging(args.log_level):
        return run_render(args)


def run_render(args: Namespace) -> int:
    cancelled = Event()
    previous = signal.signal(signal.SIGINT, lambda *_: cancelled.set())
    try:
        LOGGER.info("Starting CLI render for %s.", args.board)
        output = render(args, cancelled)
        print(output, flush=True)
        LOGGER.info("Saved PNG to %s.", output)
    except PreviewCancelled:
        LOGGER.info("CLI render cancelled.")
        print("KiPng: rendering cancelled.", file=sys.stderr)
        return 130
    except (PreviewError, OSError, ImportError) as error:
        LOGGER.error("CLI render failed: %s", error)
        print(f"KiPng: {error}", file=sys.stderr)
        return 1
    except Exception:
        LOGGER.exception("CLI render failed unexpectedly.")
        print("KiPng: unexpected rendering error. See the KiPng log.", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGINT, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
