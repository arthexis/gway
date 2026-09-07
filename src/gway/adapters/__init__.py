from __future__ import annotations

from collections.abc import Callable

from gway.project import Project

from .base import ProjectAdapter

AdapterFactory = Callable[[Project], ProjectAdapter]


class AdapterError(ValueError):
    pass


class AdapterRegistry:
    """Map manifest adapter types to adapter factories."""

    def __init__(self) -> None:
        self._factories: dict[str, AdapterFactory] = {}

    def register(self, adapter_type: str, factory: AdapterFactory) -> None:
        if not adapter_type:
            raise ValueError("adapter type must not be empty")
        self._factories[adapter_type] = factory

    def create(self, project: Project) -> ProjectAdapter:
        try:
            factory = self._factories[project.adapter_type]
        except KeyError as exc:
            raise AdapterError(f"unsupported adapter: {project.adapter_type}") from exc
        return factory(project)


__all__ = ["AdapterError", "AdapterFactory", "AdapterRegistry", "ProjectAdapter"]
