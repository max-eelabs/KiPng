# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import sys
from threading import Event, Timer

import pytest

from kipng.contracts import PreviewCancelled, PreviewError
from kipng.export import cli


def test_cli_reports_process_output_and_errors():
    # A successful command returns its stdout.
    command = [sys.executable, "-c"]
    assert cli.run_cli([*command, "print('10.0.7')"], Event(), 5) == "10.0.7"

    # A failing command includes stderr in the preview error.
    with pytest.raises(PreviewError, match="board invalid"):
        cli.run_cli([*command, "raise SystemExit('board invalid')"], Event(), 5)


def test_cli_times_out():
    with pytest.raises(PreviewError, match="timed out"):
        cli.run_cli([sys.executable, "-c", "import time; time.sleep(60)"], Event(), 1)


def test_cli_can_be_cancelled():
    # Signal cancellation while a long-running command is in flight.
    cancelled = Event()
    timer = Timer(0.3, cancelled.set)
    timer.start()
    try:
        # The CLI runner stops before reaching the timeout.
        with pytest.raises(PreviewCancelled):
            cli.run_cli([sys.executable, "-c", "import time; time.sleep(60)"], cancelled, 5)
    finally:
        timer.cancel()
        timer.join()


def test_cli_falls_back_from_an_incompatible_executable(monkeypatch, tmp_path):
    # Put an older editor-supplied CLI ahead of a compatible CLI on PATH.
    custom = tmp_path / "custom" / "kicad-cli.exe"
    fallback = tmp_path / "path" / "kicad-cli.exe"
    for path in (custom, fallback):
        path.parent.mkdir()
        path.touch()
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda name: str(fallback))
    monkeypatch.setattr(
        cli, "run_cli", lambda args, *_: "9.0.0" if args[0] == str(custom) else "10.0.7"
    )

    # Select the compatible CLI after rejecting the editor's candidate.
    assert cli.find_cli(str(custom), Event()) == fallback


def test_cli_finds_macos_app_bundle_without_path(monkeypatch, tmp_path):
    # Simulate the standard macOS installation with no CLI on PATH.
    executable = tmp_path / "kicad-cli"
    executable.touch()
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    monkeypatch.setattr(cli, "MACOS_CLI", executable)
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli, "run_cli", lambda *_: "10.0.7")

    # KiPng picks the CLI inside the application bundle.
    assert cli.find_cli(None, Event()) == executable
