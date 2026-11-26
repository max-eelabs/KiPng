# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate coarse fabric grain with a quiet warp and weft pattern."""

from functools import lru_cache
from random import Random

from PIL import Image, ImageChops

THREAD = (0, 38, 48, 26, -12, -48, -38, -14)
CELL_COUNT = 48


@lru_cache(maxsize=1)
def tile() -> Image.Image:
    pitch = len(THREAD)
    edge = CELL_COUNT * pitch
    random = Random(25)
    noise = Image.frombytes("L", (CELL_COUNT, CELL_COUNT), random.randbytes(CELL_COUNT**2))

    # Build a periodic neighborhood so the coarse fibers interpolate across tile edges.
    padded = Image.new("L", (CELL_COUNT * 3, CELL_COUNT * 3))
    for row in range(3):
        for column in range(3):
            padded.paste(noise, (column * CELL_COUNT, row * CELL_COUNT))
    coarse = padded.resize(
        (edge, edge), Image.Resampling.BICUBIC, box=(CELL_COUNT,) * 2 + (CELL_COUNT * 2,) * 2
    )

    # Adjacent cells alternate which thread appears to pass over the other.
    repeat = 2 * pitch
    weave = Image.frombytes(
        "L",
        (repeat, repeat),
        bytes(
            128 + THREAD[x % pitch if (x // pitch + y // pitch) % 2 else y % pitch]
            for y in range(repeat)
            for x in range(repeat)
        ),
    )
    return ImageChops.blend(coarse, weave.resize((edge, edge), Image.Resampling.NEAREST), 0.45)
