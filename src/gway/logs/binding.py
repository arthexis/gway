from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


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
    environment: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_record(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "destination": self.destination,
            "configuration": dict(self.configuration),
            "environment": dict(self.environment),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> PublisherBinding | None:
        provider = record.get("provider")
        destination = record.get("destination")
        configuration = record.get("configuration", {})
        environment = record.get("environment", {})
        metadata = record.get("metadata", {})
        if (
            not isinstance(provider, str)
            or not provider
            or not isinstance(destination, str)
            or not destination
            or not isinstance(configuration, Mapping)
            or not isinstance(environment, Mapping)
            or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in environment.items()
            )
            or not isinstance(metadata, Mapping)
        ):
            return None
        return cls(
            provider=provider,
            destination=destination,
            configuration=dict(configuration),
            environment=dict(environment),
            metadata=dict(metadata),
        )


@dataclass(frozen=True)
class LogBinding:
    """Bind one consumer, optionally one service, to a logging publisher."""

    consumer: str
    publisher: PublisherBinding
    service: ServiceRef | None = None


__all__ = ["LogBinding", "PublisherBinding", "ServiceRef"]
