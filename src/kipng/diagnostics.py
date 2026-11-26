# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Configure KiPng's process-local logging and shared rotating log file."""

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVEL_ENV = "KIPNG_LOG_LEVEL"
MAX_LOG_BYTES = 10 * 1024 * 1024
LOG_BACKUPS = 9
LOGGER = logging.getLogger("kipng")


def log_path() -> Path:
    """Use the same per-user location for the preview and CLI."""
    from PySide6.QtCore import QStandardPaths

    directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    if not directory:
        raise OSError("Could not locate the user data directory.")
    return Path(directory) / "KiPng" / "logs" / "kipng.txt"


def file_handler(path: Path) -> logging.Handler:
    from concurrent_log_handler import ConcurrentRotatingFileHandler

    path.parent.mkdir(parents=True, exist_ok=True)
    # Open Log should work even when the configured level filters out startup messages.
    with path.open("a", encoding="utf-8"):
        pass
    handler = ConcurrentRotatingFileHandler(
        str(path),
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUPS,
        encoding="utf-8",
        unicode_error_policy="replace",
        keep_file_open=False,
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(process)d/%(threadName)s] %(message)s"
        )
    )
    return handler


@contextmanager
def qt_diagnostics() -> Iterator[None]:
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }
    logger = LOGGER.getChild("qt")

    def log_message(kind, context, message):
        logger.log(levels[kind], "[%s] %s", context.category or "default", message)

    previous = qInstallMessageHandler(log_message)
    try:
        yield
    finally:
        qInstallMessageHandler(previous)


@contextmanager
def configure_logging(override: str | None = None) -> Iterator[Path | None]:
    """Route KiPng and Qt records for one entry-point run, then restore their settings."""
    raw_level = os.environ.get(LOG_LEVEL_ENV, DEFAULT_LOG_LEVEL) if override is None else override
    level = raw_level.strip().upper()
    invalid_level = level not in LOG_LEVELS
    if invalid_level:
        level = DEFAULT_LOG_LEVEL

    path = None
    try:
        destination = log_path()
        handler = file_handler(destination)
        path = destination
    except (ImportError, OSError) as error:
        print(f"KiPng: could not start file logging: {error}", file=sys.stderr)
        handler = logging.NullHandler()

    previous_level, previous_propagate = LOGGER.level, LOGGER.propagate
    LOGGER.setLevel(level)
    LOGGER.propagate = False
    LOGGER.addHandler(handler)
    try:
        if invalid_level:
            LOGGER.warning("Invalid %s value %r. Using %s.", LOG_LEVEL_ENV, raw_level, level)
        if path is None:
            yield None
            return
        with qt_diagnostics():
            yield path
    finally:
        LOGGER.removeHandler(handler)
        handler.close()
        LOGGER.setLevel(previous_level)
        LOGGER.propagate = previous_propagate
