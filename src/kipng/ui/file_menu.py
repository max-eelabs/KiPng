# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""File menu actions and always-visible keyboard mnemonics."""

from collections.abc import Callable

from PySide6.QtWidgets import QMenuBar, QProxyStyle, QStyle, QWidget


class MnemonicStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, return_data=None) -> int:
        if hint == QStyle.StyleHint.SH_UnderlineShortcut:
            return 1
        return super().styleHint(hint, option, widget, return_data)


class FileMenuBar(QMenuBar):
    def __init__(
        self,
        parent: QWidget,
        render: Callable[[], None],
        copy_cli: Callable[[], None],
        reload_board: Callable[[], None],
        reset: Callable[[], None],
        close: Callable[[], bool],
    ) -> None:
        super().__init__(parent)
        self.setNativeMenuBar(False)
        self.mnemonic_style = MnemonicStyle()
        self.mnemonic_style.setParent(self)
        self.setStyle(self.mnemonic_style)

        self.file_menu = self.addMenu("&File")
        self.file_menu.setStyle(self.mnemonic_style)
        self.render_action = self.file_menu.addAction("&Render", render)
        self.copy_cli_action = self.file_menu.addAction("&Copy CLI", copy_cli)
        self.reload_action = self.file_menu.addAction("Re&load Board", reload_board)
        self.reset_action = self.file_menu.addAction("Reset to &Default", reset)
        self.file_menu.addSeparator()
        self.file_menu.addAction("E&xit", close)

    def set_availability(self, ready: bool, has_snapshot: bool, has_renderer: bool) -> None:
        self.render_action.setEnabled(ready and has_snapshot and has_renderer)
        self.copy_cli_action.setEnabled(ready and has_snapshot)
        self.reload_action.setEnabled(ready)
        self.reset_action.setEnabled(ready)
