"""Public Python API for GWAY."""

from __future__ import annotations

from .project import Project
from .registry import Registry


class Gway:
    """Stable Python facade for managed GWAY projects.

    The facade and CLI share the same registry. Managed command namespaces will
    be attached to this object by the dispatcher/adapters in later chunks.
    """

    @property
    def registry(self) -> Registry:
        return Registry()

    def projects(self) -> list[Project]:
        """Return registered projects."""
        return self.registry.list()

    def project(self, name_or_alias: str) -> Project:
        """Return metadata for one registered project."""
        return self.registry.require(name_or_alias)

    def __getattr__(self, name: str):
        project = self.registry.get(name)
        if project is not None:
            raise AttributeError(
                f"managed command dispatch for project {project.name!r} is not "
                "implemented yet; see PLAN.md Chunk 12"
            )
        raise AttributeError(f"project is not registered: {name}")


gway = Gway()
# Compatibility alias for older code that imported ``gw`` directly.
gw = gway

__all__ = ["Gway", "gway", "gw"]
