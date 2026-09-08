from __future__ import annotations

import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass


MANAGED_EXPRESSION_PROJECT = "\0gway-expression"


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


def _split_compact(token: str) -> tuple[list[str], str | None]:
    path_text, separator, argument = token.partition(":")
    path = path_text.split(".")
    if not path_text or any(not part for part in path):
        raise ExpressionError(f"invalid managed command expression: {token!r}")
    return path, argument if separator else None


def normalize_managed_args(args: Sequence[str]) -> tuple[str, list[str]]:
    """Normalize dotted/colon managed CLI syntax into dispatcher arguments."""
    if not args:
        raise ExpressionError("managed command expression is empty")

    expression = " ".join(args)
    if "|" in expression or expression.endswith(":"):
        return MANAGED_EXPRESSION_PROJECT, [expression]

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


def _command_branch(text: str, *, operator: str | None = None) -> ManagedBranch:
    try:
        words = shlex.split(text)
    except ValueError as exc:
        raise ExpressionError(f"invalid managed command expression: {text!r}") from exc
    if not words:
        raise ExpressionError("managed fallback branch is empty")

    first = words[0]
    remaining = list(words[1:])
    if "." in first or ":" in first:
        path, argument = _split_compact(first)
        project = path[0]
        command_args = path[1:]
        if argument:
            command_args.append(argument)
        command_args.extend(remaining)
        return ManagedBranch(project=project, args=tuple(command_args), operator=operator)

    project = first
    if remaining and ("." in remaining[0] or ":" in remaining[0]):
        path, argument = _split_compact(remaining[0])
        command_args = path
        if argument:
            command_args.append(argument)
        command_args.extend(remaining[1:])
        return ManagedBranch(project=project, args=tuple(command_args), operator=operator)

    return ManagedBranch(project=project, args=tuple(remaining), operator=operator)


def parse_managed_branches(expression: str) -> tuple[ManagedBranch, ...]:
    """Parse loose ``|`` and strict ``||`` fallback chains.

    ``|`` advances on any falsey result. ``||`` advances only on a missing
    command/project, ``None``, or an empty set/frozenset. ``|:literal`` and
    ``||:literal`` are terminal literal fallbacks.
    """
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
            branches.append(ManagedBranch(literal=branch[1:], operator=operator))
            break
        if branch.endswith(":"):
            branches.append(
                ManagedBranch(literal=branch[:-1].strip(), operator=operator)
            )
            break
        branches.append(_command_branch(branch, operator=operator))

    return tuple(branches)


__all__ = [
    "ExpressionError",
    "MANAGED_EXPRESSION_PROJECT",
    "ManagedBranch",
    "normalize_managed_args",
    "parse_managed_branches",
]
