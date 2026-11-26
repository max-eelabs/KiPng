# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Locate a KiCad 10.0 CLI and run commands with cancellation and time limits."""

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from threading import Event
from time import monotonic

from ..contracts import PreviewCancelled, PreviewError

LOGGER = logging.getLogger(__name__)


def run_cli(
    args: list[str], cancelled: Event, timeout: int, *, env: dict[str, str] | None = None
) -> str:
    if cancelled.is_set():
        raise PreviewCancelled

    LOGGER.debug("Starting subprocess %s with a %d-second timeout.", args[0], timeout)
    startup_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=startup_flags,
        env=env,
    ) as process:
        deadline = monotonic() + timeout
        try:
            while True:
                if cancelled.is_set():
                    raise PreviewCancelled
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise PreviewError(f"KiCad CLI timed out after {timeout} seconds.")
                try:
                    stdout, stderr = process.communicate(timeout=min(remaining, 0.2))
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    output = stdout.decode("utf-8", errors="replace").strip()
    errors = stderr.decode("utf-8", errors="replace").strip()
    LOGGER.debug("KiCad CLI exited with code %d.", process.returncode)
    if process.returncode:
        details = (errors or output or f"Exit code {process.returncode}.")[-2000:]
        raise PreviewError(f"KiCad CLI could not complete the command.\n\n{details}")
    return output


def find_cli(preferred: str | None, cancelled: Event) -> Path:
    candidates = [preferred]
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(str(Path(program_files) / "KiCad/10.0/bin/kicad-cli.exe"))
    candidates.append(shutil.which("kicad-cli"))

    failures = []
    for candidate in dict.fromkeys(candidates):
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            version = run_cli([candidate, "version"], cancelled, 10)
        except (OSError, PreviewError) as error:
            failures.append(f"{candidate}\n{error}")
            continue
        if re.search(r"(?m)^10\.0\.\d+\b", version):
            return Path(candidate)
        failures.append(f"{candidate} reported {version or 'no version'}.")

    details = "\n\n" + "\n".join(failures) if failures else ""
    raise PreviewError(
        "KiCad 10.0 CLI was not found. Install KiCad 10.0 or add its bin folder to PATH." + details
    )
