"""Dispatch-facing recipe invocation resolution."""

import os
from pathlib import Path

from ..tokens import is_unquoted, token_value
from .path import recipe_path


def recipe_source(token):
    """Return the filesystem source represented by one dispatch token."""
    return token if isinstance(token, os.PathLike) else token_value(token)


def split_recipe_stage(tokens):
    """Split one recipe invocation from a following raw pipeline."""
    tokens = list(tokens)
    for index, token in enumerate(tokens[1:], start=1):
        if is_unquoted(token) and token_value(token) == "-":
            return tokens[:index], tokens[index + 1 :]
    return tokens, []


def resolve_recipe_stage(runtime, tokens, *, pipeline):
    """Resolve a recipe stage using explicit-path then operation-safe fallback."""
    if not tokens:
        return None

    source = recipe_source(tokens[0])
    explicit = recipe_path(runtime, source, allow_bare=False)
    if explicit is not None:
        stage, remaining = split_recipe_stage(tokens)
        return explicit, stage[1:], remaining

    bare = recipe_path(runtime, source, allow_bare=True)
    if bare is None:
        return None

    stack = getattr(runtime, "_recipe_stack", ()) or ()
    if stack:
        try:
            if bare.expanduser().resolve() == Path(stack[-1]).expanduser().resolve():
                bare = None
        except (OSError, RuntimeError):
            pass
    if bare is None:
        return None

    from ..dispatch import resolve_operation

    try:
        resolve_operation(runtime, tokens, pipeline=pipeline)
    except LookupError:
        stage, remaining = split_recipe_stage(tokens)
        return bare, stage[1:], remaining
    return None
