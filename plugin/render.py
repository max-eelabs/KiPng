# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run the KiPng CLI from an installed plugin or a source checkout."""

import sys
from pathlib import Path

if __name__ == "__main__":
    directory = Path(__file__).resolve().parent
    if not (directory / "kipng").is_dir():
        sys.path.insert(0, str(directory.parent / "src"))
    from kipng.cli import main

    raise SystemExit(main())
