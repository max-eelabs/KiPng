# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Prepare a temporary GLB from the board open in the PCB Editor."""

import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from ..contracts import BoardSnapshot, BoardSource, PreviewCancelled, PreviewError
from .board import KiCadBoardSource, stage_board
from .cli import find_cli, run_cli
from .glb import prepare_preview_materials

EXPORT_TIMEOUT_SECONDS = 120


def export_board_model(
    output: Path, cancelled: Event, *, source: BoardSource | None = None
) -> BoardSnapshot:
    board_source = source if source is not None else KiCadBoardSource()
    snapshot = board_source.read(cancelled)
    export_snapshot_model(snapshot, output, cancelled)
    return snapshot


def export_snapshot_model(snapshot: BoardSnapshot, output: Path, cancelled: Event) -> None:
    """Write the preview GLB from an already captured board."""
    if cancelled.is_set():
        raise PreviewCancelled
    cli = find_cli(snapshot.preferred_cli, cancelled)

    with stage_board(snapshot, output.parent) as board_path:
        args = [
            str(cli),
            "pcb",
            "export",
            "glb",
            "--output",
            str(output),
            "--subst-models",
            "--include-tracks",
            "--include-pads",
            "--include-zones",
            "--include-silkscreen",
            "--include-soldermask",
            str(board_path),
        ]
        try:
            run_cli(args, cancelled, EXPORT_TIMEOUT_SECONDS)
        except OSError as error:
            raise PreviewError(f"Could not start the KiCad model exporter.\n\n{error}") from error
        if cancelled.is_set():
            raise PreviewCancelled
        try:
            with TemporaryDirectory(prefix="paste-", dir=output.parent) as directory:
                plots = export_paste_plots(cli, board_path, Path(directory), cancelled)
                if cancelled.is_set():
                    raise PreviewCancelled
                prepare_preview_materials(output, board_name=board_path.stem, paste_plots=plots)
        except (OSError, ValueError, struct.error) as error:
            raise PreviewError(f"Could not read the exported board model.\n\n{error}") from error


def export_paste_plots(cli: Path, board: Path, output: Path, cancelled: Event) -> dict[str, Path]:
    # Keep board coordinates in millimetres by using the original page at scale 1.
    run_cli(
        [
            str(cli),
            "pcb",
            "export",
            "svg",
            "--layers",
            "F.Paste,B.Paste",
            "--mode-multi",
            "--page-size-mode",
            "1",
            "--scale",
            "1",
            "--exclude-drawing-sheet",
            "--black-and-white",
            "--drill-shape-opt",
            "0",
            "--output",
            str(output),
            str(board),
        ],
        cancelled,
        EXPORT_TIMEOUT_SECONDS,
    )
    plots = {
        side: output / f"{board.stem}-{layer}_Paste.svg"
        for side, layer in (("front", "F"), ("back", "B"))
    }
    return {side: path for side, path in plots.items() if path.is_file()}
