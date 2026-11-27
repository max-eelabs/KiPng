# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build a Windows PCM package and generate the metadata for a tagged release."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
VERSION = re.compile(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,6}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Git tag for a stable release. Omit for a snapshot.")
    parser.add_argument(
        "--snapshot", action="store_true", help="Allow a snapshot of a release-preparation commit."
    )
    parser.add_argument("--repository-url", help="Public GitHub repository URL for the tag.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    if bool(args.tag) != bool(args.repository_url):
        parser.error("--tag and --repository-url must be used together.")
    if args.snapshot and args.tag:
        parser.error("--snapshot and --tag cannot be used together.")

    metadata = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    if len(metadata["versions"]) != 1:
        parser.error("metadata.json must declare exactly one version.")

    (entry,) = metadata["versions"]
    version = entry["version"]
    if not VERSION.fullmatch(version):
        parser.error("metadata.json must use a numeric major.minor.patch version.")
    if any(key.startswith("download_") or key == "install_size" for key in entry):
        parser.error("Put download and install fields in PCM repository metadata only.")
    if args.tag and (args.tag != f"v{version}" or entry["status"] != "stable"):
        parser.error(f"Publishing requires tag v{version} and status stable in metadata.json.")
    snapshot_statuses = {"development", "stable"} if args.snapshot else {"development"}
    if not args.tag and entry["status"] not in snapshot_statuses:
        parser.error("A snapshot requires status development in metadata.json.")

    project_version = version if args.tag else f"{version}-SNAPSHOT"
    package = args.output_dir.resolve() / f"KiPng-{project_version}.zip"
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "install.ps1"),
            "-OutputPath",
            str(package),
            *(["-Snapshot"] if args.snapshot else []),
        ],
        cwd=ROOT,
        check=True,
    )
    if args.snapshot:
        entry["status"] = "development"
    with ZipFile(package) as archive:
        if archive.testzip() is not None or json.loads(archive.read("metadata.json")) != metadata:
            raise SystemExit("The generated ZIP failed validation or its metadata changed.")
        if archive.read("plugins/VERSION").decode("ascii").strip() != project_version:
            raise SystemExit("The generated ZIP contains an unexpected VERSION.")
        # KiCad's repository validator counts every archive member, including metadata.json.
        install_size = sum(member.file_size for member in archive.infolist())

    if not args.tag:
        return

    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    repository_url = args.repository_url.rstrip("/")
    entry.update(
        download_url=f"{repository_url}/releases/download/{args.tag}/{package.name}",
        download_sha256=digest,
        download_size=package.stat().st_size,
        install_size=install_size,
    )
    # KiCad also validates plugin listings against its v1 license enum.
    if metadata["license"] == "GPL-3.0-or-later":
        metadata["license"] = "GPL-3.0"
    (package.parent / "pcm-metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (package.parent / "checksums.txt").write_text(f"{digest}  {package.name}\n", encoding="ascii")


if __name__ == "__main__":
    main()
