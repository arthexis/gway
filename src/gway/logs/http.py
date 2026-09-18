from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .binding import PublisherBinding

_TIMEOUT_SECONDS = 2.0


class _RejectRedirects(HTTPRedirectHandler):
    """Reject redirects so provider headers and POST bodies never move origins."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_OPENER = build_opener(_RejectRedirects())


def _loopback_host(host: str | None) -> bool:
    if host is None:
        return False
    normalized = host.rstrip(".").casefold()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _render(template: str, values: Mapping[str, str], *, run_id: str) -> str:
    rendered = template.replace("{run_id}", quote(run_id, safe=""))
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def endpoint(binding: PublisherBinding, run_id: str) -> str | None:
    """Render one provider-declared HTTP endpoint."""
    template = binding.configuration.get("url_template")
    if not isinstance(template, str) or not template:
        return None
    url = _render(template, binding.environment, run_id=run_id)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.scheme == "http" and not _loopback_host(parsed.hostname):
        return None
    return url


def headers(binding: PublisherBinding, run_id: str) -> dict[str, str] | None:
    """Render provider-declared HTTP headers from its private environment."""
    configured = binding.configuration.get("headers", {})
    if not isinstance(configured, Mapping):
        return None
    rendered: dict[str, str] = {}
    for key, value in configured.items():
        if not isinstance(key, str) or not key or not isinstance(value, str):
            return None
        if any(character in key for character in "\r\n:"):
            return None
        rendered_value = _render(value, binding.environment, run_id=run_id)
        if "\r" in rendered_value or "\n" in rendered_value:
            return None
        rendered[key] = rendered_value
    return rendered


def publish(binding: PublisherBinding, run_id: str, data: bytes) -> bool:
    """Best-effort publish using an explicit provider-declared HTTP request."""
    url = endpoint(binding, run_id)
    request_headers = headers(binding, run_id)
    if url is None or request_headers is None or not data:
        return False
    method = binding.configuration.get("method", "POST")
    if not isinstance(method, str) or method.upper() not in {"POST", "PUT"}:
        return False
    request = Request(
        url,
        data=data,
        method=method.upper(),
        headers=request_headers,
    )
    try:
        with _OPENER.open(request, timeout=_TIMEOUT_SECONDS) as response:
            response.read(1)
            return 200 <= response.status < 300
    except (HTTPError, URLError, OSError, ValueError):
        return False


__all__ = ["endpoint", "headers", "publish"]
