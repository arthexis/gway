from __future__ import annotations

import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass

MANAGED_EXPRESSION_PROJECT = "\0gway-expression"
STRUCTURED_ARG_PREFIX = "\0gway-arg:"
STRUCTURED_KWARG_PREFIX = "\0gway-kw:"
STRUCTURED_TUPLE_PREFIX = "\0gway-tuple:"


class ExpressionError(ValueError):
    """Raised when compact managed-command expression syntax is malformed."""


@dataclass(frozen=True)
class ManagedBranch:
    """One managed CLI fallback branch or terminal literal value."""

    project: str | None = None
    args: tuple[str, ...] = ()
    literal: str | None = None
    operator: str | None = None

    @property
    def is_literal(self) -> bool:
        return self.literal is not None


def _split_compact_path(token: str) -> list[str]:
    path = token.split(".")
    if not token or any(not part for part in path):
        raise ExpressionError(f"invalid managed command expression: {token!r}")
    return path


def _normalize_argument_value(value: str) -> str:
    """Normalize whitespace and retain tuple intent for comma-delimited values."""
    value = value.strip()
    if "," not in value:
        return value
    members = ",".join(item.strip() for item in value.split(","))
    return f"{STRUCTURED_TUPLE_PREFIX}{members}"


def _structured_argument(segment: str) -> str:
    """Encode one colon-delimited argument for later command-aware dispatch."""
    segment = segment.strip()
    if not segment:
        raise ExpressionError("managed call argument is empty")

    # :=value explicitly means positional, even when value itself contains '='.
    if segment.startswith("="):
        value = _normalize_argument_value(segment[1:].strip())
        return f"{STRUCTURED_ARG_PREFIX}{value}"

    if "=" in segment:
        name, value = segment.split("=", 1)
        name = name.strip()
        if not name.isidentifier():
            raise ExpressionError(f"invalid managed keyword argument: {segment!r}")
        value = _normalize_argument_value(value)
        return f"{STRUCTURED_KWARG_PREFIX}{name}={value}"

    return f"{STRUCTURED_ARG_PREFIX}{_normalize_argument_value(segment)}"


def _target_words(text: str) -> list[str]:
    try:
        words = shlex.split(text)
    except ValueError as exc:
        raise ExpressionError(f"invalid managed command expression: {text!r}") from exc
    if not words:
        raise ExpressionError("managed command expression is empty")
    return words


def _target_branch(
    target: str,
    arguments: Sequence[str] = (),
    *,
    operator: str | None = None,
) -> ManagedBranch:
    words = _target_words(target.strip())
    first = words[0]
    remaining = list(words[1:])

    if "." in first:
        path = _split_compact_path(first)
        project = path[0]
        command_args = path[1:]
        command_args.extend(remaining)
    else:
        project = first
        if remaining and "." in remaining[0]:
            path = _split_compact_path(remaining[0])
            command_args = path
            command_args.extend(remaining[1:])
        else:
            command_args = remaining

    command_args.extend(_structured_argument(argument) for argument in arguments)
    return ManagedBranch(project=project, args=tuple(command_args), operator=operator)


def _command_branch(text: str, *, operator: str | None = None) -> ManagedBranch:
    if ":" not in text:
        return _target_branch(text, operator=operator)

    parts = text.split(":")
    target = parts[0].strip()
    arguments = parts[1:]
    if not target:
        raise ExpressionError(f"invalid managed command expression: {text!r}")
    return _target_branch(target, arguments, operator=operator)


def normalize_managed_args(args: Sequence[str]) -> tuple[str, list[str]]:
    """Normalize managed CLI syntax into dispatcher arguments/expression mode."""
    if not args:
        raise ExpressionError("managed command expression is empty")

    expression = " ".join(args).strip()
    if expression.startswith(":"):
        raise ExpressionError(f"invalid managed command expression: {expression!r}")
    if "|" in expression or ":" in expression:
        return MANAGED_EXPRESSION_PROJECT, [expression]

    first = args[0]
    remaining = list(args[1:])

    if "." in first:
        path = _split_compact_path(first)
        return path[0], [*path[1:], *remaining]

    project = first
    if not remaining:
        return project, []

    command_head = remaining[0]
    if "." in command_head:
        path = _split_compact_path(command_head)
        return project, [*path, *remaining[1:]]

    return project, remaining


def parse_managed_branches(expression: str) -> tuple[ManagedBranch, ...]:
    """Parse calls plus loose ``|`` and strict ``||`` fallback chains.

    Colons separate call arguments, ``name=value`` marks keyword arguments,
    ``:=value`` explicitly marks a positional argument, and commas create one
    tuple argument. ``|`` advances on any falsey result while ``||`` advances
    only on missing/None/empty-set values.
    """
    expression = expression.strip()
    if not expression:
        raise ExpressionError("managed command expression is empty")

    if "|" not in expression:
        if expression.endswith(":"):
            return (ManagedBranch(literal=expression[:-1].strip()),)
        return (_command_branch(expression),)

    parts = re.split(r"(\|\|?)", expression)
    branches: list[ManagedBranch] = []
    first = parts[0].strip()
    if not first:
        raise ExpressionError("managed fallback branch is empty")
    branches.append(_command_branch(first))

    for index in range(1, len(parts), 2):
        operator = parts[index]
        branch = parts[index + 1].strip()
        if not branch:
            raise ExpressionError("managed fallback branch is empty")
        if branch.startswith(":"):
            branches.append(ManagedBranch(literal=branch[1:].strip(), operator=operator))
            break
        if branch.endswith(":"):
            branches.append(ManagedBranch(literal=branch[:-1].strip(), operator=operator))
            break
        branches.append(_command_branch(branch, operator=operator))

    return tuple(branches)


__all__ = [
    "ExpressionError",
    "MANAGED_EXPRESSION_PROJECT",
    "ManagedBranch",
    "STRUCTURED_ARG_PREFIX",
    "STRUCTURED_KWARG_PREFIX",
    "STRUCTURED_TUPLE_PREFIX",
    "normalize_managed_args",
    "parse_managed_branches",
]
