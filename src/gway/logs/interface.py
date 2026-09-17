from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..project import Project
from .binding import PublisherBinding, ServiceRef


@runtime_checkable
class LogPublisherProvider(Protocol):
    """Provider contract for provisioning one usable logging publisher binding."""

    name: str

    def provision(
        self,
        *,
        destination: str,
        consumer: Project,
        service: ServiceRef | None = None,
    ) -> PublisherBinding: ...


__all__ = ["LogPublisherProvider"]
