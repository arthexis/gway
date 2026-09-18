from __future__ import annotations

from typing import Protocol, runtime_checkable

from .binding import PublisherBinding, ServiceRef


@runtime_checkable
class LogPublisherProvider(Protocol):
    """Provider contract for provisioning one usable logging publisher binding."""

    name: str

    def provision(
        self,
        *,
        destination: str,
        consumer: str,
        service: ServiceRef | None = None,
        current: PublisherBinding | None = None,
    ) -> PublisherBinding: ...


__all__ = ["LogPublisherProvider"]
