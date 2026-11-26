# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import Mock

from PySide6.QtCore import QUrl

from kipng.contracts import PreviewError
from kipng.ui import file_menu
from kipng.ui.window import PreviewWindow
from test_window import wait_for


def test_open_log_from_preview_error_screen(app, monkeypatch, tmp_path):
    # Make the export fail and intercept calls to the desktop and warning dialog.
    log = tmp_path / "KiPng log.txt"
    log.touch()
    open_url = Mock(side_effect=(True, False))
    warning = Mock()
    monkeypatch.setattr(file_menu.QDesktopServices, "openUrl", open_url)
    monkeypatch.setattr(file_menu.QMessageBox, "warning", warning)
    export = Mock(side_effect=PreviewError("Board unavailable."))
    preview = PreviewWindow(tmp_path / "board.glb", export, log=log)
    preview.show()
    preview.start()
    try:
        # The error screen allows opening the log while render actions are unavailable.
        wait_for(lambda: preview.loading.error_details.isVisible())
        menu = preview.menu_bar
        assert menu.isVisible()
        assert menu.open_log_action.isEnabled()
        assert not menu.render_action.isEnabled()
        menu.open_log_action.trigger()
        open_url.assert_called_once_with(QUrl.fromLocalFile(str(log)))
        warning.assert_not_called()

        # If the desktop rejects the request, the warning includes the path.
        menu.open_log_action.trigger()
        assert str(log) in warning.call_args.args[2]
    finally:
        preview.close()
        preview.shutdown()


def test_open_log_is_disabled_when_logging_setup_failed(app, tmp_path):
    preview = PreviewWindow(tmp_path / "board.glb", Mock())
    try:
        assert not preview.menu_bar.open_log_action.isEnabled()
    finally:
        preview.close()
        preview.shutdown()
