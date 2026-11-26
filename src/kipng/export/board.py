# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Capture the live PCB and stage a copy for the command-line exporter."""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from threading import Event

from kipy import KiCad
from kipy.errors import ApiError
from kipy.errors import ConnectionError as KiCadConnectionError

from ..contracts import BoardSnapshot, PreviewCancelled, PreviewError


class KiCadBoardSource:
    def read(self, cancelled: Event) -> BoardSnapshot:
        if cancelled.is_set():
            raise PreviewCancelled
        try:
            editor = KiCad(timeout_ms=5000)
            board = editor.get_board()
            text = board.get_as_string()
            project = board.document.project
        except (ApiError, KiCadConnectionError, OSError) as error:
            raise PreviewError(
                f"Could not read the active PCB. Open a board and try again.\n\n{error}"
            ) from error

        if not text.strip():
            raise PreviewError("KiCad returned an empty board snapshot.")
        if cancelled.is_set():
            raise PreviewCancelled

        # The editor can identify its matching CLI even in a custom installation.
        try:
            preferred_cli = editor.get_kicad_binary_path("kicad-cli")
        except (ApiError, KiCadConnectionError, OSError):
            preferred_cli = None
        project_dir = Path(project.path) if project.path else None
        return BoardSnapshot(text, project_dir, project.name, preferred_cli)


@contextmanager
def stage_board(snapshot: BoardSnapshot, fallback_dir: Path) -> Iterator[Path]:
    project_dir = snapshot.project_dir or fallback_dir
    with ExitStack() as cleanup:
        try:
            # Store the copy beside the original so project-relative models still resolve.
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=project_dir,
                prefix="kipng-preview-",
                suffix=".kicad_pcb",
                delete=False,
            ) as board_file:
                board_path = Path(board_file.name)
                cleanup.callback(board_path.unlink, missing_ok=True)
                board_file.write(snapshot.text)

            # KiCad can write local settings when it closes the copy.
            cleanup.callback(board_path.with_suffix(".kicad_prl").unlink, missing_ok=True)
            project_file = project_dir / f"{snapshot.project_name}.kicad_pro"
            if snapshot.project_name and project_file.is_file():
                copy = board_path.with_suffix(".kicad_pro")
                with project_file.open("rb") as source, copy.open("xb") as target:
                    cleanup.callback(copy.unlink, missing_ok=True)
                    shutil.copyfileobj(source, target)
        except OSError as error:
            raise PreviewError(
                f"Could not create a preview snapshot in {project_dir}.\n\n{error}"
            ) from error
        yield board_path
