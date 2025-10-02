"""PNG utilities."""

from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image

from gway import gw


def _ensure_png_files(folder: Path) -> list[Path]:
    """Return the sorted PNG files within *folder* or raise if none exist."""

    files = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".png")
    if not files:
        raise ValueError("No PNG files found in the input folder.")
    return files


def _normalize_path(path: str | os.PathLike[str]) -> Path:
    """Expand user/home markers and return an absolute Path."""

    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return expanded
    return Path.cwd() / expanded


def make_grid(
    input_folder: str | os.PathLike[str],
    *,
    output_file: str | os.PathLike[str] | None = None,
    cards_per_row: int = 15,
    thumb_size: tuple[int, int] = (223, 310),
    background_color: tuple[int, int, int] = (0, 0, 0),
):
    """Create a thumbnail grid from PNG files in *input_folder*.

    Parameters
    ----------
    input_folder:
        Directory containing PNG files to tile into the grid.
    output_file:
        Destination file path. Defaults to ``work/shared/png/card_grid.png``
        within the gateway resource tree.
    cards_per_row:
        How many thumbnails to place in each row of the output grid.
    thumb_size:
        Maximum size for each thumbnail (width, height) before composing the grid.
    background_color:
        RGB tuple used for the blank canvas background.

    Returns
    -------
    dict
        Mapping describing the created grid including the output path,
        grid dimensions, and number of cards combined.
    """

    if cards_per_row <= 0:
        raise ValueError("cards_per_row must be a positive integer.")

    folder_path = _normalize_path(input_folder)
    if not folder_path.is_dir():
        raise FileNotFoundError(f"Input folder does not exist: {folder_path}")

    files = _ensure_png_files(folder_path)

    if output_file is None:
        output_path = Path(gw.resource("work", "shared", "png", "card_grid.png"))
    else:
        output_path = _normalize_path(output_file)

    os.makedirs(output_path.parent, exist_ok=True)

    # Determine consistent thumbnail size based on the first card.
    with Image.open(files[0]) as first_card:
        first_card.thumbnail(thumb_size, Image.LANCZOS)
        card_width, card_height = first_card.size

    num_cards = len(files)
    rows = math.ceil(num_cards / cards_per_row)
    grid_width = cards_per_row * card_width
    grid_height = rows * card_height

    grid = Image.new("RGB", (grid_width, grid_height), color=background_color)

    for idx, filename in enumerate(files):
        with Image.open(filename) as card:
            card.thumbnail(thumb_size, Image.LANCZOS)
            x = (idx % cards_per_row) * card_width
            y = (idx // cards_per_row) * card_height
            grid.paste(card, (x, y))

    grid.save(output_path)

    return {
        "path": str(output_path),
        "width": grid_width,
        "height": grid_height,
        "cards": num_cards,
        "rows": rows,
        "columns": cards_per_row,
    }


__all__ = ["make_grid"]

