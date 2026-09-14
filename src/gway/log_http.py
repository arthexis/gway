from __future__ import annotations

import os
from contextvars import ContextVar
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

_TOKEN_ENV = "GWAY_LOG_TOKEN"
_TIMEOUT_SECONDS = 2.0
_tokens: ContextVar[dict[str, str]] = ContextVar("gway_log_http_tokens", default={})


class _RejectRedirects(HTTPRedirectHandler):
    """Reject redirects so bearer credentials and POST bodies never move origins."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_OPENER = build_opener(_RejectRedirects())


def set_token(destination: str, token: str) -> None:
    """Set a process-local bearer credential for one logging destination."""
    current = dict(_tokens.get())
    current[destination] = token
    _tokens.set(current)


def clear_tokens() -> None:
    """Drop process-local publisher credentials without modifying the environment."""
    _tokens.set({})


def ingest_url(destination: str, run_id: str) -> str | None:
    """Return the GWAY Web ingest endpoint for an HTTP(S) log destination."""
    parsed = urlparse(destination)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    base_path = parsed.path.rstrip("/")
    if base_path.endswith("/api/logs"):
        path = f"{base_path}/{quote(run_id, safe='')}/events"
    else:
        path = f"{base_path}/api/logs/{quote(run_id, safe='')}/events"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def publish(destination: str, run_id: str, data: bytes) -> bool:
    """Best-effort publish an NDJSON batch using the configured bearer token."""
    token = _tokens.get().get(destination) or os.environ.get(_TOKEN_ENV)
    endpoint = ingest_url(destination, run_id)
    if not token or endpoint is None or not data:
        return False
    request = Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-ndjson",
        },
    )
    try:
        with _OPENER.open(request, timeout=_TIMEOUT_SECONDS) as response:
            response.read(1)
            return 200 <= response.status < 300
    except (HTTPError, URLError, OSError, ValueError):
        return False


__all__ = ["clear_tokens", "ingest_url", "publish", "set_token"]
