# KiPng

<img src="plugin/kipng-logo.svg" alt="KiPng Kp logo" width="80" height="80">

KiPng adds a **3D Preview** button to the KiCad PCB Editor toolbar. It opens an interactive view of the current board, including unsaved edits, against a white background. Drag to orbit all the way around the board and inspect either side, hold Ctrl and drag to pan, and scroll to zoom. Choose **File > Reload Board** to pick up the latest edits without closing the preview. The File menu also lets you render, restore the default camera and render settings, or exit.

In the **Render** section, use **Color Scheme** to preview green, red, white, black, blue, purple, or yellow solder mask. The palette updates both board faces while keeping the current camera. The exported PNG uses the selected palette.

## Install on Windows, Linux, or macOS

> **KiCad API required.** In KiCad, open **Preferences → Plugins** and turn on
> **Enable KiCad API**. KiPng uses the IPC API to read the open board, including
> unsaved edits. The **3D Preview** action requires this setting to work.
> [KiCad 10.0 plugin preferences](https://docs.kicad.org/10.0/en/kicad/kicad.html#plugins-preferences)

1. Install KiCad 10.0 with its command-line tools and configure a 64-bit Python 3.10–3.13 interpreter in **Preferences → Plugins**. KiCad installs the dependencies listed in the plugin's `requirements.txt`.
2. Download a KiPng build. Each ZIP supports Windows, Linux, and macOS.

   - **Stable release**. Choose the `KiPng-<version>.zip` asset. [Latest stable release](https://github.com/max-eelabs/KiPng/releases/latest)
   - **Development snapshot**. GitHub refreshes this ZIP after each push to `main`. [Download KiPng-SNAPSHOT.zip](https://github.com/max-eelabs/KiPng/releases/download/snapshot/KiPng-SNAPSHOT.zip)

3. In KiCad Project Manager, open **Plugin and Content Manager**, choose **Install from File**, and select the downloaded ZIP directly. KiPng appears under **Installed**.
4. Restart KiCad and open a PCB. Click **3D Preview** on the PCB Editor toolbar once KiCad finishes setting up the plugin environment. If you use a custom toolbar, add the action in the PCB Editor's toolbar preferences.

The plugin looks for the CLI in the running editor's installation, the standard Windows or macOS installation when applicable, and then `PATH`. It exports a temporary GLB for the interactive view using the default assembly variant. KiPng stages a snapshot beside the board when possible. For read-only projects, it stages the snapshot in a temporary folder and resolves relative footprint model paths from the original project.

When the GLB includes a VRML footprint model, KiPng can recover source transparency for the live preview and Viewport PNGs. This works when the footprint has one readable VRML model and each affected GLB material color identifies a single opacity in that model.

In **Render**, choose **Viewport** for the Qt 3D preview's appearance or **Ray Tracing** for KiCad's raytraced lighting. Both engines use the selected color scheme, camera, aspect ratio, and resolution to produce one PNG. The default is Viewport at FHD in 9:16 (1080 × 1920). You can also choose 3:4, 16:9, 4:3, or 1:1. 4K doubles both pixel dimensions for the selected ratio.

Choose **Background** to change the backdrop in the preview and exported PNG. Use White, one of the muted presets, or **Custom** with a six-digit RGB hex color. On opaque colors other than pure white, set **Texture** to None, Fabric Grain, or Crinkled Paper. **Transparent** displays a checkerboard in the preview and saves a PNG with transparency and a soft shadow.

Drag **Light X** and **Light Y** to move the shadow. All three sliders start centered. Drag **Shadow** left to fade it out or right to sharpen it. The controls apply to the live preview and both PNG engines.

In the **Viewport** section, turn on **Show Render Frame** to see gray corner marks and a circled crosshair for the PNG crop. Frame the part of the board you want to show, then click **Render** and choose a folder. Both engines crop the PNG to the frame, so the board can extend past the edges. The PNG uses the current camera angle, zoom, pan, and background with a soft shadow.

## Render from the command line

Use the CLI to export a PNG from a saved PCB without opening the editor. With KiCad 10.0 and the Python dependencies installed, run this from the source checkout.

```text
python plugin/render.py board.kicad_pcb --output-dir renders
```

Choose **File > Copy CLI** in the preview to reproduce its current framing and render settings. See the [CLI reference](doc/CLI.MD) for installation paths, options, defaults, and examples.

## Logging

Choose **File > Open Log** to open KiPng's current log in your default text editor. The preview and CLI share `%LOCALAPPDATA%\KiPng\logs\kipng.txt` on Windows. KiPng rotates the log at about 10 MiB and keeps nine backups, deleting the oldest on each rollover.

If your text editor holds the file open with a lock that prevents renaming on Windows, KiPng keeps appending and retries rotation on the next write. Close the log tab to release the lock.

The default level is `INFO`. To enable `DEBUG` for the preview, close KiCad and launch it from PowerShell with the environment variable set. The CLI also reads `KIPNG_LOG_LEVEL` and accepts a per-run `--log-level` override.

```powershell
$env:KIPNG_LOG_LEVEL = 'DEBUG'
& "$env:ProgramFiles\KiCad\10.0\bin\kicad.exe"
```

If an existing plugin environment is missing the logging dependency after an upgrade, right-click the **3D Preview** action in the PCB Editor's plugin preferences and select **Recreate Plugin Environment**. [KiCad IPC plugin debugging](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/#debugging)

## Project structure

| Path | Purpose |
| --- | --- |
| `plugin/` | KiCad manifest, toolbar entrypoint, icons, and runtime dependencies. |
| `src/kipng/app.py` | Application entrypoint that assembles and launches the preview. |
| `src/kipng/cli.py` | Command-line rendering of saved PCBs. |
| `src/kipng/contracts/` | Shared data, interfaces, and preview errors. |
| `src/kipng/export/` | Board capture, CLI export, and GLB preview materials. |
| `src/kipng/ui/window.py` | Window layout and loading state. |
| `src/kipng/ui/viewport/` | Left pane, QML scene, camera interaction, and overlays. |
| `src/kipng/ui/controls/` | Right pane, control sections, and the Render footer. |
| `tests/` | Export, material, UI, installation, and source-length checks. |
| `.github/workflows/ci.yml` | Python 3.10 CI on Windows, Linux, and macOS. |

The exporter accepts a `BoardSource` for supplying board snapshots. The window accepts a `ModelExporter` and receives model readiness and errors from the viewport through Qt signals.

Both installation modes place the `kipng` runtime package beside `plugin.json`. This keeps KiCad's deployment layout out of the source tree.

### Extend the preview

- Add a QML component to [`src/kipng/ui/viewport/qml/features/`](src/kipng/ui/viewport/qml/features/README.md) to overlay controls or information on the 3D viewport.
- Add a Python module to `src/kipng/ui/controls/sections/` that defines `create_section(get_viewport)` and returns a `QWidget`. The panel loads sections in filename order above Render. `get_viewport()` returns the current `BoardViewport` once it has been created, so call it when handling input. Filenames starting with `_` are reserved for helpers.
- Define image-affecting settings in `src/kipng/contracts/options.py` so the controls, CLI, and copied command use the same option definitions.

## Development and testing

See the [release guide](RELEASE.MD) for snapshot builds, tagged releases, and KiCad PCM submission.

From a Windows checkout, run `.\install.cmd` to build a PCM ZIP in `dist/`.
For direct development installs, run `.\install.cmd -Local`. It updates the
user plugin directory and respects `KICAD_DOCUMENTS_HOME`. Use one
installation mode at a time.

From the repository root, in an activated virtual environment, run:

```powershell
python -m pip install --only-binary=:all: -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

The suite uses temporary files, substitutes the KiCad editor and model exporter where needed, and checks the Qt window offscreen. GitHub Actions checks the CLI entrypoint and runs the suite on Windows, Linux, and macOS with Python 3.10 on pushes and pull requests. On Windows the installation tests build the PCM ZIP and verify a direct install in a temporary KiCad documents directory. Source files are limited to 250 lines.

For a desktop smoke check, install the plugin into KiCad 10.0 and open **3D Preview** on an edited board. Check the loading transition, the board finish, orbit, pan, and zoom. Click **Render** and check the camera angle and framing in the PNG.

## License

KiPng is licensed under the [GNU General Public License v3.0 or later](LICENSE).
Copyright (c) 2026 Maxim Pavlov.
