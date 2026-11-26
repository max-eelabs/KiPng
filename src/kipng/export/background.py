# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate backdrops for both the interactive viewport and PNG export."""

from PIL import Image, ImageColor

from ..contracts.background import BackgroundSettings, BackgroundTexture
from .textures import TEXTURES

CHECKER_SIZE = 12


def colored_texture_tile(color: str, texture: BackgroundTexture) -> Image.Image:
    generate_tile, strength = TEXTURES[texture]
    tile = generate_tile()
    rgb = ImageColor.getrgb(color)
    offsets = [round((value - 128) * strength / 128) for value in range(256)]
    channels = [tile.point([max(0, min(255, base + delta)) for delta in offsets]) for base in rgb]
    return Image.merge("RGB", channels)


def checker_tile() -> Image.Image:
    """Make the viewport-only indicator of transparent pixels."""
    edge = CHECKER_SIZE
    tile = Image.new("RGB", (edge * 2, edge * 2), "#F4F5F6")
    tile.paste("#E4E6E8", (0, 0, edge, edge))
    tile.paste("#E4E6E8", (edge, edge, edge * 2, edge * 2))
    return tile


def apply_background(
    scene: Image.Image, settings: BackgroundSettings, output_size: tuple[int, int]
) -> Image.Image:
    """Composite the PCB and its shadow, preserving alpha for Transparent."""
    if settings.color is None:
        return scene
    texture = settings.effective_texture
    if texture is BackgroundTexture.NONE:
        base = Image.new("RGBA", scene.size, settings.color)
        return Image.alpha_composite(base, scene).convert("RGB")

    # Tile at the final size so supersampled foregrounds do not soften the texture.
    if scene.size != output_size:
        scene = scene.resize(output_size, Image.Resampling.LANCZOS)
    tile = colored_texture_tile(settings.color, texture)
    if min(output_size) >= 2160:
        tile = tile.resize((tile.width * 2, tile.height * 2), Image.Resampling.BILINEAR)
    base = Image.new("RGB", output_size)
    for y in range(0, base.height, tile.height):
        for x in range(0, base.width, tile.width):
            base.paste(tile, (x, y))
    base.paste(scene, mask=scene.getchannel("A"))
    return base
