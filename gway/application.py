"""Recipe-facing application composition operations."""

from .appspec import AppSpec, ViewSpec


class Controller:
    """Compose framework-neutral application specifications through Gway operations."""

    def __init__(self, gateway):
        self.gateway = gateway

    def setup_app(self, name=None, *, topic=None, route="/", mutate=False):
        """Create a framework-neutral application specification.

        Args:
            name: Optional application name; inferred from the topic leaf when omitted.
            topic: Optional semantic handler-resolution root.
            route: Optional base route composed with each view-local route.
        """
        del mutate
        return AppSpec(name=name, topic=topic, route=route)

    def _canonical_handler(self, handler, *, app=None):
        raw = str(handler).strip()
        if not raw:
            raise ValueError("view handler must be a non-empty operation identity")

        from .dispatch import resolve_operation
        from .tokens import tokenize

        canonical = raw.replace(" ", ".")
        candidates = [canonical]
        if app is not None and app.topic and "." not in canonical:
            candidates.insert(0, f"{app.topic}.{canonical}")

        resolution = None
        for candidate in candidates:
            try:
                resolution = resolve_operation(self.gateway, tokenize(candidate))
            except LookupError:
                continue
            if not resolution.arguments:
                break
        else:
            resolution = None
        if resolution is not None and not resolution.arguments:
            return self.gateway.ops.canonical_name(
                resolution.callable,
                resolution.candidate,
            )

        normalized = canonical.replace("-", "_")
        matches = []
        for name, record in self.gateway.ops._registry.records.items():
            leaf = name.rsplit(".", 1)[-1].replace("-", "_")
            if leaf == normalized:
                matches.append((name, record.callable))

        if len(matches) == 1:
            return matches[0][0]
        if len(matches) > 1:
            names = ", ".join(name for name, _ in sorted(matches))
            raise LookupError(
                f"Ambiguous view handler {raw!r}; use a canonical operation identity: {names}"
            )
        raise LookupError(f"Unknown view handler operation: {raw}")

    def view_app(
        self,
        handler: object,
        *,
        app: AppSpec,
        route=None,
        methods: tuple[str, ...] = (),
        method=None,
        name=None,
        replace: bool = False,
        mutate=False,
    ):
        """Add one handler-backed view to the current application.

        Args:
            handler: Canonical or uniquely-resolvable Gway operation identity.
            app: Current AppSpec, normally inherited from semantic context.
            route: Explicit HTTP route; otherwise infer it from the handler.
            methods: HTTP methods as a sequence (CLI: comma-separated).
            method: Singular HTTP method convenience alias.
            name: Optional view name.
            replace: Replace existing mappings for the same route/methods.
        """
        del mutate
        if not isinstance(app, AppSpec):
            raise TypeError("view app requires an AppSpec")
        if method is not None and methods:
            raise ValueError("use either --method or --methods, not both")

        selected_methods = (method,) if method is not None else methods
        canonical = self._canonical_handler(handler, app=app)
        view = ViewSpec(
            canonical,
            route=route,
            methods=selected_methods or ("GET",),
            name=name,
        )
        return app.replace(view) if replace else app.add(view)

    def start_app(
        self,
        *,
        app: AppSpec,
        host: str = "127.0.0.1",
        port: int = 8000,
    ):
        """Run the current application locally in the foreground.

        Args:
            app: Current AppSpec, normally inherited from semantic context.
            host: Local bind address.
            port: Local TCP port.
        """
        if not isinstance(app, AppSpec):
            raise TypeError("start app requires an AppSpec")

        from .appserver import serve_app

        return serve_app(
            self.gateway,
            app,
            host=host,
            port=port,
        )


def register(gateway):
    """Register application composition operations on one Gateway."""
    controller = Controller(gateway)
    gateway._application_controller = controller
    gateway.setup_app = gateway.wrap(
        "setup.app",
        controller.setup_app,
        op="setup",
        sub="app",
    )
    gateway.view_app = gateway.wrap(
        "view.app",
        controller.view_app,
        op="view",
        sub="app",
    )
    gateway.ops.register_alias("view", gateway.view_app)
    gateway.start_app = gateway.wrap(
        "start.app",
        controller.start_app,
        op="start",
        sub="app",
    )
    return controller
