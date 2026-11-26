# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Translate preview worker results into snapshots or messages for the window."""

import logging
from pathlib import Path
from queue import Queue
from threading import Event

from ..contracts import BoardSnapshot, ModelExporter, PreviewCancelled, PreviewError

LOGGER = logging.getLogger(__name__)


def prepare_preview_model(
    exporter: ModelExporter,
    model: Path,
    cancelled: Event,
    results: Queue[BoardSnapshot | str | None],
    reloading: bool,
) -> None:
    """Export off the Qt thread and enqueue the result for the window."""
    LOGGER.info("Exporting board for %s.", "reload" if reloading else "preview")
    try:
        snapshot = exporter(model, cancelled)
    except PreviewCancelled:
        LOGGER.info("Board export cancelled.")
        return
    except PreviewError as error:
        LOGGER.error("Board export failed: %s", error)
        results.put(str(error))
        return
    except Exception:
        LOGGER.exception("Board export failed unexpectedly.")
        results.put("An unexpected preview error occurred.")
        return

    if cancelled.is_set():
        LOGGER.info("Board export cancelled.")
        return
    LOGGER.info("Board export completed.")
    results.put(snapshot)
