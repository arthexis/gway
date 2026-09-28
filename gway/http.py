"""Provider-neutral HTTP client transport built on HTTPX."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


DEFAULT_TIMEOUT = 30.0
_SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "cookie", "set-cookie"}


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
            "headers": dict(self.headers),
            "result": body,
        }


def _safe_headers(headers):
    """Return request headers with credential-bearing values redacted."""
    return {
        str(name): (
            "<redacted>"
            if str(name).lower() in _SENSITIVE_HEADERS
            else str(value)
        )
        for name, value in (headers or {}).items()
    }


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
        safe = _safe_headers(headers)
        detail = f"HTTP {method} request failed for {url}"
        if safe:
            detail += f" with headers {safe!r}"
        raise HTTPTransportError(detail) from error

    return HTTPResponse(
        status=response.status_code,
        url=str(response.url),
        headers={name.lower(): value for name, value in response.headers.items()},
        content=response.content,
    )
