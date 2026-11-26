# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
SOURCE = ROOT / "src"


def test_manifest_points_to_packaged_entrypoint_and_icons():
    # Read the manifest and check the toolbar action registration.
    manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["identifier"] == "org.kipng.preview"
    assert manifest["runtime"]["type"] == "python"
    action = manifest["actions"][0]
    assert action["show-button"] and action["scopes"] == ["pcb"]

    # Resolve the launcher and both theme icons relative to the manifest.
    for name in (action["entrypoint"], *action["icons-light"], *action["icons-dark"]):
        assert (PLUGIN / name).is_file()


def test_source_files_stay_within_250_lines():
    # Count project-owned source files, tests, and workflow definitions.
    source_files = [
        ROOT / "install.ps1",
        ROOT / "install.cmd",
        *PLUGIN.glob("*.py"),
        *SOURCE.rglob("*.py"),
        *SOURCE.rglob("*.qml"),
        *Path(__file__).parent.rglob("*.py"),
        *(ROOT / ".github/workflows").glob("*.yml"),
    ]

    # Report the path and line count of each file over the limit.
    too_long = {
        str(file.relative_to(ROOT)): count
        for file in source_files
        if (count := len(file.read_text(encoding="utf-8").splitlines())) > 250
    }
    assert not too_long


@pytest.mark.skipif(sys.platform != "win32", reason="The installer targets Windows.")
def test_install_and_upgrade_copy_runtime_without_private_files(tmp_path):
    # Give the installer a disposable KiCad documents directory.
    documents = tmp_path / "KiCad documents"
    env = {**os.environ, "KICAD_DOCUMENTS_HOME": str(documents)}
    target = documents / "KiCad/10.0/plugins/kipng"

    def run_installer():
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "install.cmd"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr

    # A fresh install copies exactly the source package and KiCad runtime assets.
    run_installer()
    expected = {
        Path("LICENSE"): ROOT / "LICENSE",
        **{file.relative_to(PLUGIN): file for file in PLUGIN.glob("*.*")},
        **{file.relative_to(SOURCE): file for file in SOURCE.rglob("*.py")},
        **{file.relative_to(SOURCE): file for file in SOURCE.rglob("*.qml")},
    }

    assert {file.relative_to(target) for file in target.rglob("*") if file.is_file()} == set(
        expected
    )

    for relative, file in expected.items():
        assert (target / relative).read_bytes() == file.read_bytes()

    # Simulate a previous launcher and a file added by the user.
    entrypoint = target / "preview.py"
    entrypoint.write_text("# old entrypoint\n", encoding="utf-8")
    user_file = target / "local.txt"
    user_file.touch()

    # An upgrade replaces the launcher and keeps the user's file.
    run_installer()
    assert entrypoint.read_bytes() == (PLUGIN / "preview.py").read_bytes()
    assert user_file.is_file()

    # Import from the installed package rather than the workspace or pytest path.
    launch_env = {key: value for key, value in env.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-B", "-c", "import preview; assert callable(preview.main)"],
        cwd=target,
        env=launch_env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
