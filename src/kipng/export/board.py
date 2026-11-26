# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Capture the live PCB and stage a copy for the command-line exporter."""

import re
import shutil
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from errno import EACCES, EPERM, EROFS
from pathlib import Path, PureWindowsPath
from threading import Event
from uuid import uuid4

from kipy import KiCad
from kipy.errors import ApiError
from kipy.errors import ConnectionError as KiCadConnectionError

from ..contracts import BoardSnapshot, PreviewCancelled, PreviewError

# Match model paths without treating text inside another quoted field as a model.
QUOTED_TEXT = r'(?:[^"\\]|\\.)*'
MODEL_PATH = re.compile(rf'(?P<model>\(model\s+")(?P<path>{QUOTED_TEXT})"|"{QUOTED_TEXT}"')


class KiCadBoardSource:
    def read(self, cancelled: Event) -> BoardSnapshot:
        if cancelled.is_set():
            raise PreviewCancelled
        try:
            editor = KiCad(timeout_ms=5000)
            board = editor.get_board()
            text = board.get_as_string()
            document = board.document
            project = document.project
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
        filename = Path(document.board_filename) if document.board_filename else None
        board_path = filename if filename is not None and filename.is_absolute() else None
        if board_path is None and filename is not None and project_dir is not None:
            board_path = project_dir / filename
        return BoardSnapshot(text, project_dir, project.name, preferred_cli, board_path)


class FileBoardSource:
    """Read a saved PCB and resolve its project-relative assets."""

    def __init__(self, path: Path, preferred_cli: str | None = None) -> None:
        self.path = path
        self.preferred_cli = preferred_cli

    def read(self, cancelled: Event) -> BoardSnapshot:
        if cancelled.is_set():
            raise PreviewCancelled
        try:
            text = self.path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            raise PreviewError(f"Could not read PCB file {self.path}.\n\n{error}") from error
        if not text.strip():
            raise PreviewError(f"The PCB file is empty: {self.path}")
        return BoardSnapshot(text, self.path.parent, self.path.stem, self.preferred_cli, self.path)


@contextmanager
def stage_board(snapshot: BoardSnapshot, fallback_dir: Path) -> Iterator[Path]:
    project_dir = snapshot.project_dir or fallback_dir
    board_path = project_dir / f"kipng-preview-{uuid4().hex}.kicad_pcb"
    with ExitStack() as cleanup:
        try:
            # On Windows tempfile can retry ACL denials as if they were filename collisions.
            try:
                board_file = board_path.open("x", encoding="utf-8")
            except OSError as error:
                if project_dir == fallback_dir or error.errno not in (EACCES, EPERM, EROFS):
                    raise
                board_path = fallback_dir / board_path.name
                board_file = board_path.open("x", encoding="utf-8")
            with board_file:
                cleanup.callback(board_path.unlink, missing_ok=True)
                text = snapshot.text
                if board_path.parent != project_dir:
                    text = relocate_model_paths(text, project_dir)
                board_file.write(text)

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
                f"Could not create a preview snapshot in {board_path.parent}.\n\n{error}"
            ) from error
        yield board_path


def relocate_model_paths(text: str, project_dir: Path) -> str:
    """Keep footprint models rooted at the original project when staging elsewhere."""
    root = project_dir.resolve().as_posix().replace("\\", "\\\\").replace('"', r"\"")

    def replace_path(match: re.Match[str]) -> str:
        if match["model"] is None:
            return match[0]

        path = match["path"]
        for prefix in ("${KIPRJMOD}/", "$(KIPRJMOD)/"):
            if path.startswith(prefix):
                return f'{match["model"]}{root}/{path.removeprefix(prefix)}"'
        if not path or path.startswith(("$", ":", "~", "/", "\\")) or PureWindowsPath(path).drive:
            return match[0]
        return f'{match["model"]}{root}/{path}"'

    return MODEL_PATH.sub(replace_path, text)
