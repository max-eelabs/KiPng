@echo off
REM Copyright (c) 2026 Maxim Pavlov
REM SPDX-License-Identifier: GPL-3.0-or-later
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
exit /b %errorlevel%
