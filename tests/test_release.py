# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import json
import subprocess
import sys
from zipfile import ZipFile

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="The release builder targets Windows.")
def test_release_metadata_matches_the_downloadable_zip(packaging_checkout):
    # Prepare stable metadata and define the public GitHub repository.
    metadata_path = packaging_checkout / "metadata.json"
    metadata = json.loads(metadata_path.read_bytes())
    (entry,) = metadata["versions"]
    entry.update(version="1.2.3", status="stable")
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    (packaging_checkout / "VERSION").write_text("1.2.3\n", encoding="ascii")
    repository_url = "https://github.com/example/KiPng"

    def build(tag):
        return subprocess.run(
            [
                sys.executable,
                ".github/scripts/build_release.py",
                "--tag",
                tag,
                "--repository-url",
                repository_url,
            ],
            cwd=packaging_checkout,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )

    # A mismatched tag is rejected before the builder writes files.
    rejected = build("v1.2.4")
    assert rejected.returncode == 2
    assert "Publishing requires tag v1.2.3" in rejected.stderr
    dist = packaging_checkout / "dist"
    assert not dist.exists()

    # A matching tag produces repository metadata for exactly the published ZIP.
    result = build("v1.2.3")
    assert result.returncode == 0, result.stdout + result.stderr
    package = dist / "KiPng-1.2.3.zip"
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    with ZipFile(package) as archive:
        assert json.loads(archive.read("metadata.json")) == metadata
        install_size = sum(member.file_size for member in archive.infolist())

    # The repository copy uses KiCad's v1 license label and adds the download fields.
    repository_metadata = json.loads((dist / "pcm-metadata.json").read_bytes())
    assert metadata["license"] == "GPL-3.0-or-later"
    assert repository_metadata["license"] == "GPL-3.0"
    (published,) = repository_metadata["versions"]
    assert published == {
        **entry,
        "download_url": f"{repository_url}/releases/download/v1.2.3/{package.name}",
        "download_sha256": digest,
        "download_size": package.stat().st_size,
        "install_size": install_size,
    }
    assert (dist / "checksums.txt").read_text(encoding="ascii") == f"{digest}  {package.name}\n"


@pytest.mark.skipif(sys.platform != "win32", reason="The release builder targets Windows.")
def test_snapshot_from_stable_metadata_is_an_installable_development_zip(packaging_checkout):
    # Simulate the release-preparation commit that just merged into main.
    metadata_path = packaging_checkout / "metadata.json"
    version_path = packaging_checkout / "VERSION"
    metadata = json.loads(metadata_path.read_bytes())
    (entry,) = metadata["versions"]
    entry.update(version="1.2.3", status="stable")
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    version_path.write_text("1.2.3\n", encoding="ascii")

    # The snapshot build produces a single PCM ZIP.
    result = subprocess.run(
        [sys.executable, ".github/scripts/build_release.py", "--snapshot"],
        cwd=packaging_checkout,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (package,) = (packaging_checkout / "dist").iterdir()
    assert package.name == "KiPng-1.2.3-SNAPSHOT.zip"

    # PCM and the plugin see a snapshot version while the checkout remains stable.
    with ZipFile(package) as archive:
        packaged_metadata = json.loads(archive.read("metadata.json"))
        assert packaged_metadata["versions"] == [{**entry, "status": "development"}]
        assert archive.read("plugins/VERSION") == b"1.2.3-SNAPSHOT\n"
        assert "plugins/plugin.json" in archive.namelist()
    assert json.loads(metadata_path.read_bytes()) == metadata
    assert version_path.read_text(encoding="ascii") == "1.2.3\n"
