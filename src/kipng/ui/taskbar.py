# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Publish the native Windows taskbar icon for each preview window handle."""

import ctypes as ct
import logging
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QWidget

APP_ID = "org.kipng.preview"
LOGGER = logging.getLogger(__name__)
PROPERTY_STORE_ID = UUID("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99").bytes_le
APP_MODEL_FORMAT = UUID("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3").bytes_le
ICON_RESOURCE = 3
WINDOW_APP_ID = 5
VT_LPWSTR = 31


class PropertyKey(ct.Structure):
    _fields_ = [("format_id", ct.c_ubyte * 16), ("property_id", ct.c_uint32)]


class PropertyValue(ct.Structure):
    # PROPVARIANT's union can hold a pointer and another word on 64-bit Windows.
    _fields_ = [
        ("type", ct.c_uint16),
        ("reserved", ct.c_uint16 * 3),
        ("text", ct.c_wchar_p),
        ("padding", ct.c_void_p),
    ]


def set_shell_icon(hwnd: int, icon: Path | None) -> None:
    """Set or clear the window's taskbar identity and icon resource."""
    store = ct.c_void_p()
    interface_id = (ct.c_ubyte * 16).from_buffer_copy(PROPERTY_STORE_ID)
    get_store = ct.windll.shell32.SHGetPropertyStoreForWindow
    result = get_store(ct.c_void_p(hwnd), ct.byref(interface_id), ct.byref(store))
    if result < 0:
        raise OSError(f"SHGetPropertyStoreForWindow failed ({result:#x})")

    methods = ct.cast(store, ct.POINTER(ct.POINTER(ct.c_void_p)))[0]
    release = ct.WINFUNCTYPE(ct.c_uint32, ct.c_void_p)(methods[2])
    set_value = ct.WINFUNCTYPE(
        ct.c_long, ct.c_void_p, ct.POINTER(PropertyKey), ct.POINTER(PropertyValue)
    )(methods[6])
    properties = (
        ((WINDOW_APP_ID, None), (ICON_RESOURCE, None))
        if icon is None
        else ((ICON_RESOURCE, f"{icon},0"), (WINDOW_APP_ID, APP_ID))
    )
    try:
        for property_id, text in properties:
            key = PropertyKey((ct.c_ubyte * 16).from_buffer_copy(APP_MODEL_FORMAT), property_id)
            value = PropertyValue(type=VT_LPWSTR if text is not None else 0, text=text)
            result = set_value(store, ct.byref(key), ct.byref(value))
            if result < 0:
                raise OSError(f"IPropertyStore::SetValue failed ({result:#x})")
    finally:
        release(store)


class TaskbarIcon(QObject):
    """Follow Qt's native handle through creation, recreation, and close."""

    def __init__(self, window: QWidget, icon: Path) -> None:
        super().__init__(window)
        self.icon = icon
        self.hwnd = 0
        window.installEventFilter(self)
        self.update_handle(int(window.effectiveWinId() or 0))

    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:
        if event.type() == QEvent.Type.WinIdChange:
            self.update_handle(int(watched.effectiveWinId() or 0))
        elif event.type() == QEvent.Type.Close:
            self.update_handle(0)
        return False

    def update_handle(self, hwnd: int) -> None:
        if hwnd == self.hwnd:
            return

        try:
            if self.hwnd and ct.windll.user32.IsWindow(ct.c_void_p(self.hwnd)):
                set_shell_icon(self.hwnd, None)
            self.hwnd = hwnd
            if hwnd:
                set_shell_icon(hwnd, self.icon)
        except OSError as error:
            LOGGER.warning("Could not update the KiPng taskbar icon: %s", error)
