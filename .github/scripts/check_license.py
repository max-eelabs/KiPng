# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check the GPL license and notices in KiPng's project-owned source files."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LICENSE_NOTICE = "SPDX-License-Identifier: GPL-3.0-or-later"
COPYRIGHT_NOTICE = re.compile(r"Copyright \(c\) [0-9]{4}(?:-[0-9]{4})? Maxim Pavlov")
SOURCE_PATTERNS = (
    "src/**/*.py",
    "src/**/*.qml",
    "plugin/**/*.py",
    "tests/**/*.py",
    ".github/**/*.py",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "*.ps1",
    "*.cmd",
)


def main() -> int:
    license_file = ROOT / "LICENSE"
    license_text = license_file.read_text(encoding="utf-8-sig") if license_file.is_file() else ""
    errors = []
    if not license_text.startswith("GNU GENERAL PUBLIC LICENSE\nVersion 3,") or (
        "END OF TERMS AND CONDITIONS" not in license_text
    ):
        errors.append("LICENSE: missing the GNU GPL version 3 text")

    sources = sorted({path for pattern in SOURCE_PATTERNS for path in ROOT.glob(pattern)})
    for path in sources:
        lines = path.read_text(encoding="utf-8-sig").splitlines()[:8]
        header = {re.sub(r"^(?:#|//|REM\b)\s*", "", line.strip(), flags=re.I) for line in lines}
        if LICENSE_NOTICE not in header or not any(
            COPYRIGHT_NOTICE.fullmatch(line) for line in header
        ):
            errors.append(f"{path.relative_to(ROOT).as_posix()}: missing the GPL notice")

    if errors:
        print("\n".join(errors))
        return 1

    print(f"Verified GPL notices in {len(sources)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
