"""Public Python API for GWAY."""

from __future__ import annotations

from collections.abc import Mapping

from .dispatcher import Dispatcher
from .project import Project
from .registry import Registry


class CommandNamespace:
    """Lazy Python namespace that mirrors one managed project's command tree."""

    def __init__(
        self,
        dispatcher: Dispatcher,
        project_name: str,
        path: tuple[str, ...] = (),
    ) -> None:
        self._dispatcher = dispatcher
        self._project_name = project_name
        self._path = path

    def __getattr__(self, name: str) -> CommandNamespace:
        return CommandNamespace(
            self._dispatcher,
            self._project_name,
            (*self._path, name.replace("_", "-")),
        )

    def __call__(self, *args: object, **kwargs: object) -> object:
        return self._dispatcher.invoke(
            self._project_name,
            self._path,
            tuple(args),
            kwargs,
        )


class Gway:
    """Stable Python facade for managed GWAY projects."""

    def __init__(self, dispatcher: Dispatcher | None = None) -> None:
        self._dispatcher = dispatcher

    @property
    def dispatcher(self) -> Dispatcher:
        return self._dispatcher or Dispatcher()

    @property
    def registry(self) -> Registry:
        return self.dispatcher.registry

    def projects(self) -> list[Project]:
        """Return registered projects."""
        return self.registry.list()

    def project(self, name_or_alias: str) -> Project:
        """Return metadata for one registered project."""
        return self.registry.require(name_or_alias)

    def invoke(
        self,
        project_name: str,
        path: tuple[str, ...],
        args: tuple[object, ...] = (),
        kwargs: Mapping[str, object] | None = None,
    ) -> object:
        """Invoke one managed command using native Python arguments."""
        return self.dispatcher.invoke(project_name, path, args, kwargs or {})

    def __getattr__(self, name: str) -> CommandNamespace:
        project = self.registry.get(name)
        if project is None:
            raise AttributeError(f"project is not registered: {name}")
        return CommandNamespace(self.dispatcher, project.name)


gway = Gway()
# Compatibility alias for older code that imported ``gw`` directly.
gw = gway

__all__ = ["CommandNamespace", "Gway", "gway", "gw"]
