# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Apply the reference renderer's soft shadow and write the framed PNG."""

from contextlib import ExitStack
from itertools import count
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from PIL import Image, ImageChops, ImageFilter

from ..contracts import PreviewCancelled, PreviewError
from ..contracts.background import DEFAULT_BACKGROUND, BackgroundSettings
from .background import apply_background

# Composite at twice FHD to keep the shadow consistent across resolutions.
SCALE = 2
SHADOW_SCALE = 1.08
SHADOW_OFFSET = (3, 20)
SHADOW_BLUR = 8


def composite(board: Image.Image, frame_size: tuple[int, int]) -> Image.Image:
    alpha = board.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None:
        raise PreviewError("The board is outside the render frame. Pan toward the center.")
    if alpha.getextrema()[0] != 0:
        raise PreviewError("KiCad did not render a board on a transparent background.")
    left, top, right, bottom = bounds
    # Crop around the optical center so the viewport pan stays in the render.
    width, height = frame_size
    crop_x = (board.width - width) // 2
    crop_y = (board.height - height) // 2
    crop = (crop_x, crop_y, crop_x + width, crop_y + height)
    if left < crop[0] or top < crop[1] or right > crop[2] or bottom > crop[3]:
        raise PreviewError("The board exceeds the render frame. Zoom out or pan toward the center.")

    shape = alpha.crop(bounds)
    shadow_width = round(shape.width * SHADOW_SCALE)
    shadow_height = round(shape.height * SHADOW_SCALE)
    offset_x, offset_y = SHADOW_OFFSET
    shadow_x = round((left + right - shadow_width) / 2) + offset_x * SCALE
    shadow_y = round((top + bottom - shadow_height) / 2) + offset_y * SCALE

    shadow_alpha = Image.new("L", board.size)
    shadow_shape = shape.resize((shadow_width, shadow_height), Image.Resampling.BICUBIC)
    shadow_alpha.paste(shadow_shape, (shadow_x, shadow_y))

    # Carry the shadow under the board to keep contact at the silhouette edge.
    shadow_alpha = ImageChops.lighter(shadow_alpha, alpha)
    shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(SHADOW_BLUR * SCALE))
    shadow = Image.new("RGBA", frame_size, "black")
    shadow.putalpha(shadow_alpha.crop(crop).point(lambda value: round(value * 0.31)))

    red, green, blue, alpha = board.crop(crop).split()
    lift = [round(255 * (value / 255) ** 0.90) for value in range(256)]
    lit_board = Image.merge("RGBA", (red.point(lift), green.point(lift), blue.point(lift), alpha))
    return Image.alpha_composite(shadow, lit_board)


def save_image(
    master: Image.Image,
    output_dir: Path,
    board_name: str,
    cancelled: Event,
    output_size: tuple[int, int],
    *,
    background: BackgroundSettings = DEFAULT_BACKGROUND,
) -> Path:
    if cancelled.is_set():
        raise PreviewCancelled

    # Stage the PNG on the destination filesystem for atomic publication.
    width, height = output_size
    with TemporaryDirectory(prefix=".render-", dir=output_dir) as directory:
        staged = Path(directory) / "render.png"
        master = apply_background(master, background, output_size)
        if master.size != output_size:
            master = master.resize(output_size, Image.Resampling.LANCZOS)
        master.save(staged, optimize=True)

        # Reserve the name before publishing so existing renders stay intact.
        for version in count(1):
            if cancelled.is_set():
                raise PreviewCancelled
            stem = f"{board_name}-render" if version == 1 else f"{board_name}-render-{version}"
            output = output_dir / f"{stem}-{width}x{height}.png"
            with ExitStack() as cleanup:
                try:
                    with output.open("xb"):
                        cleanup.callback(output.unlink, missing_ok=True)
                except FileExistsError:
                    continue
                if cancelled.is_set():
                    raise PreviewCancelled
                staged.replace(output)
                cleanup.pop_all()
                return output
