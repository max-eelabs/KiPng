# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
SOURCE = ROOT / "src"


def installed_files(root=ROOT):
    plugin = root / "plugin"
    source = root / "src"
    return {
        Path("LICENSE"): root / "LICENSE",
        Path("VERSION"): root / "VERSION",
        **{file.relative_to(plugin): file for file in plugin.glob("*.*")},
        **{file.relative_to(source): file for file in source.rglob("*.py")},
        **{file.relative_to(source): file for file in source.rglob("*.qml")},
    }


def run_installer(env, *args, cwd=ROOT):
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "install.cmd", *args],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_manifest_points_to_packaged_entrypoint_and_icons():
    # Read the manifest and check the toolbar action registration.
    manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["identifier"] == "com.max-eelabs.kipng.preview"
    assert manifest["runtime"]["type"] == "python"
    action = manifest["actions"][0]
    assert action["show-button"] and action["scopes"] == ["pcb"]

    # Resolve the launcher and both theme icons relative to the manifest.
    assert (PLUGIN / action["entrypoint"]).is_file()
    for name in (*action["icons-light"], *action["icons-dark"]):
        with Image.open(PLUGIN / name) as icon:
            assert (icon.format, icon.size, icon.mode) == ("PNG", (24, 24), "RGBA")
    assert (PLUGIN / "icon-light.png").read_bytes() == (PLUGIN / "icon-dark.png").read_bytes()

    # Windows can choose a matching bitmap for its current taskbar scale.
    with Image.open(PLUGIN / "kipng-logo.ico") as icon:
        assert {(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)} <= icon.ico.sizes()


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
def test_default_install_builds_pcm_archive(tmp_path, packaging_checkout):
    # Set a version distinct from the source metadata's current version.
    checkout = packaging_checkout
    metadata = json.loads((checkout / "metadata.json").read_bytes())
    metadata["versions"][0]["version"] = "2.3.456"
    (checkout / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (checkout / "VERSION").write_text("2.3.456-SNAPSHOT\n", encoding="ascii")

    # Build a versioned ZIP by default and replace a ZIP at an explicit path.
    documents = tmp_path / "KiCad documents"
    env = {**os.environ, "KICAD_DOCUMENTS_HOME": str(documents)}
    output = run_installer(env, cwd=checkout)
    assert "Install from File" in output
    assert not documents.exists()
    (package,) = (checkout / "dist").iterdir()
    custom_package = tmp_path / "Custom package.zip"
    custom_package.write_bytes(b"previous build")
    run_installer(env, "-OutputPath", str(custom_package), cwd=checkout)
    with ZipFile(custom_package) as archive:
        assert archive.testzip() is None

    # PCM discovers the package metadata and the editor finds the IPC manifest.
    with ZipFile(package) as archive:
        metadata = json.loads(archive.read("metadata.json"))
        manifest = json.loads(archive.read("plugins/plugin.json"))
        assert metadata["identifier"] == manifest["identifier"]
        assert metadata["type"] == "plugin"
        assert metadata["author"]["contact"]["email"] == "max.eelabs@gmail.com"
        (version,) = metadata["versions"]
        assert package.name == f"KiPng-{version['version']}-SNAPSHOT.zip"
        assert version["runtime"] == "ipc"
        assert version["kicad_version"] == "10.0"
        assert set(version["platforms"]) == {"windows", "linux", "macos"}
        assert not any(key.startswith("download_") for key in version)

        # The ZIP includes a PCM listing icon and the same runtime as a direct install.
        with Image.open(BytesIO(archive.read("resources/icon.png"))) as icon:
            assert (icon.format, icon.size, icon.mode) == ("PNG", (64, 64), "RGBA")
        expected = {
            f"plugins/{relative.as_posix()}": file
            for relative, file in installed_files(checkout).items()
        }
        assert sorted(archive.namelist()) == sorted(
            ["metadata.json", "resources/icon.png", *expected]
        )
        for entry, file in expected.items():
            assert archive.read(entry) == file.read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="The installer targets Windows.")
def test_install_and_upgrade_copy_runtime_without_private_files(tmp_path):
    # Give the installer a disposable KiCad documents directory.
    documents = tmp_path / "KiCad documents"
    env = {**os.environ, "KICAD_DOCUMENTS_HOME": str(documents)}
    target = documents / "KiCad/10.0/plugins/kipng"

    # A fresh install copies exactly the source package and KiCad runtime assets.
    run_installer(env, "-Local")
    expected = installed_files()

    assert {file.relative_to(target) for file in target.rglob("*") if file.is_file()} == set(
        expected
    )

    for relative, file in expected.items():
        assert (target / relative).read_bytes() == file.read_bytes()

    # Simulate an older direct install and a file added by the user.
    entrypoint = target / "preview.py"
    entrypoint.write_text("# old entrypoint\n", encoding="utf-8")
    manifest_path = target / "plugin.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["identifier"] = "org.kipng.preview"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    user_file = target / "local.txt"
    user_file.touch()

    # An upgrade replaces the launcher and keeps the user's file.
    run_installer(env, "-Local")
    assert entrypoint.read_bytes() == (PLUGIN / "preview.py").read_bytes()
    assert manifest_path.read_bytes() == (PLUGIN / "plugin.json").read_bytes()
    assert user_file.is_file()

    # Import from the installed package rather than the workspace or pytest path.
    launch_env = {key: value for key, value in env.items() if key != "PYTHONPATH"}
    launch_env["QT_QPA_PLATFORM"] = "offscreen"
    verify_application = """
from pathlib import Path

import preview
from kipng.app import create_application, project_version
from PySide6.QtWidgets import QDialog, QWidget

assert callable(preview.main)
assert project_version() == Path("VERSION").read_text(encoding="ascii").strip()
app = create_application()
window = QWidget()
dialog = QDialog(window)
for widget in (window, dialog):
    icon = widget.windowIcon()
    assert icon.cacheKey() == app.windowIcon().cacheKey()
    assert not icon.pixmap(48, 48).isNull()
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", verify_application],
        cwd=target,
        env=launch_env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr

    # Invoke the installed CLI by its absolute path from another directory.
    cli_help = subprocess.run(
        [sys.executable, "-B", str(target / "render.py"), "--help"],
        cwd=tmp_path,
        env=launch_env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert cli_help.returncode == 0, cli_help.stderr
    assert "BOARD.kicad_pcb" in cli_help.stdout and "--camera" in cli_help.stdout
