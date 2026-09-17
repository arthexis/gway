from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping


@dataclass(frozen=True)
class ServiceRef:
    """Stable reference to one named service declared by a GWAY project."""

    project: str
    service: str = "default"


@dataclass(frozen=True)
class PublisherBinding:
    """Opaque provider-owned configuration for one logging destination."""

    provider: str
    destination: str
    configuration: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LogBinding:
    """Bind one consumer, optionally one service, to a logging publisher."""

    consumer: str
    publisher: PublisherBinding
    service: ServiceRef | None = None


__all__ = ["LogBinding", "PublisherBinding", "ServiceRef"]
