from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar

_JSON_MODE: ContextVar[bool | None] = ContextVar("gway_json_mode", default=None)


def global_json_requested(argv: Sequence[str]) -> bool:
    """Return whether argv enables GWAY's exact global ``--json`` flag."""
    for argument in argv:
        if argument == "--":
            break
        if argument == "--json":
            return True
    return False


def resolve_cli_json_mode(argv: Sequence[str]) -> bool:
    """Resolve JSON mode for a user invocation."""
    return global_json_requested(argv)


def current_json_mode() -> bool | None:
    """Return invocation-local JSON mode, or ``None`` outside a CLI invocation."""
    return _JSON_MODE.get()


@contextmanager
def json_mode_scope(enabled: bool) -> Iterator[None]:
    """Apply JSON mode to one invocation without shared mutable process state."""
    token = _JSON_MODE.set(bool(enabled))
    try:
        yield
    finally:
        _JSON_MODE.reset(token)


def seed_legacy_cli_json_mode(argv: Sequence[str]) -> bool:
    """Seed root invocation state for an already-generated legacy console launcher."""
    enabled = resolve_cli_json_mode(argv)
    _JSON_MODE.set(enabled)
    return enabled


__all__ = [
    "current_json_mode",
    "global_json_requested",
    "json_mode_scope",
    "resolve_cli_json_mode",
    "seed_legacy_cli_json_mode",
]
