from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from ..config import GwayPaths
from ..project import Project
from ..sigils import resolve_cli_values
from .manifest import ServiceError

_UNRESOLVED_SIGIL = re.compile(r"(?<!\[)%?\[(?!\[)(?P<expression>[^\[\]]+?)\](?!\])")


def _reject_unresolved(original: str, rendered: str, service: str) -> None:
    """Reject service Sigils that survive ordinary noninteractive resolution."""
    for match in _UNRESOLVED_SIGIL.finditer(original):
        token = match.group(0)
        if token in rendered:
            raise ServiceError(
                f"service {service!r} contains unresolved Sigil {token!r}"
            )


def resolve_service_values(
    values: Sequence[str],
    project: Project,
    service: str,
    *,
    paths: GwayPaths | None = None,
) -> list[str]:
    """Resolve service templates with the owning project's Sigil context.

    Ordinary noninteractive Sigil resolution preserves unknown expressions so
    callers can decide how to handle them. Managed services fail closed instead:
    unresolved Sigils must never be serialized into a systemd unit.
    """
    rendered = resolve_cli_values(
        values,
        project,
        ("service", service),
        paths=paths,
    )
    for original, value in zip(values, rendered, strict=True):
        _reject_unresolved(original, value, service)
    return rendered


def resolve_service_config(
    config: Mapping[str, Any],
    project: Project,
    service: str,
    *,
    paths: GwayPaths | None = None,
) -> dict[str, Any]:
    """Resolve supported string-bearing service fields without changing validation.

    Invalid/non-string shapes are intentionally preserved for the existing
    service renderer to validate. Only command strings and environment string
    values participate in Sigil resolution.
    """
    resolved = dict(config)

    command = config.get("command")
    if isinstance(command, str):
        resolved["command"] = resolve_service_values(
            [command], project, service, paths=paths
        )[0]
    elif isinstance(command, (list, tuple)) and all(
        isinstance(value, str) for value in command
    ):
        resolved["command"] = resolve_service_values(
            command, project, service, paths=paths
        )

    environment = config.get("environment")
    if isinstance(environment, Mapping):
        items = list(environment.items())
        string_indexes = [
            index for index, (_, value) in enumerate(items) if isinstance(value, str)
        ]
        if string_indexes:
            values = [str(items[index][1]) for index in string_indexes]
            replacements = iter(
                resolve_service_values(values, project, service, paths=paths)
            )
            environment_copy = dict(environment)
            for index in string_indexes:
                key = items[index][0]
                environment_copy[key] = next(replacements)
            resolved["environment"] = environment_copy

    return resolved


__all__ = ["resolve_service_config", "resolve_service_values"]
