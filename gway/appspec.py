"""Framework-neutral application topology models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewSpec:
    """Describe one framework-neutral application view."""

    callable_name: str
    endpoint: str | None = None
    methods: tuple[str, ...] = ("GET",)
    name: str | None = None


@dataclass(frozen=True)
class AppSpec:
    """Describe an application independently from its serving framework."""

    name: str | None = None
    views: tuple[ViewSpec, ...] = ()

    def add(self, view: ViewSpec):
        """Return a copy containing one additional view."""
        if view in self.views:
            return self
        return AppSpec(name=self.name, views=(*self.views, view))
