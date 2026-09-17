from __future__ import annotations

from collections.abc import Sequence

from ..command import Command, command_path_aliases
from ..explain import record
from .errors import CommandNotFound


def command_key(value: str) -> str:
    """Return the canonical lookup spelling for one command-path component."""
    return value.replace("_", "-").casefold()


def command_path_key(path: Sequence[str]) -> tuple[str, ...]:
    """Normalize command-path spelling while leaving argument values untouched."""
    return tuple(command_key(part) for part in path)


def resolve_command(
    commands: Sequence[Command],
    tokens: Sequence[str],
) -> tuple[Command, list[str]]:
    normalized_tokens = command_path_key(tokens)
    matches = [
        command
        for command in commands
        if len(tokens) >= len(command.path)
        and normalized_tokens[: len(command.path)] == command_path_key(command.path)
    ]
    resolution = "exact"
    if not matches:
        matches = [
            command
            for command in commands
            if len(tokens) >= len(command.path)
            and normalized_tokens[: len(command.path)]
            in tuple(
                command_path_key(alias)
                for alias in command_path_aliases(command.path)[1:]
            )
        ]
        resolution = "alias"
    if not matches:
        requested = " ".join(tokens) if tokens else "<command>"
        record("command.resolve", "command resolution failed", requested=requested)
        raise CommandNotFound(f"unknown command: {requested}")
    command = max(matches, key=lambda item: len(item.path))
    record(
        "command.resolve",
        "resolved managed command",
        requested=list(tokens),
        selected=list(command.path),
        resolution=resolution,
    )
    return command, list(tokens[len(command.path) :])


def resolve_default_command(
    commands: Sequence[Command],
    default_path: tuple[str, ...],
    tokens: Sequence[str],
) -> tuple[Command, list[str]]:
    normalized_default = command_path_key(default_path)
    for command in commands:
        if command_path_key(command.path) == normalized_default:
            record(
                "command.resolve",
                "resolved configured default command",
                requested=list(tokens),
                selected=list(command.path),
                resolution="default",
            )
            return command, list(tokens)
    record(
        "command.resolve",
        "configured default command was not found",
        selected=list(default_path),
        resolution="default",
    )
    raise CommandNotFound(
        f"configured default command not found: {' '.join(default_path)}"
    )


__all__ = ["resolve_command", "resolve_default_command"]
