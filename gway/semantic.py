"""Shared semantic mapping-key resolution."""

from collections.abc import Mapping
import re


_SEPARATORS = re.compile(r"[\s_-]+")


class AmbiguousKeyError(KeyError):
    """Raised when one semantic key matches multiple mapping keys."""

    def __init__(self, requested, matches):
        self.requested = requested
        self.matches = tuple(matches)
        rendered = ", ".join(repr(value) for value in self.matches)
        super().__init__(
            f"Semantic key {requested!r} is ambiguous; matched {rendered}"
        )


def normalize_key(value):
    """Return the canonical semantic form for one string key."""
    if not isinstance(value, str):
        return value
    return _SEPARATORS.sub("", value).casefold()


def resolve_mapping_key(mapping: Mapping, requested):
    """Return the concrete mapping key matching one semantic request."""
    if not isinstance(mapping, Mapping):
        raise TypeError("resolve_mapping_key requires a mapping")

    if not isinstance(requested, str):
        if requested in mapping:
            return requested
        raise KeyError(requested)

    normalized = normalize_key(requested)
    matches = [
        key
        for key in mapping
        if isinstance(key, str) and normalize_key(key) == normalized
    ]
    if not matches:
        raise KeyError(requested)
    if len(matches) > 1:
        raise AmbiguousKeyError(requested, matches)
    return matches[0]


def mapping_value(mapping: Mapping, requested):
    """Return one semantic mapping value."""
    return mapping[resolve_mapping_key(mapping, requested)]
