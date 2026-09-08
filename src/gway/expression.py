from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass


class ExpressionError(ValueError):
    """Raised when compact managed-command expression syntax is malformed."""


@dataclass(frozen=True)
class ManagedBranch:
    """One managed CLI fallback branch or terminal literal value."""

    project: str | None = None
    args: tuple[str, ...] = ()
    literal: str | None = None

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
    """Normalize dotted/colon managed CLI syntax into dispatcher arguments.

    Dots explicitly separate project/command path components. A colon marks an
    explicit call boundary and optionally contributes one argument. Literal
    trailing-colon handling is performed by :func:`parse_managed_branches`
    before this lower-level normalizer is used.
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


def _command_branch(text: str) -> ManagedBranch:
    try:
        words = shlex.split(text)
    except ValueError as exc:
        raise ExpressionError(f"invalid managed command expression: {text!r}") from exc
    if not words:
        raise ExpressionError("managed fallback branch is empty")
    project, args = normalize_managed_args(words)
    return ManagedBranch(project=project, args=tuple(args))


def parse_managed_branches(args: Sequence[str]) -> tuple[ManagedBranch, ...]:
    """Parse Sigil-style CLI fallback and literal syntax.

    ``|`` separates fallback command expressions. ``|:literal`` is a terminal
    literal fallback. A trailing colon with no right-hand caller is also a
    literal, so ``gway ready:`` returns ``ready``. When no fallback operator is
    present, normal shell argument boundaries are preserved.
    """
    if not args:
        raise ExpressionError("managed command expression is empty")

    joined = " ".join(args)
    if "|" not in joined:
        if len(args) == 1 and args[0].endswith(":"):
            return (ManagedBranch(literal=args[0][:-1]),)
        project, command_args = normalize_managed_args(args)
        return (ManagedBranch(project=project, args=tuple(command_args)),)

    branches: list[ManagedBranch] = []
    for raw_branch in joined.split("|"):
        branch = raw_branch.strip()
        if not branch:
            raise ExpressionError("managed fallback branch is empty")
        if branch.startswith(":"):
            branches.append(ManagedBranch(literal=branch[1:]))
            break
        if branch.endswith(":"):
            branches.append(ManagedBranch(literal=branch[:-1].strip()))
            break
        branches.append(_command_branch(branch))

    return tuple(branches)


__all__ = [
    "ExpressionError",
    "ManagedBranch",
    "normalize_managed_args",
    "parse_managed_branches",
]
