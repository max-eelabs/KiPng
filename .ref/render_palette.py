# Copyright (c) 2026 Maxim Pavlov
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render a 2160 × 3840 sheet of KiPng's top and bottom PCB color previews.

Run with the KiPng virtual environment, for example:
    .venv/Scripts/python.exe .ref/render_palette.py PROJECT.kicad_pcb

The PNG is saved in the current directory by default. Use --output to choose
another path or --kicad-cli for a custom KiCad 10.0 installation.
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from PIL import Image, ImageChops, ImageDraw, ImageFont
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kipng.contracts import BoardSnapshot, PreviewError  # noqa: E402
from kipng.export.cli import find_cli  # noqa: E402
from kipng.export.exporter import export_board_model  # noqa: E402
from kipng.ui.viewport.colors import COLOR_SCHEMES  # noqa: E402
from kipng.ui.viewport.pane import BoardViewport  # noqa: E402

SHEET_SIZE = (2160, 3840)
FACES = ("Top view", "Bottom view")
COLUMNS = (517, 1477)
LABEL_X = 1971
FIRST_ROW = 230
ROW_HEIGHT = 510
TILE_SIZE = (946, 500)
MODEL_PATH = re.compile(r'(\(model\s+)("(?:[^"\\]|\\.)*")')


def resolve_local_models(text: str, project_dir: Path) -> str:
    """Keep local 3D model references valid after staging outside the project."""

    def resolve(match: re.Match[str]) -> str:
        model = json.loads(match[2]).replace("${KIPRJMOD}", project_dir.as_posix())
        candidate = Path(model)
        if not candidate.is_absolute() and "$" not in model and ":" not in model:
            local = project_dir / candidate
            if local.is_file():
                model = local.as_posix()
        return match[1] + json.dumps(model, ensure_ascii=False)

    return MODEL_PATH.sub(resolve, text)


class SavedBoard:
    def __init__(self, board: Path, work: Path, cli: Path) -> None:
        self.board = board
        self.work = work
        self.cli = cli

    def read(self, _cancelled: Event) -> BoardSnapshot:
        text = self.board.read_text(encoding="utf-8")
        project = self.board.with_suffix(".kicad_pro")
        if project.is_file():
            shutil.copyfile(project, self.work / project.name)
        return BoardSnapshot(
            resolve_local_models(text, self.board.parent),
            self.work,
            self.board.stem,
            str(self.cli),
        )


def frame_image(view: BoardViewport) -> Image.Image:
    frame = view.grabFramebuffer().convertToFormat(QImage.Format.Format_RGB888)
    if frame.isNull():
        raise PreviewError("The 3D viewport returned an empty frame.")
    return Image.frombytes(
        "RGB",
        (frame.width(), frame.height()),
        frame.constBits(),
        "raw",
        "RGB",
        frame.bytesPerLine(),
    )


def capture_views(model: Path) -> dict[tuple[str, str], Image.Image]:
    app = QApplication([])
    view = BoardViewport()
    failures: list[str] = []
    view.failed.connect(failures.append)
    view.resize(1200, 720)
    view.show()
    try:
        view.load_model(model)
        scene = view.rootObject()
        for _ in range(60):
            if failures or scene is None or scene.property("framed"):
                break
            QTest.qWait(500)
        if failures:
            raise PreviewError(failures[0])
        if scene is None or not scene.property("framed"):
            raise PreviewError("The 3D viewport did not finish framing the board.")
        if not any(layer == "soldermask" for _, layer in view.board_materials):
            raise PreviewError("The exported board has no solder-mask materials to recolor.")

        extent = scene.property("boardExtent")
        yaw = 90 if extent.z() > extent.x() else 0
        views = {}
        for face, pitch, angle in zip(FACES, (-90, 90), (yaw, yaw + 180), strict=True):
            view.set_camera_view(pitch, angle)
            for color, scheme in COLOR_SCHEMES.items():
                view.set_color_scheme(scheme)
                QTest.qWait(60)
                views[face, color] = frame_image(view)
        return views
    finally:
        view.release_model()
        view.close()
        app.processEvents()


def fit_frames(views: dict[tuple[str, str], Image.Image]) -> dict[tuple[str, str], Image.Image]:
    # Center each face by its full shadow while keeping both faces at one scale.
    boxes: dict[str, list[tuple[int, int, int, int]]] = {face: [] for face in FACES}
    for (face, _), frame in views.items():
        delta = ImageChops.difference(frame, Image.new("RGB", frame.size, "white"))
        bounds = delta.point(lambda value: 255 if value >= 5 else 0).getbbox()
        if bounds is None:
            raise PreviewError("A rendered view contains no visible board.")
        boxes[face].append(bounds)
    crops = {
        face: (
            min(box[0] for box in face_boxes),
            min(box[1] for box in face_boxes),
            max(box[2] for box in face_boxes),
            max(box[3] for box in face_boxes),
        )
        for face, face_boxes in boxes.items()
    }
    width = max(right - left for left, _, right, _ in crops.values())
    height = max(bottom - top for _, top, _, bottom in crops.values())
    scale = min(TILE_SIZE[0] / width, TILE_SIZE[1] / height)
    fitted = {}
    for key, frame in views.items():
        cropped = frame.crop(crops[key[0]])
        size = round(cropped.width * scale), round(cropped.height * scale)
        fitted[key] = cropped.resize(size, Image.Resampling.LANCZOS)
    return fitted


def make_sheet(title: str, views: dict[tuple[str, str], Image.Image]) -> Image.Image:
    sheet = Image.new("RGB", SHEET_SIZE, "white")
    draw = ImageDraw.Draw(sheet)
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    title_font = ImageFont.truetype(str(fonts / "seguisb.ttf"), 76)
    subtitle_font = ImageFont.truetype(str(fonts / "segoeui.ttf"), 31)
    heading_font = ImageFont.truetype(str(fonts / "seguisb.ttf"), 37)
    draw.text((61, 49), title, font=title_font, fill="#1c2530", anchor="lt")
    draw.text((64, 136), "PCB color palette", font=subtitle_font, fill="#455665", anchor="lt")
    for center, face in zip(COLUMNS, FACES, strict=True):
        draw.text((center, 181), face, font=heading_font, fill="#1c2530", anchor="mt")

    fitted = fit_frames(views)
    for index, color in enumerate(COLOR_SCHEMES):
        center_y = FIRST_ROW + index * ROW_HEIGHT + ROW_HEIGHT // 2
        for center_x, face in zip(COLUMNS, FACES, strict=True):
            frame = fitted[face, color]
            sheet.paste(frame, (center_x - frame.width // 2, center_y - frame.height // 2))
        draw.text((LABEL_X, center_y), color, font=heading_font, fill="#455665", anchor="lm")
    return sheet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("board", type=Path, help="Path to a saved .kicad_pcb board")
    parser.add_argument("--output", type=Path, help="Destination PNG")
    parser.add_argument("--title", help="Sheet title, defaulting to the board filename stem")
    parser.add_argument("--kicad-cli", type=Path, help="Path to kicad-cli.exe")
    args = parser.parse_args()
    board = args.board.resolve()
    if not board.is_file() or board.suffix.lower() != ".kicad_pcb":
        parser.error(f"expected a saved .kicad_pcb file, got {board}")
    output = args.output or Path(f"{board.stem}-color-palette-2160x3840.png")
    if output.suffix.lower() != ".png":
        parser.error("--output must end in .png")

    cancelled = Event()
    try:
        cli = find_cli(str(args.kicad_cli.resolve()) if args.kicad_cli else None, cancelled)
        models = cli.resolve().parent.parent / "share/kicad/3dmodels"
        if models.is_dir():
            os.environ.setdefault("KICAD10_3DMODEL_DIR", str(models))
        with TemporaryDirectory(prefix="kipng-palette-") as directory:
            work = Path(directory)
            model = work / "board.glb"
            export_board_model(model, cancelled, source=SavedBoard(board, work, cli))
            sheet = make_sheet(args.title or board.stem, capture_views(model))
        with TemporaryDirectory(prefix="kipng-palette-", dir=output.parent) as directory:
            staged = Path(directory) / "sheet.png"
            sheet.save(staged, dpi=(300, 300))
            staged.replace(output)
    except (OSError, PreviewError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(output.resolve())


if __name__ == "__main__":
    main()
