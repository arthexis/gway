"""Recipe file loading for GWAY."""

from pathlib import Path

from .tokens import tokenize


def load_recipe(recipe_filename, *, strict=True, section=None):
    """Load a recipe from an explicit filesystem path.

    Blank lines and comments are ignored. A physical line beginning with --
    extends the previous operation. Quote provenance is retained so single
    quotes can mark opaque literal values.
    """
    path = Path(recipe_filename).expanduser()
    if not path.is_file():
        if strict:
            raise FileNotFoundError(f"Recipe not found: {path}")
        return [], []

    commands = []
    comments = []
    current = None
    active_section = section is None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            comments.append(stripped)
            if (
                section is not None
                and stripped.startswith("# ")
                and not stripped.startswith("## ")
            ):
                active_section = (
                    stripped[2:].strip().casefold()
                    == section.strip().casefold()
                )
            continue

        if not active_section:
            continue

        tokens = tokenize(stripped)
        if stripped.startswith("--") and current is not None:
            current["tokens"].extend(tokens)
            continue

        current = {"tokens": tokens}
        commands.append(current)

    return commands, comments
