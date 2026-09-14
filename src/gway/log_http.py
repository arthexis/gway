from __future__ import annotations

import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse, urlunparse
from urllib.request import Request, urlopen

_TOKEN_ENV = "GWAY_LOG_TOKEN"
_TIMEOUT_SECONDS = 2.0


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
    token = os.environ.get(_TOKEN_ENV)
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
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            response.read(1)
            return 200 <= response.status < 300
    except (HTTPError, URLError, OSError, ValueError):
        return False
