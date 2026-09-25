"""Declarative local-service and public exposure models for AppSpec applications."""

from dataclasses import dataclass


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
    path: str = "/"
    site: str | None = None
    email: str | None = None
    adapter: str = "nginx-certbot"

    def __post_init__(self):
        domain = str(self.domain).strip().lower()
        path = "/" + str(self.path or "/").strip("/")
        if path == "//":
            path = "/"
        if not domain:
            raise ValueError("exposure domain cannot be empty")
        site = self.site or domain.replace(".", "-")
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "site", str(site).strip())


def apply_exposure(gateway, exposure):
    """Apply one exposure through the maintained web exposure sampler."""
    if exposure.adapter != "nginx-certbot":
        raise ValueError(f"unsupported exposure adapter: {exposure.adapter}")
    if exposure.path != "/":
        raise NotImplementedError(
            "the nginx-certbot exposure adapter currently supports only path /"
        )
    if not exposure.email:
        raise ValueError("applied HTTPS exposure requires --email")

    from .sampler import run

    run(
        gateway,
        "web/expose/expose",
        site=exposure.site,
        domain=exposure.domain,
        host=exposure.service.host,
        port=exposure.service.port,
        email=exposure.email,
    )
    return exposure
