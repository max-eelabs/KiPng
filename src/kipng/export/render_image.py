# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Apply the reference renderer's soft shadow and write a portrait PNG."""

from contextlib import ExitStack
from itertools import count
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from PIL import Image, ImageChops, ImageFilter

from ..contracts import PreviewCancelled, PreviewError

OUTPUT_SIZE = (1080, 1920)
# Composite at twice the output resolution for the reference's antialiased finish.
SCALE = 2
COMPOSITE_SIZE = (OUTPUT_SIZE[0] * SCALE, OUTPUT_SIZE[1] * SCALE)
SHADOW_SCALE = 1.08
SHADOW_OFFSET = (3, 20)
SHADOW_BLUR = 8


def composite(board: Image.Image, translation: tuple[int, int]) -> Image.Image:
    red, green, blue, alpha = board.split()
    bounds = alpha.getbbox()
    if bounds is None or alpha.getextrema()[0] != 0:
        raise PreviewError("KiCad did not render a board on a transparent background.")
    left, top, right, bottom = bounds
    if left == 0 or top == 0 or right == alpha.width or bottom == alpha.height:
        raise PreviewError("The board reaches the render edge. Zoom out or pan toward the center.")

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
    framing = shadow_alpha.getbbox()
    shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(SHADOW_BLUR * SCALE))
    shadow = Image.new("RGBA", board.size, "black")
    shadow.putalpha(shadow_alpha.point(lambda value: round(value * 0.31)))

    lift = [round(255 * (value / 255) ** 0.90) for value in range(256)]
    lit_board = Image.merge("RGBA", (red.point(lift), green.point(lift), blue.point(lift), alpha))
    width, height = COMPOSITE_SIZE

    # Center on the board and shadow together, then restore the viewport pan.
    frame_left, frame_top, frame_right, frame_bottom = framing
    shift_x, shift_y = translation
    crop_x = (frame_left + frame_right - width) // 2 - shift_x
    crop_y = (frame_top + frame_bottom - height) // 2 - shift_y
    crop = (crop_x, crop_y, crop_x + width, crop_y + height)
    if left < crop[0] or top < crop[1] or right > crop[2] or bottom > crop[3]:
        raise PreviewError(
            "The board exceeds the portrait crop. Zoom out or pan toward the center."
        )
    scene = Image.alpha_composite(shadow.crop(crop), lit_board.crop(crop))
    white = Image.new("RGBA", scene.size, "white")
    return Image.alpha_composite(white, scene).convert("RGB")


def save_image(master: Image.Image, output_dir: Path, board_name: str, cancelled: Event) -> Path:
    if cancelled.is_set():
        raise PreviewCancelled

    # Stage the PNG on the destination filesystem for atomic publication.
    width, height = OUTPUT_SIZE
    with TemporaryDirectory(prefix=".render-", dir=output_dir) as directory:
        staged = Path(directory) / "render.png"
        master.resize(OUTPUT_SIZE, Image.Resampling.LANCZOS).save(staged, optimize=True)

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
