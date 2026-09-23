"""Shared semantic mapping-key resolution."""

from collections.abc import Mapping
from itertools import permutations
import re


_SEPARATORS = re.compile(r"[\s_-]+")


class AmbiguousKeyError(KeyError):
    """Raised when one semantic key matches multiple mapping keys."""

    def __init__(self, requested, matches):
        self.requested = requested
        self.matches = tuple(matches)
        rendered = ", ".join(repr(value) for value in self.matches)
        super().__init__(f"Semantic key {requested!r} is ambiguous; matched {rendered}")


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


def semantic_candidates(subject, topics=()):
    """Return semantic lookup keys for one subject under ordered topics.

    Topics describe contextual meaning while the subject names the value being
    resolved. The complete topic combination is most specific, followed by each
    individual topic from most-local to broadest, then the bare subject.
    """
    subject = str(subject).strip()
    if not subject:
        raise ValueError("semantic subject must be non-empty")

    normalized_topics = tuple(str(topic).strip() for topic in topics)
    if any(not topic for topic in normalized_topics):
        raise ValueError("semantic topics must be non-empty")

    candidates = []
    if normalized_topics:
        for ordered_topics in permutations(normalized_topics):
            candidates.append(".".join((*ordered_topics, subject)))
        candidates.extend(
            f"{topic}.{subject}" for topic in reversed(normalized_topics)
        )
    candidates.append(subject)
    return tuple(dict.fromkeys(candidates))
