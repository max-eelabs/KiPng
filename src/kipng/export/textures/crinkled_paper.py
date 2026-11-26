# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate matte paper with irregular, softly lit folds."""

from functools import lru_cache
from random import Random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

CELL_COUNT = 16
CELL_SIZE = 64
TILE_SIZE = CELL_COUNT * CELL_SIZE
PADDING = 36
WARP_PITCH = CELL_SIZE // 2
Point = tuple[int, int, int]


def facet_shade(a: Point, b: Point, c: Point) -> int:
    # Derive the slope of the paper from the three corner heights.
    ux, uy, uz = (end - start for start, end in zip(a, b, strict=True))
    vx, vy, vz = (end - start for start, end in zip(a, c, strict=True))
    area = ux * vy - uy * vx
    slope_x = (uz * vy - uy * vz) / area
    slope_y = (ux * vz - uz * vx) / area
    return max(0, min(255, round(128 + 215 * (-0.6 * slope_x - 0.8 * slope_y))))


def warp_folds(surface: Image.Image, random: Random) -> Image.Image:
    """Bend the fold edges with a periodic distortion mesh."""
    cells = TILE_SIZE // WARP_PITCH
    offsets = [(random.randint(-10, 10), random.randint(-10, 10)) for _ in range(cells**2)]

    def corner(column: int, row: int) -> tuple[int, int]:
        dx, dy = offsets[row % cells * cells + column % cells]
        return column * WARP_PITCH + PADDING + dx, row * WARP_PITCH + PADDING + dy

    mesh = []
    for row in range(cells):
        for column in range(cells):
            x, y = column * WARP_PITCH, row * WARP_PITCH
            bounds = (x, y, x + WARP_PITCH, y + WARP_PITCH)
            samples = (
                *corner(column, row),
                *corner(column, row + 1),
                *corner(column + 1, row + 1),
                *corner(column + 1, row),
            )
            mesh.append((bounds, samples))
    return surface.transform(
        (TILE_SIZE, TILE_SIZE), Image.Transform.MESH, mesh, Image.Resampling.BILINEAR
    )


@lru_cache(maxsize=1)
def tile() -> Image.Image:
    random = Random(317)
    folds = [
        (random.randint(-15, 15), random.randint(-15, 15), random.randint(-16, 16))
        for _ in range(CELL_COUNT**2)
    ]
    diagonals = [random.getrandbits(1) for _ in folds]

    def index(column: int, row: int) -> int:
        return row % CELL_COUNT * CELL_COUNT + column % CELL_COUNT

    def point(column: int, row: int) -> Point:
        x, y, height = folds[index(column, row)]
        return (column * CELL_SIZE + x + PADDING, row * CELL_SIZE + y + PADDING, height)

    # Extend the periodic mesh beyond the crop so creases continue across the seams.
    edge = TILE_SIZE + 2 * PADDING
    surface = Image.new("L", (edge, edge), 128)
    draw = ImageDraw.Draw(surface)
    for row in range(-1, CELL_COUNT + 1):
        for column in range(-1, CELL_COUNT + 1):
            a, b = point(column, row), point(column + 1, row)
            c, d = point(column, row + 1), point(column + 1, row + 1)
            if diagonals[index(column, row)]:
                faces = ((a, b, d), (a, d, c))
            else:
                faces = ((a, b, c), (b, d, c))
            for face in faces:
                draw.polygon([point[:2] for point in face], fill=facet_shade(*face))

    creases = surface.filter(ImageFilter.GaussianBlur(1.5))
    soft_light = surface.filter(ImageFilter.GaussianBlur(8))
    shaded = warp_folds(ImageChops.blend(creases, soft_light, 0.23), random)
    fibers = Image.frombytes("L", shaded.size, random.randbytes(TILE_SIZE**2))
    return ImageChops.blend(shaded, fibers, 0.08)
