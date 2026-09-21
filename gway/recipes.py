"""Recipe discovery, loading, and execution for GWAY."""

import os
from pathlib import Path

from .ingestion.router import has_path_syntax
from .tokens import is_literal, statements, token_value, tokenize


_NO_PIPELINE = object()


def parse_recipe_context(tokens):
    """Parse recipe --key [value] arguments into shared semantic context."""
    context = {}
    index = 0
    tokens = list(tokens)
    while index < len(tokens):
        raw = tokens[index]
        token = token_value(raw)
        if is_literal(raw) or not token.startswith("--") or token == "--":
            raise ValueError(f"Unexpected recipe argument: {token}")
        key = token[2:].replace("-", "_")
        if index + 1 < len(tokens):
            next_token = tokens[index + 1]
            next_value = token_value(next_token)
            if is_literal(next_token) or not next_value.startswith("--"):
                context[key] = next_value
                index += 2
                continue
        context[key] = True
        index += 1
    return context


def _recipe_base(runtime):
    stack = getattr(runtime, "_recipe_stack", ())
    return stack[-1].parent if stack else Path.cwd()


def recipe_path(runtime, source, *, allow_bare=True):
    """Resolve a possible recipe reference without executing it."""
    pathlike = isinstance(source, os.PathLike)
    text = os.fspath(source) if pathlike else str(source)
    explicit = pathlike or has_path_syntax(text)

    path = Path(text).expanduser()
    if not path.is_absolute():
        path = _recipe_base(runtime) / path

    candidates = [path]
    if path.suffix == "":
        candidates.append(path.with_suffix(".rx"))
    if path.is_dir():
        candidates.extend(
            (
                path / f"{path.name}.rx",
                path / "__main__.rx",
            )
        )

    if explicit:
        return next(
            (candidate for candidate in candidates if candidate.is_file()), path
        )
    if allow_bare:
        return next(
            (candidate for candidate in candidates if candidate.is_file()), None
        )
    return None


def companion_path(recipe_filename):
    """Return the sibling Python path associated with one recipe path."""
    recipe = Path(recipe_filename).expanduser().resolve()
    companion = recipe.with_suffix(".py")
    if companion == recipe or not companion.is_file():
        return None
    return companion


def ingest_companion(runtime, recipe_filename):
    """Ingest a recipe's sibling Python companion once per Gateway."""
    companion = companion_path(recipe_filename)
    if companion is None:
        return []

    ingested = getattr(runtime, "_recipe_companions", None)
    if ingested is None:
        ingested = set()
        runtime._recipe_companions = ingested

    if companion in ingested:
        return []

    # Mark the path only after successful ingestion so a failed import may be
    # retried after its cause is corrected.
    wrapped = runtime.ingest_path(companion)
    ingested.add(companion)
    return wrapped


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
                    stripped[2:].strip().casefold() == section.strip().casefold()
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


def execute_recipe(
    runtime,
    recipe_filename,
    *,
    context=None,
    section=None,
    pipeline=_NO_PIPELINE,
):
    """Execute one recipe in the caller's runtime and return its internal results."""
    path = Path(recipe_filename).expanduser().resolve()
    runtime.launchables.recipe(
        path,
        metadata={"recipe": str(path)},
    )
    stack = getattr(runtime, "_recipe_stack", None)
    if stack is None:
        stack = []
        runtime._recipe_stack = stack

    if path in stack:
        cycle = " -> ".join(str(item) for item in (*stack, path))
        raise RuntimeError(f"Recipe cycle: {cycle}")

    stack.append(path)
    try:
        if context:
            runtime.context.update(context)

        ingest_companion(runtime, path)
        commands, _ = load_recipe(path, section=section)
        statement_list = []
        for command in commands:
            statement_list.extend(statements(command.get("tokens", ())))

        if not statement_list:
            return [], None

        from .dispatch import dispatch_program

        if pipeline is _NO_PIPELINE:
            return dispatch_program(runtime, statement_list)
        return dispatch_program(runtime, statement_list, pipeline=pipeline)
    finally:
        stack.pop()
