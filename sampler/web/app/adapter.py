"""Minimal in-memory execution adapter for framework-neutral AppSpecs."""

from .appspec import AppSpec, RouteSpec


class ApplicationDispatchError(RuntimeError):
    """Base error for in-memory application dispatch failures."""


class RouteNotFound(ApplicationDispatchError):
    """Raised when an application has no route for a requested path."""


class MethodNotAllowed(ApplicationDispatchError):
    """Raised when a route exists but not for the requested HTTP method."""


class HandlerNotFound(ApplicationDispatchError):
    """Raised when a RouteSpec references an unavailable Gway operation."""


class InMemoryAdapter:
    """Dispatch AppSpec routes directly through an existing Gateway runtime."""

    def __init__(self, gateway, app: AppSpec):
        if not isinstance(app, AppSpec):
            raise TypeError("in-memory adapter requires an AppSpec")
        self.gateway = gateway
        self.app = app

    def resolve(self, route: str, method: str = "GET") -> RouteSpec:
        """Resolve one concrete route/method mapping from the application."""
        route = str(route)
        method = str(method).upper()
        path_matches = tuple(item for item in self.app.routes if item.route == route)
        if not path_matches:
            raise RouteNotFound(f"No route registered for {route}")

        for item in path_matches:
            if item.method == method:
                return item

        allowed = ", ".join(item.method for item in path_matches)
        raise MethodNotAllowed(
            f"{method} is not allowed for {route}; allowed methods: {allowed}"
        )

    def resolve_handler(self, mapping: RouteSpec):
        """Resolve one route's late-bound canonical handler operation."""
        from gway.dispatch import resolve_operation
        from gway.tokens import tokenize

        try:
            resolution = resolve_operation(self.gateway, tokenize(mapping.handler))
        except LookupError as exception:
            raise HandlerNotFound(
                f"Route {mapping.method} {mapping.route} references unavailable "
                f"handler {mapping.handler!r}"
            ) from exception
        if resolution.arguments:
            raise HandlerNotFound(
                f"Route {mapping.method} {mapping.route} does not reference a "
                f"canonical handler operation: {mapping.handler!r}"
            )
        return resolution.callable

    def invoke(self, mapping: RouteSpec, arguments=None):
        """Invoke one already-resolved mapping with ordinary handler arguments."""
        arguments = {} if arguments is None else dict(arguments)

        from gway.binding import coerce_native_arguments

        handler = self.resolve_handler(mapping)
        arguments = coerce_native_arguments(
            handler,
            arguments,
            runtime=self.gateway,
        )
        return self.gateway(mapping.handler, **arguments)

    def request(self, route: str, method: str = "GET", arguments=None):
        """Invoke one route while keeping transport fields separate from handler inputs."""
        mapping = self.resolve(route, method)
        return self.invoke(mapping, arguments=arguments)
