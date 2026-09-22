"""Recipe invocation context and filesystem resolution."""

import os
from pathlib import Path

from ..ingestion.router import has_path_syntax
from ..tokens import is_literal, token_value


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


def recipe_base(runtime):
    """Return the directory used to resolve relative recipe references."""
    stack = getattr(runtime, "_recipe_stack", ())
    return stack[-1].parent if stack else Path.cwd()


def recipe_path(runtime, source, *, allow_bare=True):
    """Resolve a possible recipe reference without executing it."""
    pathlike = isinstance(source, os.PathLike)
    text = os.fspath(source) if pathlike else str(source)
    explicit = pathlike or has_path_syntax(text)

    path = Path(text).expanduser()
    if not path.is_absolute():
        path = recipe_base(runtime) / path

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
