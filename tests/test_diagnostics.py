# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PySide6.QtCore import qInstallMessageHandler, qWarning

from kipng import app, cli, diagnostics

LOGGER = logging.getLogger("kipng.test")


@pytest.fixture
def log_path(monkeypatch, tmp_path):
    path = tmp_path / "KiPng" / "logs" / "kipng.txt"
    monkeypatch.setattr(diagnostics, "log_path", lambda: path)
    monkeypatch.delenv(diagnostics.LOG_LEVEL_ENV, raising=False)
    return path


@pytest.mark.parametrize(
    ("env_level", "override", "expected", "invalid"),
    [
        (None, None, logging.INFO, False),
        ("debug", None, logging.DEBUG, False),
        ("debug", "error", logging.ERROR, False),
        ("verbose", None, logging.INFO, True),
    ],
)
def test_levels_filter_records(log_path, monkeypatch, env_level, override, expected, invalid):
    # Configure the environment and parse any explicit CLI override.
    if env_level is not None:
        monkeypatch.setenv(diagnostics.LOG_LEVEL_ENV, env_level)
    options = ["board.kicad_pcb"]
    if override is not None:
        options.extend(["--log-level", override])
    args = cli.create_parser().parse_args(options)

    # Write records through KiPng and an unrelated Python logger.
    with diagnostics.configure_logging(args.log_level) as active:
        assert active == log_path
        LOGGER.debug("debug message")
        LOGGER.info("info message – árvíz")
        LOGGER.error("error message")
        logging.getLogger("dependency").error("dependency message")

    # The log respects the effective level and preserves Unicode text.
    contents = log_path.read_text(encoding="utf-8")
    assert ("debug message" in contents) == (expected <= logging.DEBUG)
    assert ("info message – árvíz" in contents) == (expected <= logging.INFO)
    assert "error message" in contents
    assert "dependency message" not in contents
    assert ("Invalid KIPNG_LOG_LEVEL" in contents) == invalid


def test_qt_warnings_are_logged_and_previous_handler_is_restored(log_path):
    # Install a prior message handler to verify KiPng restores it on exit.
    previous_messages = []
    previous = qInstallMessageHandler(lambda _, __, message: previous_messages.append(message))
    try:
        with diagnostics.configure_logging():
            qWarning("Qt warning in run")
        qWarning("Qt warning after run")
    finally:
        qInstallMessageHandler(previous)

    # Qt warnings are routed to exactly one destination at a time.
    contents = log_path.read_text(encoding="utf-8")
    assert "WARNING kipng.qt" in contents
    assert "Qt warning in run" in contents
    assert previous_messages == ["Qt warning after run"]


def test_log_retains_only_nine_backups(log_path, monkeypatch):
    # Force more than ten rotations using a small file size.
    monkeypatch.setattr(diagnostics, "MAX_LOG_BYTES", 128)
    with diagnostics.configure_logging():
        for number in range(100):
            LOGGER.info("Record %03d %s", number, "x" * 64)

    # The active file holds the newest record and the oldest archive was discarded.
    logs = sorted(log_path.parent.glob("kipng.txt*"))
    assert [path.name for path in logs] == ["kipng.txt", *(f"kipng.txt.{i}" for i in range(1, 10))]
    assert "Record 099" in log_path.read_text(encoding="utf-8")
    assert all("Record 000" not in path.read_text(encoding="utf-8") for path in logs)


def test_separate_processes_can_write_and_rotate_the_same_file(log_path):
    # Run independent Python processes with a shared destination and rotation settings.
    source = Path(diagnostics.__file__).resolve().parents[1]
    python_path = os.pathsep.join(filter(None, (str(source), os.environ.get("PYTHONPATH"))))
    script = """
import logging
import sys
from pathlib import Path
from kipng import diagnostics

diagnostics.log_path = lambda: Path(sys.argv[1])
diagnostics.MAX_LOG_BYTES = 4096
with diagnostics.configure_logging():
    for number in range(100):
        logging.getLogger('kipng.test').info('entry %s-%03d', sys.argv[2], number)
"""

    def run_worker(worker):
        return subprocess.run(
            [sys.executable, "-c", script, str(log_path), worker],
            env={**os.environ, "PYTHONPATH": python_path},
            capture_output=True,
            text=True,
            timeout=30,
        )

    with ThreadPoolExecutor(2) as pool:
        for result in pool.map(run_worker, ("a", "b")):
            assert result.returncode == 0, result.stderr
            assert result.stderr == ""

    # All records survive concurrent writes and rollover within the retained history.
    logs = list(log_path.parent.glob("kipng.txt*"))
    assert 1 < len(logs) <= 10
    lines = [line for path in logs for line in path.read_text(encoding="utf-8").splitlines()]
    assert sorted(line.split("entry ")[1] for line in lines) == [
        f"{worker}-{number:03d}" for worker in ("a", "b") for number in range(100)
    ]


def test_file_setup_failure_leaves_rendering_available(log_path, capsys, monkeypatch):
    # Occupy the log filename with a directory to make file setup fail.
    log_path.mkdir(parents=True)
    output = log_path.parent / "test.png"
    monkeypatch.setattr(cli, "render", lambda *_: output)

    # The CLI returns the output path and reports the setup problem once.
    assert cli.main(["test.kicad_pcb"]) == 0
    captured = capsys.readouterr()
    assert captured.out == f"{output}\n"
    assert len(captured.err.splitlines()) == 1
    assert "could not start file logging" in captured.err


def test_cli_help_does_not_create_a_log(log_path):
    with pytest.raises(SystemExit) as result:
        cli.main(["--help"])
    assert result.value.code == 0
    assert not log_path.exists()


def test_preview_logs_the_started_version_at_info(log_path, monkeypatch):
    # Run the plugin entry point with a disposable log and no live PCB Editor.
    version = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="ascii").strip()
    monkeypatch.setattr(app, "run_preview", lambda _: 0)
    assert app.main() == 0

    # The startup record identifies both the version and its log level.
    started = log_path.read_text(encoding="utf-8").splitlines()[0]
    assert "INFO kipng.app" in started
    assert started.endswith(f"Started KiPng {version}")
