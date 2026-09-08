from __future__ import annotations

from collections.abc import Sequence


class ExpressionError(ValueError):
    """Raised when compact managed-command expression syntax is malformed."""


def _split_compact(token: str) -> tuple[list[str], str | None]:
    path_text, separator, argument = token.partition(":")
    path = path_text.split(".")
    if not path_text or any(not part for part in path):
        raise ExpressionError(f"invalid managed command expression: {token!r}")
    return path, argument if separator else None


def normalize_managed_args(args: Sequence[str]) -> tuple[str, list[str]]:
    """Normalize dotted/colon managed CLI syntax into dispatcher arguments.

    Dots explicitly separate project/command path components. A colon marks an
    explicit call boundary and optionally contributes one argument. A trailing
    colon is therefore accepted but adds no argument because the dispatcher
    already invokes the final command automatically.
    """
    if not args:
        raise ExpressionError("managed command expression is empty")

    first = args[0]
    remaining = list(args[1:])

    if "." in first or ":" in first:
        path, argument = _split_compact(first)
        project = path[0]
        command_args = path[1:]
        if argument:
            command_args.append(argument)
        command_args.extend(remaining)
        return project, command_args

    project = first
    if not remaining:
        return project, []

    command_head = remaining[0]
    if "." not in command_head and ":" not in command_head:
        return project, remaining

    path, argument = _split_compact(command_head)
    command_args = path
    if argument:
        command_args.append(argument)
    command_args.extend(remaining[1:])
    return project, command_args


__all__ = ["ExpressionError", "normalize_managed_args"]
