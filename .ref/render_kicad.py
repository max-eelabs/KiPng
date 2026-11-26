#!/usr/bin/env python3
"""Render both sides of a KiCad PCB as 1080 x 1920 and 2160 x 3840 PNGs.

Usage: python3 render_kicad.py BOARD.kicad_pcb [--config views.json]
Requires Python 3.10+, Pillow (python -m pip install Pillow), and KiCad 10.0
with the board's 3D models. Tested with KiCad 10.0.7 and Pillow 12.2.0.
PNGs are named after the board and saved beside this script by default.

Example views.json (rotations are [X, Y, Z] in degrees):
    {"front": {"rotation": [-25, 0, -65], "zoom": 0.5},
     "back": {"rotation": [-15, 0, -65]}}

Each view can also override key_light (0 to 1), shadow_scale ([X, Y]
multipliers), shadow_offset ([X, Y] pixels), and shadow_blur (pixels).
Shadow distances are measured at 1080 x 1920. The soft shadow is projected
from the board silhouette. Keep KiCad, Pillow, and the board and its 3D
models fixed when comparing output hashes. Different KiCad builds or OSes
can render pixels differently.

On Linux and WSL, use native Linux Python and KiCad. WSL can read files
on Windows drives using paths such as /mnt/c/Users/me/board.kicad_pcb.
Use --kicad-cli for a custom installation or executable wrapper and
--models-dir to override the standard 3D model directory.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import subprocess
import tempfile

try:
    from PIL import Image, ImageChops, ImageFilter
except ImportError:
    raise SystemExit('Install Pillow with: python -m pip install Pillow') from None


# Image dimensions and default view settings.
OUTPUT_SIZES = ((1080, 1920), (2160, 3840))
MASTER_SIZE = OUTPUT_SIZES[-1]

# Render with extra room around the frame for the board and its shadow.
CANVAS_SIZE = (2304, 3968)
SCALE = MASTER_SIZE[0] // OUTPUT_SIZES[0][0]
DEFAULT_ROTATIONS = {'front': [-25, 0, -65], 'back': [-15, 0, -65]}

# Each rule is (number of array elements, lower limit, upper limit). Zero means scalar.
VIEW_RULES = {
    'rotation': (3, -360000, 360000),
    'zoom': (0, 0.01, 10),
    'key_light': (0, 0, 1),
    'shadow_scale': (2, 0.1, 4),
    'shadow_offset': (2, -500, 500),
    'shadow_blur': (0, 0, 100),
}
DEFAULT_VIEW = {
    'zoom': 0.5,
    'key_light': 0.20,
    'shadow_scale': [1.08, 1.08],
    'shadow_offset': [3, 20],
    'shadow_blur': 8,
}

# Isolate KiCad from the user profile and disable randomized post-processing.
RENDER_SETTINGS = {
    'material_mode': 0,
    'raytrace_anti_aliasing': True,
    'raytrace_backfloor': False,
    'raytrace_post_processing': False,
    'raytrace_procedural_textures': False,
    'raytrace_shadows': True,
    'raytrace_reflections': True,
    'raytrace_refractions': True,
    'raytrace_nrsamples_shadows': 1,
    'raytrace_nrsamples_reflections': 1,
    'raytrace_nrsamples_refractions': 1,
    'raytrace_spread_shadows': 0.0,
    'raytrace_spread_reflections': 0.0,
    'raytrace_spread_refractions': 0.0,
}


# View configuration
def load_views(path):
    """Merge validated per-view JSON overrides with the built-in defaults."""
    config = json.loads(path.read_text(encoding='utf-8-sig')) if path else {}
    if not isinstance(config, dict) or set(config) - DEFAULT_ROTATIONS.keys():
        raise ValueError('Config must be a JSON object with optional front and back keys.')
    views = {}
    for name, rotation in DEFAULT_ROTATIONS.items():
        overrides = config.get(name, {})
        if not isinstance(overrides, dict) or set(overrides) - VIEW_RULES.keys():
            raise ValueError(f'{name} must be an object containing only documented view settings.')
        view = {**DEFAULT_VIEW, 'rotation': rotation, **overrides}
        for key, (count, lower, upper) in VIEW_RULES.items():
            values = view[key] if count else [view[key]]
            if not isinstance(values, list) or len(values) != (count or 1) or any(
                type(value) not in (int, float) or not lower <= value <= upper for value in values
            ):
                shape = f'an array of {count} numbers' if count else 'a number'
                raise ValueError(f'{name}.{key} must be {shape} between {lower} and {upper}.')
        views[name] = view
    return views


# KiCad discovery and rendering
def find_cli(override):
    """Prefer an explicit executable, then PATH, then platform install paths."""
    if override is not None:
        cli = shutil.which(str(override.absolute()))
    else:
        cli = shutil.which('kicad-cli')
        if cli is None and sys.platform == 'win32':
            program_files = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))
            cli = shutil.which(str(program_files / 'KiCad/10.0/bin/kicad-cli.exe'))
        elif cli is None and sys.platform == 'darwin':
            bundle = Path('/Applications/KiCad/KiCad.app/Contents/MacOS')
            cli = shutil.which(str(bundle / 'kicad-cli'))
    if cli is None:
        raise ValueError('KiCad CLI was not found. Add it to PATH or pass --kicad-cli.')
    # Keep the executable name intact for wrappers or multi-call symlinks.
    return Path(cli).absolute()


def render_environment(work, cli, model_override):
    """Create an isolated KiCad profile and locate the standard model library."""
    config_root = work / 'config'
    config = config_root / '10.0'
    config.mkdir(parents=True)
    (config / '3d_viewer.json').write_text(
        json.dumps({'meta': {'version': 4}, 'render': RENDER_SETTINGS}),
        encoding='utf-8',
    )
    (config / 'kicad_advanced').write_text('MaximumThreads=1\n', encoding='ascii')

    env = dict(os.environ, KICAD_CONFIG_HOME=str(config_root))
    if model_override is not None:
        if not model_override.is_dir():
            raise ValueError(f'KiCad 3D model directory not found: {model_override}')
        env['KICAD10_3DMODEL_DIR'] = str(model_override.resolve())
    elif 'KICAD10_3DMODEL_DIR' not in env:
        install_root = cli.resolve().parent.parent
        for relative_path in ('share/kicad/3dmodels', 'SharedSupport/3dmodels'):
            models = install_root / relative_path
            if models.is_dir():
                env['KICAD10_3DMODEL_DIR'] = str(models)
                break
    return env


def run_kicad(cli, arguments, env):
    """Run the CLI without shell quoting and retain any failure diagnostics."""
    result = subprocess.run([str(cli), *arguments], env=env, capture_output=True)
    if result.returncode:
        details = (result.stderr or result.stdout).decode(errors='replace').strip()
        raise RuntimeError(details or f'KiCad exited with status {result.returncode}.')
    return result.stdout.decode(errors='replace').strip()


def render_board(cli, board, target, env, side, view):
    """Raytrace the board on transparency for clean edges and through-holes."""
    # Normalize negative angles so KiCad's parser does not mistake them for options.
    rotation = ','.join(str(angle % 360) for angle in view['rotation'])
    width, height = CANVAS_SIZE
    key = str(view['key_light'])
    command = [
        'pcb', 'render',
        '--quality', 'user',
        '--width', str(width),
        '--height', str(height),
        '--background', 'transparent',
        '--side', side,
        '--rotate', rotation,
        '--zoom', str(view['zoom']),
        '--light-top', key if side == 'top' else '0',
        '--light-bottom', key if side == 'bottom' else '0',
        '--light-camera', '1',
        '--light-side', '0',
        '--output', str(target),
        str(board),
    ]
    run_kicad(cli, command, env)
    if not target.is_file():
        raise RuntimeError(f'KiCad did not produce {target.name}.')
    with Image.open(target) as png:
        return png.convert('RGBA')


# Image compositing
def composite(board, view):
    """Project one soft shadow and center the result in the 4K frame."""
    stretch_x, stretch_y = view['shadow_scale']
    offset_x, offset_y = view['shadow_offset']
    blur = view['shadow_blur']
    red, green, blue, alpha = board.split()
    bounds = alpha.getbbox()
    if bounds is None or alpha.getextrema()[0] != 0:
        raise RuntimeError('The KiCad render must contain a board on a transparent background.')
    left, top, right, bottom = bounds
    if left == 0 or top == 0 or right == alpha.width or bottom == alpha.height:
        raise ValueError('The board reaches the render edge. Reduce the zoom for this view.')
    shape = alpha.crop(bounds)
    shadow_width = round(shape.width * stretch_x)
    shadow_height = round(shape.height * stretch_y)
    shadow_x = round((left + right - shadow_width) / 2) + round(offset_x * SCALE)
    shadow_y = round((top + bottom - shadow_height) / 2) + round(offset_y * SCALE)

    shadow_alpha = Image.new('L', board.size)
    shadow_shape = shape.resize((shadow_width, shadow_height), Image.Resampling.BICUBIC)
    shadow_alpha.paste(shadow_shape, (shadow_x, shadow_y))
    
    # Carry the shadow under the board to keep contact at the silhouette edge.
    shadow_alpha = ImageChops.lighter(shadow_alpha, alpha)
    framing = shadow_alpha.getbbox()
    shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(blur * SCALE))
    shadow = Image.new('RGBA', board.size, 'black')
    shadow.putalpha(shadow_alpha.point(lambda value: round(value * 0.31)))

    lift = [round(255 * (value / 255) ** 0.90) for value in range(256)]
    lit_board = Image.merge('RGBA', (red.point(lift), green.point(lift), blue.point(lift), alpha))
    large_width, large_height = MASTER_SIZE
    
    # Center on the board and shadow together. Crop the transparent layers before flattening.
    left, top, right, bottom = framing
    crop_x = (left + right - large_width) // 2
    crop_y = (top + bottom - large_height) // 2
    crop = (crop_x, crop_y, crop_x + large_width, crop_y + large_height)
    board_left, board_top, board_right, board_bottom = bounds
    if board_left < crop[0] or board_top < crop[1] or board_right > crop[2] or board_bottom > crop[3]:
        raise ValueError('The board exceeds the portrait crop. Reduce the zoom for this view.')
    scene = Image.alpha_composite(shadow.crop(crop), lit_board.crop(crop))
    white = Image.new('RGBA', scene.size, 'white')
    return Image.alpha_composite(white, scene).convert('RGB')


# Export and command-line entry point
def save_exports(master, output_dir, board_name, view_name):
    """Write the 4K master and its Lanczos downsample as RGB PNGs."""
    # Stage on the destination filesystem so each image can be replaced atomically.
    with tempfile.TemporaryDirectory(prefix='.render-', dir=output_dir) as stage_dir:
        for size in OUTPUT_SIZES:
            width, height = size
            png = master
            if size != MASTER_SIZE:
                png = master.resize(size, Image.Resampling.LANCZOS)
            output = output_dir / f'{board_name}-{view_name}-{width}x{height}.png'
            staged = Path(stage_dir) / output.name
            png.save(staged, optimize=True)
            digest = hashlib.sha256(staged.read_bytes()).hexdigest()
            staged.replace(output)
            print(f'{output}\nSHA-256 {digest}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('board', type=Path, help='input .kicad_pcb file')
    parser.add_argument('--config', type=Path, help='JSON file with per-view settings')
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path(__file__).resolve().parent,
        help='PNG destination (default: the directory containing this script)',
    )
    parser.add_argument('--kicad-cli', type=Path, help='KiCad executable or wrapper path')
    parser.add_argument('--models-dir', type=Path, help='path to the standard 3D model library')
    args = parser.parse_args()

    board = args.board.resolve()
    if not board.is_file():
        parser.error(f'Board not found: {board}')
    output_dir = args.output_dir.resolve()
    try:
        cli = find_cli(args.kicad_cli)
        views = load_views(args.config)
        with tempfile.TemporaryDirectory(prefix='kicad-render-') as work_dir:
            work = Path(work_dir)
            env = render_environment(work, cli, args.models_dir)
            version = run_kicad(cli, ['version'], env)
            if not re.match(r'^10\.0(?:\.|$)', version):
                raise RuntimeError(f'KiCad 10.0 is required, found {version}.')

            output_dir.mkdir(parents=True, exist_ok=True)
            for name, view in views.items():
                side = 'top' if name == 'front' else 'bottom'
                print(f'Rendering {name} with KiCad {version}...', flush=True)
                raw = render_board(cli, board, work / f'{name}.png', env, side, view)
                master = composite(raw, view)
                save_exports(master, output_dir, board.stem, name)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f'Render failed: {error}\n')


if __name__ == '__main__':
    main()
