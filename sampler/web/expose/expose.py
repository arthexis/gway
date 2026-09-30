"""Helpers for maintained generic web exposure."""

import re


_UNSAFE_NGINX_IDENTIFIER = re.compile(r"[^A-Za-z0-9_]")


def normalize_site(site: str) -> str:
    """Return a stable nginx-safe identifier derived from a site name."""
    value = _UNSAFE_NGINX_IDENTIFIER.sub("_", str(site).strip())
    if not value:
        raise ValueError("web exposure site cannot be empty")
    if value[0].isdigit():
        value = "_" + value
    return value
