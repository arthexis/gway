"""Validation helpers for maintained remote web exposure."""

import re

_NGINX_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_site(site: str) -> str:
    """Return a site identifier that is safe inside nginx variable names."""
    value = str(site).strip()
    if not _NGINX_IDENTIFIER.fullmatch(value):
        raise ValueError(
            "remote exposure site must be an nginx-safe identifier "
            "(letters, digits, and underscores; must not start with a digit); "
            f"got {site!r}"
        )
    return value
