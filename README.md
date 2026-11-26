# KiPng

KiPng adds a **3D Preview** button to the KiCad PCB Editor toolbar. It opens an interactive view of the current board, including unsaved edits, against a white background. Drag to orbit all the way around the board and inspect either side, hold Ctrl and drag to pan, and scroll to zoom. Close the window and click the button again to pick up the latest edits.

In the **Viewport** panel, use **Color Scheme** to preview green, red, white, black, blue, purple, or yellow solder mask. The palette updates both board faces while keeping the current camera. **Render** uses the selected palette in the exported PNG.

## Install locally on Windows

1. Install KiCad 10.0 with its command-line tools and configure a 64-bit Python 3.10–3.13 interpreter in **Preferences → Plugins**. KiCad installs the dependencies listed in the plugin's `requirements.txt`.
2. Run the install command from the workspace root. It installs or updates the plugin in your KiCad 10.0 user plugin directory and respects `KICAD_DOCUMENTS_HOME`.

   ```powershell
   .\install.cmd
   ```

3. Enable **Enable KiCad API** in **Preferences → Plugins**, restart KiCad, and open a PCB. Click **3D Preview** on the PCB Editor toolbar once KiCad finishes setting up the plugin environment. If you use a custom toolbar, add the action in the PCB Editor's toolbar preferences.

The plugin looks for the CLI in the running editor's installation, the default Windows installation, and then `PATH`. It exports a temporary GLB for the interactive view using the default assembly variant. The project directory must be writable so the plugin can briefly save a snapshot beside the original board and retain relative model paths. VRML-only footprint models require a matching STEP or IGES file to appear in the GLB.

Click **Render** in the lower-right corner and choose a folder to save a 1080 × 1920 portrait PNG. The render uses the current camera angle, zoom, and pan on the board shown in the preview. KiCad raytraces the board, then the plugin composites it on white with a soft shadow. If the board extends past the portrait frame, zoom out or pan toward the center and render again.

## Project structure

| Path | Purpose |
| --- | --- |
| `plugin/` | KiCad manifest, toolbar entrypoint, icons, and runtime dependencies. |
| `src/kipng/app.py` | Application entrypoint that assembles and launches the preview. |
| `src/kipng/contracts/` | Shared data, interfaces, and preview errors. |
| `src/kipng/export/` | Board capture, CLI export, and GLB preview materials. |
| `src/kipng/ui/window.py` | Window layout and loading state. |
| `src/kipng/ui/viewport/` | Left pane, QML scene, camera interaction, and overlays. |
| `src/kipng/ui/controls/` | Right pane, control sections, and the Render footer. |
| `tests/` | Export, material, UI, installation, and source-length checks. |
| `.github/workflows/ci.yml` | Windows CI for the supported Python range. |

The exporter accepts a `BoardSource` for supplying board snapshots. The window accepts a `ModelExporter` and receives model readiness and errors from the viewport through Qt signals.

The installer places the contents of `plugin/` and the `kipng` package together in KiCad's user plugin directory. This keeps KiCad's deployment layout out of the source tree.

### Extend the preview

- Add a QML component to [`src/kipng/ui/viewport/qml/features/`](src/kipng/ui/viewport/qml/features/README.md) to overlay controls or information on the 3D viewport.
- Add a Python module to `src/kipng/ui/controls/sections/` that defines `create_section(get_viewport)` and returns a `QWidget`. The panel loads sections in filename order above Render. `get_viewport()` returns the current `BoardViewport` once it has been created, so call it when handling input. Filenames starting with `_` are reserved for helpers.

## Development and testing

From the repository root, in an activated virtual environment, run:

```powershell
python -m pip install --only-binary=:all: -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

The suite uses temporary files, substitutes the KiCad editor and model exporter where needed, and checks the Qt window offscreen. The Windows installer test uses a temporary KiCad documents directory. GitHub Actions runs these checks on pushes and pull requests. Source files are limited to 250 lines.

For a desktop smoke check, install the plugin into KiCad 10.0 and open **3D Preview** on an edited board. Check the loading transition, the board finish, orbit, pan, and zoom. Click **Render** and check the camera angle and framing in the PNG.

## License

KiPng is licensed under the [GNU General Public License v3.0 or later](LICENSE).
Copyright (c) 2026 Maxim Pavlov.
