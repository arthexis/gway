"""Provider-neutral HTTP client transport built on HTTPX."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx


DEFAULT_TIMEOUT = 30.0
_SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "api-key",
}


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


def request(
    method,
    url,
    *,
    headers=None,
    params=None,
    json=None,
    data=None,
    timeout=DEFAULT_TIMEOUT,
    follow_redirects=False,
    transport=None,
):
    """Execute one HTTP request and return a stable GWAY response."""
    method = str(method).upper()
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=bool(follow_redirects),
            transport=transport,
        ) as client:
            response = client.request(
                method,
                str(url),
                headers=headers,
                params=params,
                json=json,
                content=data,
            )
    except httpx.HTTPError as error:
        names = sorted(str(name) for name in (headers or {}))
        detail = f"HTTP {method} request failed for {_safe_url(url)}"
        if names:
            detail += f" with header names {names!r}"
        raise HTTPTransportError(detail) from error

    return HTTPResponse(
        status=response.status_code,
        url=str(response.url),
        headers={name.lower(): value for name, value in response.headers.items()},
        content=response.content,
    )
