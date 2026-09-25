"""Framework-neutral application topology models."""

from dataclasses import dataclass


def _route_from_callable(callable_name: str) -> str:
    """Infer a conventional route from a Gway callable identity."""
    subject = callable_name.rsplit(".", 1)[-1].replace("_", "-")
    return f"/{subject}"


@dataclass(frozen=True)
class RouteSpec:
    """Describe one concrete HTTP route mapping."""

    route: str
    method: str
    handler: str
    name: str | None = None


@dataclass(frozen=True)
class ViewSpec:
    """Describe one framework-neutral application view."""

    callable_name: str
    route: str | None = None
    methods: tuple[str, ...] = ("GET",)
    name: str | None = None

    def __post_init__(self):
        methods = tuple(dict.fromkeys(method.upper() for method in self.methods))
        if not methods:
            methods = ("GET",)
        object.__setattr__(self, "methods", methods)

    @property
    def resolved_route(self) -> str:
        """Return the explicit route or the route inferred from the callable name."""
        return self.route or _route_from_callable(self.callable_name)

    @property
    def routes(self) -> tuple[RouteSpec, ...]:
        """Compile this view into deterministic concrete route mappings."""
        return tuple(
            RouteSpec(
                route=self.resolved_route,
                method=method,
                handler=self.callable_name,
                name=self.name,
            )
            for method in self.methods
        )


@dataclass(frozen=True)
class AppSpec:
    """Describe an application independently from its serving framework."""

    name: str | None = None
    views: tuple[ViewSpec, ...] = ()

    @property
    def routes(self) -> tuple[RouteSpec, ...]:
        """Return all concrete route mappings in composition order."""
        return tuple(route for view in self.views for route in view.routes)

    def add(self, view: ViewSpec):
        """Return a copy containing one additional non-conflicting view."""
        if view in self.views:
            return self

        occupied = {(route.route, route.method) for route in self.routes}
        conflicts = [
            route for route in view.routes if (route.route, route.method) in occupied
        ]
        if conflicts:
            route = conflicts[0]
            raise ValueError(
                f"Conflicting view for {route.method} {route.route}: "
                f"{view.callable_name}"
            )

        return AppSpec(name=self.name, views=(*self.views, view))
