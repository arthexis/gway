"""Ordered operation fallback routes for GWAY runtimes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OperationRoute:
    """One ordered source that may expand unresolved operations."""

    name: str
    expand: object

    def __post_init__(self):
        name = str(self.name).strip()
        if not name:
            raise ValueError("Operation route requires a non-empty name")
        if not callable(self.expand):
            raise TypeError("Operation route expand hook must be callable")
        object.__setattr__(self, "name", name)

    def try_expand(self, runtime, tokens):
        """Try to expand this route for one unresolved command."""
        return bool(self.expand(runtime, tokens))


class OperationRoutes:
    """Ordered registry of operation fallback routes."""

    def __init__(self):
        self._routes = []

    def register(self, name, expand):
        """Append one fallback route and return its immutable route record."""
        if any(route.name == str(name).strip() for route in self._routes):
            raise ValueError(f"Operation route already registered: {name}")
        route = OperationRoute(name=name, expand=expand)
        self._routes.append(route)
        return route

    def expand(self, runtime, tokens):
        """Try routes in registration order until one expands the runtime."""
        for route in self._routes:
            if route.try_expand(runtime, tokens):
                return True
        return False

    @property
    def routes(self):
        """Return registered routes in resolution order."""
        return tuple(self._routes)
