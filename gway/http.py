"""Provider-neutral HTTP client transport built on HTTPX."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx


DEFAULT_TIMEOUT = 30.0
_SENSITIVE_HEADERS = {\n    "authorization",\n    "proxy-authorization",\n    "cookie",\n    "set-cookie",\n    "x-api-key",\n    "x-auth-token",\n    "api-key",\n}


class HTTPTransportError(RuntimeError):
    """Raised when an HTTP request cannot be completed."""


@dataclass(frozen=True)
class HTTPResponse:
    """Stable GWAY representation of an HTTP response."""

    status: int
    url: str
    headers: dict[str, str]
    content: bytes

    @property
    def text(self):
        return self.content.decode("utf-8", "replace")

    def json(self):
        import json

        return json.loads(self.content)

    def result(self):
        content_type = self.headers.get("content-type", "").lower()
        if "json" in content_type and self.content:
            try:
                body = self.json()
            except (ValueError, UnicodeDecodeError):
                body = self.text
        else:
            body = self.text
        return {
            "status": self.status,
            "url": self.url,
            "headers": _safe_headers(self.headers),
            "result": body,
        }


def _safe_headers(headers):
    """Return headers without exposing values that commonly carry credentials."""
    return {
        str(name): (
            "<redacted>"
            if str(name).lower() in _SENSITIVE_HEADERS
            else str(value)
        )
        for name, value in (headers or {}).items()
    }


def _safe_url(url):
    """Return a URL safe for diagnostics by removing credentials and query data."""
    parsed = urlsplit(str(url))
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))

