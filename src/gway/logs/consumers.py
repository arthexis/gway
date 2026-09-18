from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from ..dispatcher.errors import DispatchError
from ..project import Project

_CONSUMER_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
ConsumerResolver = Callable[[str], Project | None]


def normalize_consumers(values: Sequence[str]) -> tuple[str, ...]:
    """Normalize singular/plural consumer arguments into safe unique names."""
    consumers: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in raw.split(","):
            value = part.strip()
            if not value:
                continue
            if not _CONSUMER_NAME.fullmatch(value):
                raise DispatchError(f"invalid log consumer name: {value!r}")
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            consumers.append(value)
    return tuple(consumers)


def consumer_identity(
    value: str,
    resolve_consumer: ConsumerResolver | None,
) -> tuple[str, set[str]]:
    project = resolve_consumer(value) if resolve_consumer is not None else None
    if project is None:
        return value, {value.casefold()}
    identities = {item.casefold() for item in (project.name, *project.aliases)}
    return project.name, identities


def canonical_consumers(
    values: Sequence[str],
    resolve_consumer: ConsumerResolver | None,
) -> tuple[tuple[str, ...], set[str]]:
    canonical: list[str] = []
    identities: set[str] = set()
    seen: set[str] = set()
    for value in normalize_consumers(values):
        name, aliases = consumer_identity(value, resolve_consumer)
        identities.update(aliases)
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            canonical.append(name)
    return tuple(canonical), identities


__all__ = [
    "ConsumerResolver",
    "canonical_consumers",
    "consumer_identity",
    "normalize_consumers",
]
