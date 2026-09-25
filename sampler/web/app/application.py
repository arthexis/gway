"""Recipe-facing application composition operations."""

from pathlib import Path

from gway.appspec import AppSpec, BindingSpec, ViewSpec
from gway.appexposure import ExposureSpec, LocalAppService, apply_exposure
from gway.binding import Literal
from gway.publication import SKIP_PUBLICATION


class Controller:
    """Compose framework-neutral application specifications through Gway operations."""

    def __init__(self, gateway):
        self.gateway = gateway
        self._exposures = {}

    def setup_app(
        self,
        name=None,
        *,
        topic=None,
        route="/",
        templates=None,
        template: Literal = None,
        mutate=False,
    ):
        """Create a framework-neutral application specification.

        Args:
            name: Optional application name; inferred from the topic leaf when omitted.
            topic: Optional semantic handler-resolution root.
            route: Optional base route composed with each view-local route.
            templates: Optional recipe-relative template directory.
            template: Optional default template expression for handler-backed views.
        """
        del mutate
        template_root = None
        if templates is not None or template is not None:
            from gway.recipe import recipe_base

            if templates is None:
                template_root = str(recipe_base(self.gateway).resolve())
            else:
                resolved = Path(str(self.gateway.resolve(str(templates)))).expanduser()
                if not resolved.is_absolute():
                    resolved = recipe_base(self.gateway) / resolved
                template_root = str(resolved.resolve())
        return AppSpec(
            name=name,
            topic=topic,
            route=route,
            templates=template_root,
            template=None if template is None else str(template),
        )

    def _canonical_handler(self, handler, *, app=None):
        raw = str(handler).strip()
        if not raw:
            raise ValueError("view handler must be a non-empty operation identity")

        from gway.dispatch import resolve_operation
        from gway.tokens import tokenize

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
        handler: object = None,
        *,
        app: AppSpec,
        route=None,
        methods: tuple[str, ...] = (),
        method=None,
        name=None,
        query: tuple[str, ...] = (),
        path_params: tuple[str, ...] = (),
        header: tuple[str, ...] = (),
        body: tuple[str, ...] = (),
        body_model=None,
        response_model=None,
        static=None,
        directory: bool = False,
        content_type=None,
        auth=None,
        template: Literal = None,
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
            query: Handler arguments sourced from query parameters.
            path_params: Handler arguments sourced from named route segments.
            header: Handler arguments sourced from HTTP headers.
            body: Handler arguments sourced from the request body.
            body_model: Optional schema reference used to validate the request body.
            response_model: Optional schema reference used to validate/serialize results.
            static: Optional static file or directory source.
            directory: Treat the static source as a directory mount.
            content_type: Optional static response content-type override.
            auth: Optional named request policy applied before handler invocation.
            template: Optional sigil-aware text template used to render handler output.
            replace: Replace existing mappings for the same route/methods.
        """
        del mutate
        if not isinstance(app, AppSpec):
            raise TypeError("view app requires an AppSpec")
        if method is not None and methods:
            raise ValueError("use either --method or --methods, not both")

        selected_methods = (method,) if method is not None else methods
        if static is not None and (auth is not None or template is not None):
            raise ValueError("static views do not support auth or templates")
        if template is not None and app.templates is None:
            from gway.recipe import recipe_base

            app = AppSpec(
                name=app.name,
                topic=app.topic,
                route=app.route,
                views=app.views,
                templates=str(recipe_base(self.gateway).resolve()),
                template=app.template,
            )
        if handler is None and static is None:
            raise ValueError("view requires a handler or --static")
        if handler is not None and static is not None:
            raise ValueError("view accepts either a handler or --static, not both")

        canonical = None
        auth_policy = None
        static_source = None
        if static is None:
            canonical = self._canonical_handler(handler, app=app)
            if auth is not None:
                raw_auth = str(auth).strip()
                auth_policy = (
                    "public"
                    if raw_auth == "public"
                    else self._canonical_handler(raw_auth, app=app)
                )
        else:
            from gway.recipe import recipe_base

            resolved = Path(str(self.gateway.resolve(str(static)))).expanduser()
            if not resolved.is_absolute():
                resolved = recipe_base(self.gateway) / resolved
            static_source = str(resolved.resolve())

        bindings = tuple(
            BindingSpec(binding, source)
            for source, values in (
                ("query", query),
                ("path", path_params),
                ("header", header),
                ("body", body),
            )
            for binding in values
        )
        view = ViewSpec(
            canonical,
            route=route,
            methods=selected_methods or ("GET",),
            name=name,
            bindings=bindings,
            body_model=None if body_model is None else str(body_model),
            response_model=None if response_model is None else str(response_model),
            static=static_source,
            directory=directory,
            content_type=None if content_type is None else str(content_type),
            auth=auth_policy,
            template=None if template is None else str(template),
        )
        return app.replace(view) if replace else app.add(view)

    def expose_app(
        self,
        domain,
        *,
        app: AppSpec,
        service: LocalAppService = None,
        host=None,
        port=None,
        route="/",
        site=None,
        email=None,
        adapter="nginx-certbot",
        mutate=True,
    ):
        """Expose one known local application service externally."""
        if not isinstance(app, AppSpec):
            raise TypeError("expose app requires an AppSpec")
        if service is not None and (host is not None or port is not None):
            raise ValueError("use either --service or --host/--port, not both")
        if service is None:
            if host is None or port is None:
                raise ValueError(
                    "expose app requires a known local service or explicit --host and --port"
                )
            service = LocalAppService(app=app.name, host=host, port=port)
        elif not isinstance(service, LocalAppService):
            raise TypeError("service must be a LocalAppService")

        exposure = ExposureSpec(
            service=service,
            domain=domain,
            route=route,
            site=site,
            email=email,
            adapter=adapter,
        )
        key = (exposure.domain, exposure.route)
        existing = self._exposures.get(key)
        if existing is not None and existing != exposure:
            raise ValueError(
                f"conflicting exposure for {exposure.domain}{exposure.route}"
            )
        if existing is None:
            self._exposures[key] = exposure
        if not mutate:
            result = exposure
        elif existing is not None:
            result = existing
        else:
            result = apply_exposure(self.gateway, exposure)

        self.gateway.results.insert("exposure", result)
        return SKIP_PUBLICATION

    def serve_app(
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
            raise TypeError("serve app requires an AppSpec")

        from gway.appserver import serve_app

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
    gateway.serve_app = gateway.wrap(
        "serve.app",
        controller.serve_app,
        op="serve",
        sub="app",
    )
    gateway.expose_app = gateway.wrap(
        "expose.app",
        controller.expose_app,
        op="expose",
        sub="app",
    )
    return controller
