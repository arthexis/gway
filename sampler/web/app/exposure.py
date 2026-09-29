"""Declarative local-service and public exposure models for AppSpec applications."""

from dataclasses import dataclass

from .appspec import HeaderSpec


@dataclass(frozen=True)
class LocalAppService:
    """Describe an already-running local application service."""

    app: str | None
    host: str
    port: int

    def __post_init__(self):
        host = str(self.host).strip()
        port = int(self.port)
        if not host:
            raise ValueError("local app service host cannot be empty")
        if not 1 <= port <= 65535:
            raise ValueError("local app service port must be between 1 and 65535")
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", port)


@dataclass(frozen=True)
class ExposureSpec:
    """Describe how one local application service should be exposed."""

    service: LocalAppService
    domain: str
    route: str = "/"
    site: str | None = None
    email: str | None = None
    adapter: str = "nginx-certbot"
    headers: tuple[HeaderSpec, ...] = ()

    def __post_init__(self):
        domain = str(self.domain).strip().lower()
        route = "/" + str(self.route or "/").strip("/")
        if route == "//":
            route = "/"
        if not domain:
            raise ValueError("exposure domain cannot be empty")
        site = self.site or domain.replace(".", "-")
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "route", route)
        object.__setattr__(self, "site", str(site).strip())
        headers = tuple(self.headers)
        if any(not isinstance(header, HeaderSpec) for header in headers):
            raise TypeError("exposure headers must be HeaderSpec instances")
        object.__setattr__(self, "headers", headers)


def _nginx_header_directives(headers):
    """Render semantic response headers as server-scoped NGINX directives."""
    directives = []
    for header in headers:
        value = header.value.replace("\\", "\\\\").replace('"', '\\"')
        directives.append(f'add_header {header.name} "{value}" always;')
    return "\n    ".join(directives)


def apply_exposure(gateway, exposure):
    """Apply one exposure through the maintained web exposure sampler."""
    if exposure.adapter != "nginx-certbot":
        raise ValueError(f"unsupported exposure adapter: {exposure.adapter}")
    if exposure.route != "/":
        raise NotImplementedError(
            "the nginx-certbot exposure adapter currently supports only route /"
        )
    if not exposure.email:
        raise ValueError("applied HTTPS exposure requires --email")

    from gway.sampler import run

    run(
        gateway,
        "web/expose/expose",
        site=exposure.site,
        domain=exposure.domain,
        host=exposure.service.host,
        port=exposure.service.port,
        email=exposure.email,
        response_headers=_nginx_header_directives(exposure.headers),
    )
    return exposure
