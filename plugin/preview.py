# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""KiCad entrypoint, packaged alongside the runtime by the installer."""

from kipng.app import main

if __name__ == "__main__":
    raise SystemExit(main())
