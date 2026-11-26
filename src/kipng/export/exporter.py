# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Prepare a temporary GLB from the board open in the PCB Editor."""

import struct
from pathlib import Path
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
            prepare_preview_materials(output)
        except (OSError, ValueError, struct.error) as error:
            raise PreviewError(f"Could not read the exported board model.\n\n{error}") from error

    return snapshot
