"""Framework-neutral application topology models."""

from dataclasses import dataclass


def _route_from_callable(callable_name: str) -> str:
    """Infer a conventional route from a Gway callable identity."""
    subject = callable_name.rsplit(".", 1)[-1].replace("_", "-")
    return f"/{subject}"


def _route_pattern_key(route: str) -> tuple[str, ...]:
    """Normalize named route segments for conflict detection."""
    parts = route.strip("/").split("/") if route != "/" else ()
    return tuple(
        "{}" if part.startswith("{") and part.endswith("}") else part
        for part in parts
    )


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
class BindingSpec:
    """Describe one declared HTTP input bound to a handler argument."""

    name: str
    source: str
    key: str | None = None

    def __post_init__(self):
        name = str(self.name).strip()
        source = str(self.source).strip().casefold()
        if self.key is None:
            key = name.replace("_", "-") if source == "header" else name
        else:
            key = str(self.key).strip()
        if not name:
            raise ValueError("binding name cannot be empty")
        if source not in {"query", "path", "header", "body"}:
            raise ValueError(f"unsupported binding source: {source!r}")
        if not key:
            raise ValueError("binding key cannot be empty")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "key", key)


@dataclass(frozen=True)
class RouteSpec:
    """Describe one concrete HTTP route mapping."""

    route: str
    method: str
    handler: str | None = None
    name: str | None = None
    bindings: tuple[BindingSpec, ...] = ()
    body_model: str | None = None
    response_model: str | None = None
    static: str | None = None
    directory: bool = False
    content_type: str | None = None


@dataclass(frozen=True)
class ViewSpec:
    """Describe one framework-neutral application view."""

    callable_name: str | None = None
    route: str | None = None
    methods: tuple[str, ...] = ("GET",)
    name: str | None = None
    bindings: tuple[BindingSpec, ...] = ()
    body_model: str | None = None
    response_model: str | None = None
    static: str | None = None
    directory: bool = False
    content_type: str | None = None

    def __post_init__(self):
        static = None if self.static is None else str(self.static).strip()
        if bool(self.callable_name) == bool(static):
            raise ValueError("view requires exactly one of handler or static source")
        if static and self.route is None:
            raise ValueError("static view requires an explicit route")
        if self.directory and not static:
            raise ValueError("directory view requires a static source")
        methods = tuple(dict.fromkeys(method.upper() for method in self.methods))
        if not methods:
            methods = ("GET", "HEAD") if static else ("GET",)
        if static and methods == ("GET",):
            methods = ("GET", "HEAD")
        bindings = tuple(self.bindings)
        names = set()
        for binding in bindings:
            if not isinstance(binding, BindingSpec):
                raise TypeError("view bindings must be BindingSpec instances")
            if binding.name in names:
                raise ValueError(f"duplicate view binding: {binding.name}")
            names.add(binding.name)
        if self.body_model and not any(
            binding.source == "body" for binding in bindings
        ):
            raise ValueError("body_model requires at least one body binding")
        object.__setattr__(self, "methods", methods)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "static", static or None)

    @property
    def resolved_route(self) -> str:
        """Return the explicit route or the route inferred from the callable name."""
        if self.route is not None:
            return self.route
        return _route_from_callable(self.callable_name)

    @property
    def routes(self) -> tuple[RouteSpec, ...]:
        """Compile this view into deterministic concrete route mappings."""
        return tuple(
            RouteSpec(
                route=self.resolved_route,
                method=method,
                handler=self.callable_name,
                name=self.name,
                bindings=self.bindings,
                body_model=self.body_model,
                response_model=self.response_model,
                static=self.static,
                directory=self.directory,
                content_type=self.content_type,
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
                key = (_route_pattern_key(mapping.route), mapping.method)
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
                bindings=mapping.bindings,
                body_model=mapping.body_model,
                response_model=mapping.response_model,
                static=mapping.static,
                directory=mapping.directory,
                content_type=mapping.content_type,
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
            (_route_pattern_key(mapping.route), mapping.method)
            for mapping in self._routes_for(view)
        }
        retained = []
        for existing in self.views:
            remaining_methods = tuple(
                method
                for method in existing.methods
                if (
                    _route_pattern_key(
                        _join_route(self.route, existing.resolved_route)
                    ),
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
                    bindings=existing.bindings,
                    body_model=existing.body_model,
                    response_model=existing.response_model,
                    static=existing.static,
                    directory=existing.directory,
                    content_type=existing.content_type,
                )
            )
        return AppSpec(
            name=self.name,
            topic=self.topic,
            route=self.route,
            views=(*retained, view),
        )
