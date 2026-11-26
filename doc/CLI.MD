# KiPng command-line reference

KiPng renders a saved KiCad PCB to one PNG without opening the PCB Editor.

## Run KiPng

Use KiCad 10.0 and a 64-bit Python 3.10–3.13 interpreter with the packages in [plugin/requirements.txt](../plugin/requirements.txt). From a source checkout, install the dependencies into your active Python environment if needed.

```text
python -m pip install -r plugin/requirements.txt
python plugin/render.py --help
python plugin/render.py BOARD.kicad_pcb [options]
```

Use `python3` if that's how you invoke your interpreter. For an installed plugin, run `python render.py` from the directory containing `plugin.json` or pass the absolute path to `render.py`. Quote any path containing spaces.

KiPng stages a temporary copy beside the saved PCB when possible. For read-only projects, it uses a temporary folder and resolves relative footprint model paths from the original project. Use `--output-dir` to save the PNG in a writable directory when the PCB's directory is read-only.

## Input and output

| Argument | Behavior |
| --- | --- |
| `BOARD.kicad_pcb` | Required path to the saved PCB. |
| `-h`, `--help` | Show usage, available options, and defaults, then exit. |
| `--output-dir PATH` | Save the PNG in this directory and create it if needed. Defaults to the PCB's directory. |
| `--kicad-cli PATH` | Prefer this KiCad 10.0 executable. KiPng also checks the standard Windows installation, when applicable, and `PATH`. |

On success, KiPng prints the full PNG path to stdout. It names the file `BOARD-render-WIDTHxHEIGHT.png`. If that name is already taken, it tries `BOARD-render-2-WIDTHxHEIGHT.png`, then increments the number until a name is available.

| Exit code | Meaning |
| --- | --- |
| `0` | Render saved or help displayed. |
| `1` | Render failed. Details go to stderr. |
| `2` | Invalid command-line arguments. |
| `130` | Render cancelled with Ctrl+C. |

## Render options

| Option | Accepted values | Default |
| --- | --- | --- |
| `--engine ENGINE` | `ray-tracing` uses KiCad's raytracer. `viewport` uses the Qt Quick 3D scene from the preview. | `ray-tracing` |
| `--color-scheme COLOR` | `green`, `red`, `white`, `black`, `blue`, `purple`, `yellow` | `green` |
| `--background BACKGROUND` | `white`, `transparent`, `warm-stone`, `mist-blue`, `sage-gray`, `dusty-rose`, `soft-slate`, or six RGB hex digits such as `E4DDD2`. | `white` |
| `--texture TEXTURE` | `none`, `fabric-grain`, `crinkled-paper` | `none` |
| `--resolution RESOLUTION` | `fhd`, `4k` | `fhd` |
| `--aspect-ratio RATIO` | `9:16`, `3:4`, `16:9`, `4:3`, `1:1` | `9:16` |
| `--light-x N` | Integer from `-100` to `100`. Increasing it moves the shadow left. | `0` |
| `--light-y N` | Integer from `-100` to `100`. Increasing it moves the shadow down. | `0` |
| `--shadow N` | Integer from `0` to `100`. At `0` the shadow is off, at `50` it is soft, and toward `100` it becomes sharper. | `50` |

A transparent background preserves the drop shadow and writes a PNG with an alpha channel. Textures apply only to opaque backgrounds other than pure white. If you include a leading `#` in a custom hex color, quote the value in the shell.

### Output dimensions

| Aspect ratio | FHD | 4K |
| --- | ---: | ---: |
| `9:16` | 1080 × 1920 | 2160 × 3840 |
| `3:4` | 1080 × 1440 | 2160 × 2880 |
| `16:9` | 1920 × 1080 | 3840 × 2160 |
| `4:3` | 1440 × 1080 | 2880 × 2160 |
| `1:1` | 1080 × 1080 | 2160 × 2160 |

## Camera options

Choose either `--view` or `--camera`. If you omit both, KiPng fits the `default-front` view.

| View preset | Framing |
| --- | --- |
| `--view default-front` | Angled view of the front, aligned to the board's long axis. |
| `--view default-back` | Angled view of the back, aligned to the board's long axis. |
| `--view straight-top` | View perpendicular to the front face. |
| `--view straight-bottom` | View perpendicular to the back face. |

Use `--camera=PITCH,YAW,DISTANCE,PAN_X,PAN_Y,BOARD_SPAN,FRAME_HALF_WIDTH` for an exact pose and crop. Use the `=` form so a negative pitch is parsed as part of the pose.

| Field | Meaning |
| --- | --- |
| `PITCH`, `YAW` | Orbit angles in degrees. |
| `DISTANCE` | Depth of the board center along the viewing axis, in GLB units. |
| `PAN_X`, `PAN_Y` | Camera-space pan offsets in GLB units. |
| `BOARD_SPAN` | Longest board-plane extent in GLB units. |
| `FRAME_HALF_WIDTH` | Half the horizontal width of the output crop at the board depth, in GLB units. |

All values must be finite. Distance, board span, and frame half-width must be positive. **File > Copy CLI** captures these values from the preview and appends `PIVOT_X,PIVOT_Y,PIVOT_Z` when the PCB body bounds are available. This optional vector gives the assembly center relative to the PCB center in GLB axes and metres. It aligns Ray Tracing with the preview for boards with tall or overhanging parts. Seven-value commands remain valid.

The Viewport engine always uses Qt Quick 3D and needs a working graphics session. Automatic camera fitting with `--view` also uses Qt Quick 3D. Ray tracing with an explicit `--camera` can run headless.

## Copy a command from the preview

In **3D Preview**, set the camera and render controls, then choose **File > Copy CLI**. The command captures the current angle, zoom, pan, crop, and render settings. Save any PCB edits in KiCad and reload the preview before copying to include those edits. Running the command reads the saved PCB again.

Paste into PowerShell on Windows or a POSIX-style shell such as Bash or Zsh on Linux and macOS. Keep the `| Write-Output` suffix on Windows so KiCad's Python environment can print the PNG path. To override the destination of a copied command, add `--output-dir PATH` before that suffix on Windows or at the end of the command on Linux and macOS.

## Examples

Render the default front view as a 1080 × 1920 PNG beside the PCB.

```text
python plugin/render.py board.kicad_pcb
```

Render a blue, straight-top view to a separate folder using a custom backdrop and fabric texture.

```text
python plugin/render.py board.kicad_pcb --output-dir renders --view straight-top --color-scheme blue --background E4DDD2 --texture fabric-grain --light-x -25 --shadow 65
```

Render a 3840 × 2160 Viewport image with transparency.

```text
python plugin/render.py board.kicad_pcb --engine viewport --aspect-ratio 16:9 --resolution 4k --background transparent
```
