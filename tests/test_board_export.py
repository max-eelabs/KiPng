# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

from contextlib import nullcontext
from errno import EACCES, EROFS
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from kipng.contracts import BoardSnapshot, PreviewCancelled, PreviewError
from kipng.export import board, exporter


def test_ipc_uses_live_board_text_and_preferred_cli(monkeypatch, tmp_path):
    # Supply an edited board and the CLI path from the same editor instance.
    project = SimpleNamespace(path=str(tmp_path), name="project")
    open_board = SimpleNamespace(
        get_as_string=lambda: "(kicad_pcb unsaved-text)",
        document=SimpleNamespace(project=project, board_filename="other-name.kicad_pcb"),
    )
    editor = SimpleNamespace(
        get_board=lambda: open_board,
        get_kicad_binary_path=lambda name: f"alternative/{name}.exe",
    )
    monkeypatch.setattr(board, "KiCad", lambda timeout_ms: editor)

    # Capture the live text and enough project information to export it.
    snapshot = board.KiCadBoardSource().read(Event())
    assert snapshot == BoardSnapshot(
        "(kicad_pcb unsaved-text)",
        tmp_path,
        "project",
        "alternative/kicad-cli.exe",
        tmp_path / "other-name.kicad_pcb",
    )


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        pytest.param("success", nullcontext(), id="success"),
        pytest.param("command", pytest.raises(PreviewError, match="Export failed"), id="cli-error"),
        pytest.param("cancelled", pytest.raises(PreviewCancelled), id="cancelled"),
        pytest.param(
            "invalid",
            pytest.raises(PreviewError, match="Could not read the exported"),
            id="invalid-model",
        ),
    ],
)
def test_export_stages_project_and_cleans_up(monkeypatch, tmp_path, write_glb, outcome, expected):
    # Keep the saved board and project beside the temporary export files.
    project_dir = tmp_path / "PCB á"
    project_dir.mkdir()
    original_board = project_dir / "design.kicad_pcb"
    original_board.write_text("last saved board", encoding="utf-8")
    original_project = project_dir / "design.kicad_pro"
    original_project.write_bytes(b"project settings")

    # Supply a live snapshot with different text from the saved board.
    cancellation = Event()
    output = tmp_path / "preview.glb"
    cli = tmp_path / "kicad-cli.exe"
    snapshot = BoardSnapshot("live board", project_dir, "design", str(cli))
    reader = SimpleNamespace(read=lambda cancelled: snapshot)
    monkeypatch.setattr(exporter, "find_cli", lambda preferred, cancelled: cli)

    plotted = []

    def run_export_command(args, cancelled, timeout):
        if args[3] == "svg":
            # Plot both paste layers from the same staged board as the GLB.
            directory = Path(args[args.index("--output") + 1])
            staged = Path(args[-1])
            assert staged.parent == project_dir
            assert staged.read_text(encoding="utf-8") == snapshot.text
            assert args[args.index("--layers") + 1] == "F.Paste,B.Paste"
            assert "--exclude-drawing-sheet" in args
            assert cancelled is cancellation
            plotted.append(directory)
            return

        # Check the arguments, timeout, and cancellation event passed to KiCad.
        assert args[:4] == [str(cli), "pcb", "export", "glb"]
        assert args[4:6] == ["--output", str(output)]
        assert "--subst-models" in args and "--include-silkscreen" in args
        assert cancelled is cancellation and timeout == 120

        # Verify that KiCad sees the unsaved board and a copy of its project settings.
        staged = next(project_dir.glob("kipng-preview-*.kicad_pcb"))
        assert args[-1] == str(staged)
        assert staged.read_text(encoding="utf-8") == "live board"
        assert staged.with_suffix(".kicad_pro").read_bytes() == b"project settings"

        # Simulate the local settings that KiCad can leave next to a board.
        staged.with_suffix(".kicad_prl").write_bytes(b"CLI settings")

        # Return the selected export outcome.
        if outcome == "command":
            raise PreviewError("Export failed")
        if outcome == "cancelled":
            cancelled.set()
        elif outcome == "invalid":
            output.write_bytes(b"truncated")
        else:
            write_glb(output)

    # Run the exporter and check the expected result for this case.
    monkeypatch.setattr(exporter, "run_cli", run_export_command)
    with expected:
        exporter.export_board_model(output, cancellation, source=reader)
    if outcome == "success":
        assert output.read_bytes().startswith(b"glTF")
        assert len(plotted) == 1 and not plotted[0].exists()

    # Cleanup always removes the staged files and preserves the original project.
    assert set(project_dir.iterdir()) == {original_board, original_project}
    assert original_board.read_text(encoding="utf-8") == "last saved board"
    assert original_project.read_bytes() == b"project settings"


def test_unsaved_project_can_stage_in_fallback_directory(tmp_path):
    # Stage a board with no project directory.
    snapshot = BoardSnapshot("new board", None, "")
    with board.stage_board(snapshot, tmp_path) as staged:
        assert staged.parent == tmp_path
        assert staged.read_text(encoding="utf-8") == "new board"

    # The fallback directory is empty after the preview closes the snapshot.
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("denied", [EACCES, EROFS], ids=["permission-denied", "read-only"])
def test_read_only_project_stages_once_in_temp_with_original_model_paths(
    tmp_path, monkeypatch, denied
):
    # Keep the saved project and its relative model paths in a protected directory.
    project_dir = tmp_path / "original project"
    project_dir.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    original = project_dir / "board.kicad_pro"
    original.write_bytes(b"project settings")
    text = (
        '(model "${KIPRJMOD}/models/relative.step")\n'
        '(model "models/bare.step")\n'
        '(model "${KICAD10_3DMODEL_DIR}/library.step")\n'
        '(property "text" "literal (model \\"do not change\\")")'
    )
    open_path = Path.open
    attempts = []

    def open_file(path, mode="r", *args, **kwargs):
        # Deny creation in the project directory once Python opens the staging file.
        if mode == "x" and path.suffix == ".kicad_pcb":
            attempts.append(path.parent)
            if path.parent == project_dir:
                raise OSError(denied, "Project is read only")
        return open_path(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)

    # Stage in scratch with paths still pointing to the original project.
    snapshot = BoardSnapshot(text, project_dir, "board")
    with board.stage_board(snapshot, scratch) as staged:
        root = project_dir.resolve().as_posix()
        assert attempts == [project_dir, scratch]
        assert staged.parent == scratch
        assert staged.read_text(encoding="utf-8") == text.replace(
            "${KIPRJMOD}/models/relative.step", f"{root}/models/relative.step"
        ).replace('"models/bare.step"', f'"{root}/models/bare.step"')
        assert staged.with_suffix(".kicad_pro").read_bytes() == b"project settings"

    # The fallback files disappear while the saved project remains available.
    assert not list(scratch.iterdir())
    assert original.read_bytes() == b"project settings"
