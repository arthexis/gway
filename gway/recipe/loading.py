"""Parsing and loading for .rx recipe source files."""

from pathlib import Path

from ..tokens import is_literal, token_value, tokenize


def load_recipe(recipe_filename, *, strict=True, section=None):
    """Load a recipe from an explicit filesystem path.

    Blank lines and comments are ignored. A physical line beginning with --
    extends the previous operation. A bare -- at the end of a physical line,
    including a standalone -- continuation line, also extends the operation
    with the next substantive line as positional input. Quote provenance is
    retained so single quotes can mark opaque literal values.
    """
    path = Path(recipe_filename).expanduser()
    if not path.is_file():
        if strict:
            raise FileNotFoundError(f"Recipe not found: {path}")
        return [], []

    commands = []
    comments = []
    current = None
    positional_continuation = False
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
                    stripped[2:].strip().casefold() == section.strip().casefold()
                )
            continue

        if not active_section:
            continue

        tokens = tokenize(stripped)
        extends_current = current is not None and (
            stripped.startswith("--") or positional_continuation
        )
        if extends_current:
            current["tokens"].extend(tokens)
            positional_continuation = bool(
                tokens
                and not is_literal(tokens[-1])
                and token_value(tokens[-1]) == "--"
            )
            continue

        current = {"tokens": tokens}
        commands.append(current)
        positional_continuation = bool(
            tokens
            and not is_literal(tokens[-1])
            and token_value(tokens[-1]) == "--"
        )

    return commands, comments
