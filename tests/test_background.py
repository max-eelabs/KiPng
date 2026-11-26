# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

from threading import Event

import pytest
from PIL import Image, ImageColor
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit

from kipng.contracts.background import (
    BACKGROUND_COLORS,
    DEFAULT_BACKGROUND,
    BackgroundSettings,
    BackgroundTexture,
)
from kipng.export.background import apply_background, colored_texture_tile
from kipng.export.render_image import composite, save_image
from kipng.ui.controls.sections import viewport_render
from kipng.ui.viewport.pane import BoardViewport


def test_background_controls_update_preview_and_restore_texture(app, tmp_path):
    # Connect the controls to a viewport whose scene can load without a GPU.
    view = BoardViewport()
    view.load_model(tmp_path / "unused.glb")
    section = viewport_render.create_section(lambda: view)
    selector = section.findChild(QComboBox, "backgroundSelector")
    custom = section.findChild(QLineEdit, "backgroundHex")
    hint = section.findChild(QLabel, "backgroundHexHint")
    texture = section.findChild(QComboBox, "backgroundTexture")
    try:
        # A new preview is white with the texture choices disabled.
        root = view.rootObject()
        assert view.background == DEFAULT_BACKGROUND
        assert root.property("color").name() == "#ffffff"
        assert custom.isHidden()
        assert not texture.isEnabled()
        assert [texture.itemText(i) for i in range(texture.count())] == [
            "None",
            "Fabric Grain",
            "Crinkled Paper",
        ]

        # Apply fabric to a preset and then enter a custom hex color.
        selector.setCurrentText("Warm Stone")
        texture.setCurrentText("Fabric Grain")
        assert view.background == BackgroundSettings("#E4DDD2", BackgroundTexture.FABRIC_GRAIN)
        selector.setCurrentText("Custom")
        custom.setText("a12bcd")
        assert not custom.isHidden()
        assert hint.isHidden()
        assert view.background == BackgroundSettings("#A12BCD", BackgroundTexture.FABRIC_GRAIN)
        assert root.property("color").name() == "#a12bcd"
        assert (
            root.property("backgroundPattern").toString() == "image://backdrop/fabric-grain/A12BCD"
        )

        # Incomplete and invalid values leave the last valid background in use.
        for value in ("#a12", "#zzzzzz", "#01020304"):
            custom.setText(value)
            assert not hint.isHidden()
            assert "#A12BCD" in hint.text()
            assert view.background == BackgroundSettings("#A12BCD", BackgroundTexture.FABRIC_GRAIN)

        # Switch to paper, then use the transparency checkerboard and restore paper.
        texture.setCurrentText("Crinkled Paper")
        assert view.background == BackgroundSettings("#A12BCD", BackgroundTexture.CRINKLED_PAPER)
        assert (
            root.property("backgroundPattern").toString()
            == "image://backdrop/crinkled-paper/A12BCD"
        )
        selector.setCurrentText("Transparent")
        assert not texture.isEnabled()
        assert texture.currentText() == "None"
        assert view.background == BackgroundSettings(None)
        assert root.property("backgroundPattern").toString() == "image://backdrop/checker"
        selector.setCurrentText("Custom")
        assert custom.text() == "#A12BCD"
        assert texture.currentText() == "Crinkled Paper"

        # Both whites suspend the texture, which can also be cleared explicitly.
        custom.setText("#ffffff")
        assert view.background == DEFAULT_BACKGROUND
        assert not texture.isEnabled()
        assert texture.currentText() == "None"
        selector.setCurrentText("White")
        assert view.background == DEFAULT_BACKGROUND
        selector.setCurrentText("Mist Blue")
        assert view.background == BackgroundSettings("#DCE5EB", BackgroundTexture.CRINKLED_PAPER)
        texture.setCurrentText("None")
        assert view.background == BackgroundSettings("#DCE5EB")
        assert root.property("backgroundPattern").isEmpty()
    finally:
        view.release_model()
        view.close()


def test_opaque_backgrounds_use_exact_colors_and_transparent_keeps_shadow(tmp_path):
    # Process a synthetic raytraced board with its normal soft shadow.
    board = Image.new("RGBA", (240, 240))
    board.paste((40, 90, 50, 255), (100, 80, 140, 120))
    scene = composite(board, (200, 200))

    # All flat backgrounds are the exact hex color outside the shadow.
    for color in (*BACKGROUND_COLORS.values(), "#131517"):
        if color is not None:
            opaque = apply_background(scene, BackgroundSettings(color), scene.size)
            assert opaque.mode == "RGB"
            assert opaque.getpixel((0, 0)) == ImageColor.getrgb(color)

    # Saving a transparent render keeps empty, opaque, and semitransparent pixels.
    png = save_image(
        scene, tmp_path, "board", Event(), (100, 100), background=BackgroundSettings(None)
    )
    with Image.open(png) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0)) == (0, 0, 0, 0)
        assert image.getpixel((50, 40))[3] == 255
        assert 0 < image.getpixel((50, 62))[3] < 255


@pytest.mark.parametrize(
    "texture", (BackgroundTexture.FABRIC_GRAIN, BackgroundTexture.CRINKLED_PAPER)
)
def test_texture_is_repeatable_and_keeps_its_scale_at_4k(texture):
    # Use the matching colored tile to compare the texture at both resolutions.
    color = "#E4DDD2"
    settings = BackgroundSettings(color, texture)
    tile = colored_texture_tile(color, texture)
    edge = tile.width
    fhd = apply_background(Image.new("RGBA", (1080, 1080)), settings, (1080, 1080))
    wide = apply_background(Image.new("RGBA", (2160, 2160)), settings, (2160, 2160))

    # Keep distinct light and dark details and repeat the pattern at twice the pixel scale.
    assert fhd.crop((0, 0, edge, edge)).tobytes() == tile.tobytes()
    assert fhd.crop((edge, 0, edge + 32, edge)).tobytes() == tile.crop((0, 0, 32, edge)).tobytes()
    assert (
        wide.crop((0, 0, edge * 2, edge * 2)).tobytes()
        == tile.resize((edge * 2, edge * 2), Image.Resampling.BILINEAR).tobytes()
    )
    for base, (low, high) in zip(ImageColor.getrgb(color), tile.getextrema(), strict=True):
        assert low < base - 8 < base + 8 < high

    # Direct callers also get a flat white fill or preserved alpha for ineligible colors.
    empty = Image.new("RGBA", (32, 32))
    assert (
        apply_background(empty, BackgroundSettings("#FFFFFF", texture), empty.size).getextrema()
        == ((255, 255),) * 3
    )
    assert apply_background(empty, BackgroundSettings(None, texture), empty.size) is empty
