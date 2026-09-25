"""Recipe-facing application composition operations."""

from .appspec import AppSpec, ViewSpec


class Controller:
    """Compose framework-neutral application specifications through Gway operations."""

    def __init__(self, gateway):
        self.gateway = gateway

    def setup_app(self, name=None):
        """Create a new framework-neutral application specification.

        Args:
            name: Optional application name.
        """
        return AppSpec(name=name)

    def _canonical_handler(self, handler):
        raw = str(handler).strip()
        if not raw:
            raise ValueError("view handler must be a non-empty operation identity")

        canonical = raw.replace(" ", ".")
        direct = self.gateway.ops.resolve(canonical)
        if direct is not None:
            return self.gateway.ops.canonical_name(direct, canonical)

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
        if not isinstance(app, AppSpec):
            raise TypeError("view app requires an AppSpec")
        if method is not None and methods:
            raise ValueError("use either --method or --methods, not both")

        selected_methods = (method,) if method is not None else methods
        canonical = self._canonical_handler(handler)
        view = ViewSpec(
            canonical,
            route=route,
            methods=selected_methods or ("GET",),
            name=name,
        )
        return app.replace(view) if replace else app.add(view)


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
    return controller
