# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Control choices, defaults, and their command-line representation."""

import re
from argparse import ArgumentParser, ArgumentTypeError, Namespace
from dataclasses import dataclass, field, fields

from .background import BACKGROUND_COLORS, BackgroundSettings, BackgroundTexture
from .colors import COLOR_SCHEMES, DEFAULT_COLOR_SCHEME, BoardColors
from .render import (
    DEFAULT_SHADOW,
    FHD_SIZES,
    RESOLUTION_SCALES,
    SLIDER_MAX,
    RenderEngine,
    ShadowSettings,
)

RGB_HEX = re.compile(r"#?([0-9a-fA-F]{6})")


def slug(label: str) -> str:
    return label.lower().replace(" ", "-")


@dataclass(frozen=True)
class Control:
    key: str
    label: str
    default: str | int
    labels: tuple[str, ...] = ()
    limits: tuple[int, int] | None = None
    accepts_color: bool = False

    def setting(self):
        """Declare a settings field and register its CLI flag."""
        return field(default=self.default, metadata={"control": self})

    @property
    def flag(self) -> str:
        return "--" + self.key.replace("_", "-")

    def parse(self, value: str) -> str | int:
        if self.limits is not None:
            lower, upper = self.limits
            try:
                number = int(value)
            except ValueError:
                number = lower - 1
            if not lower <= number <= upper:
                raise ArgumentTypeError(f"expected an integer from {lower} to {upper}")
            return number

        for label in self.labels:
            if slug(value) == slug(label):
                return label
        if self.accepts_color and (match := RGB_HEX.fullmatch(value)):
            return f"#{match[1].upper()}"
        accepted = ", ".join(map(slug, self.labels))
        if self.accepts_color:
            accepted += ", or a six-digit RGB hex color"
        raise ArgumentTypeError(f"expected {accepted}")

    def add_argument(self, parser: ArgumentParser) -> None:
        if self.limits is not None:
            values = f"{self.limits[0]} to {self.limits[1]}"
        else:
            values = ", ".join(map(slug, self.labels))
            if self.accepts_color:
                values += ", or RRGGBB"
        default = slug(self.default) if isinstance(self.default, str) else self.default
        parser.add_argument(
            self.flag,
            type=self.parse,
            default=None,
            metavar=self.key.upper(),
            help=f"{self.label} ({values}). Default {default}.",
        )

    def argument(self, value: str | int) -> str:
        return f"{self.flag}={slug(value) if isinstance(value, str) else value}"


ENGINE = Control(
    "engine",
    "Engine",
    RenderEngine.VIEWPORT.value,
    tuple(engine.value for engine in RenderEngine),
)
COLOR_SCHEME = Control("color_scheme", "Color Scheme", DEFAULT_COLOR_SCHEME, tuple(COLOR_SCHEMES))
BACKGROUND = Control(
    "background", "Background", "White", tuple(BACKGROUND_COLORS), accepts_color=True
)
TEXTURE = Control(
    "texture",
    "Texture",
    BackgroundTexture.NONE.label,
    tuple(choice.label for choice in BackgroundTexture),
)
RESOLUTION = Control("resolution", "Resolution", "FHD", tuple(RESOLUTION_SCALES))
ASPECT_RATIO = Control("aspect_ratio", "Aspect Ratio", "9:16", tuple(FHD_SIZES))
LIGHT_X = Control("light_x", "Light X", DEFAULT_SHADOW.light_x, limits=(-SLIDER_MAX, SLIDER_MAX))
LIGHT_Y = Control("light_y", "Light Y", DEFAULT_SHADOW.light_y, limits=(-SLIDER_MAX, SLIDER_MAX))
SHADOW = Control("shadow", "Shadow", DEFAULT_SHADOW.strength, limits=(0, SLIDER_MAX))


@dataclass(frozen=True)
class RenderOptions:
    engine: str = ENGINE.setting()
    color_scheme: str = COLOR_SCHEME.setting()
    background: str = BACKGROUND.setting()
    texture: str = TEXTURE.setting()
    resolution: str = RESOLUTION.setting()
    aspect_ratio: str = ASPECT_RATIO.setting()
    light_x: int = LIGHT_X.setting()
    light_y: int = LIGHT_Y.setting()
    shadow: int = SHADOW.setting()

    @classmethod
    def from_cli(cls, args: Namespace) -> "RenderOptions":
        return cls(
            **{
                field.name: value
                for field in fields(cls)
                if (value := getattr(args, field.name)) is not None
            }
        )

    def cli_arguments(self) -> list[str]:
        return [control.argument(getattr(self, control.key)) for control in RENDER_CONTROLS]

    @property
    def output_size(self) -> tuple[int, int]:
        width, height = FHD_SIZES[self.aspect_ratio]
        scale = RESOLUTION_SCALES[self.resolution]
        return width * scale, height * scale

    @property
    def palette(self) -> BoardColors:
        return COLOR_SCHEMES[self.color_scheme]

    @property
    def backdrop(self) -> BackgroundSettings:
        return BackgroundSettings(
            BACKGROUND_COLORS.get(self.background, self.background),
            BackgroundTexture(slug(self.texture)),
        )

    @property
    def lighting(self) -> ShadowSettings:
        return ShadowSettings(self.light_x, self.light_y, self.shadow)

    @classmethod
    def from_render(
        cls,
        engine: RenderEngine,
        palette: BoardColors,
        output_size: tuple[int, int],
        background: BackgroundSettings,
        shadow: ShadowSettings,
    ) -> "RenderOptions":
        resolution, ratio = next(
            (resolution, ratio)
            for resolution, scale in RESOLUTION_SCALES.items()
            for ratio, (width, height) in FHD_SIZES.items()
            if (width * scale, height * scale) == output_size
        )
        return cls(
            engine=engine.value,
            color_scheme=next(name for name, colors in COLOR_SCHEMES.items() if colors == palette),
            background=next(
                (name for name, color in BACKGROUND_COLORS.items() if color == background.color),
                background.color or BACKGROUND.default,
            ),
            texture=background.effective_texture.label,
            resolution=resolution,
            aspect_ratio=ratio,
            light_x=shadow.light_x,
            light_y=shadow.light_y,
            shadow=shadow.strength,
        )


RENDER_CONTROLS = tuple(option.metadata["control"] for option in fields(RenderOptions))
