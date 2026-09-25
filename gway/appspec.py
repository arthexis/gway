"""Framework-neutral application topology models."""

from dataclasses import dataclass


def _route_from_callable(callable_name: str) -> str:
    """Infer a conventional route from a Gway callable identity."""
    subject = callable_name.rsplit(".", 1)[-1].replace("_", "-")
    return f"/{subject}"


def _join_route(base: str | None, route: str) -> str:
    """Compose an application base route with one view-local route."""
    base = "/" if base is None else str(base).strip()
    route = str(route).strip()
    if not base or base == "/":
        return "/" + route.strip("/") if route != "/" else "/"
    if not route or route == "/":
        return "/" + base.strip("/")
    return "/" + "/".join((base.strip("/"), route.strip("/")))


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
    topic: str | None = None
    route: str = "/"
    views: tuple[ViewSpec, ...] = ()

    def __post_init__(self):
        topic = None if self.topic is None else str(self.topic).strip().strip(".")
        name = self.name
        if name is None and topic:
            name = topic.rsplit(".", 1)[-1]
        route = str(self.route or "/").strip()
        route = "/" if route == "/" else "/" + route.strip("/")
        object.__setattr__(self, "topic", topic or None)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "route", route)

        unique_views = []
        occupied = set()
        for view in self.views:
            if view in unique_views:
                continue
            for mapping in self._routes_for(view):
                key = (mapping.route, mapping.method)
                if key in occupied:
                    raise ValueError(
                        f"Conflicting view for {mapping.method} {mapping.route}: "
                        f"{view.callable_name}"
                    )
                occupied.add(key)
            unique_views.append(view)
        object.__setattr__(self, "views", tuple(unique_views))

    def _routes_for(self, view: ViewSpec) -> tuple[RouteSpec, ...]:
        return tuple(
            RouteSpec(
                route=_join_route(self.route, mapping.route),
                method=mapping.method,
                handler=mapping.handler,
                name=mapping.name,
            )
            for mapping in view.routes
        )

    @property
    def routes(self) -> tuple[RouteSpec, ...]:
        """Return all concrete route mappings in composition order."""
        return tuple(mapping for view in self.views for mapping in self._routes_for(view))

    def add(self, view: ViewSpec):
        """Return a copy containing one additional non-conflicting view."""
        if view in self.views:
            return self
        return AppSpec(
            name=self.name,
            topic=self.topic,
            route=self.route,
            views=(*self.views, view),
        )

    def replace(self, view: ViewSpec):
        """Replace only route/method mappings claimed by the supplied view."""
        replacements = {
            (mapping.route, mapping.method) for mapping in self._routes_for(view)
        }
        retained = []
        for existing in self.views:
            remaining_methods = tuple(
                method
                for method in existing.methods
                if (
                    _join_route(self.route, existing.resolved_route),
                    method,
                )
                not in replacements
            )
            if not remaining_methods:
                continue
            if remaining_methods == existing.methods:
                retained.append(existing)
                continue
            retained.append(
                ViewSpec(
                    existing.callable_name,
                    route=existing.route,
                    methods=remaining_methods,
                    name=existing.name,
                )
            )
        return AppSpec(
            name=self.name,
            topic=self.topic,
            route=self.route,
            views=(*retained, view),
        )
