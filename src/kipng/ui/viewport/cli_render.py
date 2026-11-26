# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Own the render-only Qt event loop and temporary model for CLI use."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from ...contracts import BoardSnapshot, PcbGeometry, PreviewCancelled, PreviewError
from ...contracts.options import RenderOptions
from ...export.exporter import export_snapshot_model
from .render import RenderSurface


@contextmanager
def open_render_surface(
    snapshot: BoardSnapshot, settings: RenderOptions, cancelled: Event
) -> Iterator[tuple[RenderSurface, PcbGeometry | None]]:
    app = QApplication.instance() or QApplication(["KiPng"])
    with TemporaryDirectory(prefix="kipng-cli-") as directory:
        model = Path(directory) / "board.glb"
        geometry = export_snapshot_model(snapshot, model, cancelled)
        surface = RenderSurface(
            model, settings.palette, settings.output_size, shadow=settings.lighting
        )
        try:
            wait_for_model(surface, cancelled)
            yield surface, geometry
        finally:
            surface.release()
            app.processEvents()


def wait_for_model(surface: RenderSurface, cancelled: Event) -> None:
    loop = QEventLoop()
    finished = False
    failure = None

    def finish(message: str | None = None) -> None:
        nonlocal finished, failure
        if finished:
            return
        finished = True
        failure = message
        loop.quit()

    def check_cancelled() -> None:
        if cancelled.is_set():
            finish()

    timer = QTimer(loop, interval=100)
    timer.timeout.connect(check_cancelled)
    surface.loaded.connect(finish)
    surface.failed.connect(finish)
    surface.start()
    if not finished and not cancelled.is_set():
        timer.start()
        loop.exec()
    timer.stop()
    surface.loaded.disconnect(finish)
    surface.failed.disconnect(finish)
    if cancelled.is_set():
        raise PreviewCancelled
    if failure is not None:
        raise PreviewError(failure)
    if not finished:
        raise PreviewError("The viewport closed before loading the 3D model.")
