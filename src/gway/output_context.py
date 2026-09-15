from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar

_JSON_MODE_ENV = "_GWAY_JSON_MODE"
_JSON_MODE: ContextVar[bool | None] = ContextVar("gway_json_mode", default=None)
_MISSING = object()


def global_json_requested(argv: Sequence[str]) -> bool:
    """Return whether argv enables GWAY's exact global ``--json`` flag."""
    for argument in argv:
        if argument == "--":
            break
        if argument == "--json":
            return True
    return False


def _inherited_json_mode() -> bool | None:
    value = os.environ.get(_JSON_MODE_ENV)
    if value == "1":
        return True
    if value == "0":
        return False
    return None


def resolve_cli_json_mode(argv: Sequence[str]) -> bool:
    """Resolve JSON mode for a user invocation or an internal reload resume."""
    if argv and argv[0] == "--resume":
        inherited = _inherited_json_mode()
        if inherited is not None:
            return inherited
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
    """Seed the root CLI context for launchers that bypass the canonical entrypoint."""
    enabled = resolve_cli_json_mode(argv)
    _JSON_MODE.set(enabled)
    return enabled


@contextmanager
def json_mode_exec_environment() -> Iterator[None]:
    """Bridge the current mode through an imminent exec, restoring it on exec failure."""
    previous: object = os.environ.get(_JSON_MODE_ENV, _MISSING)
    enabled = current_json_mode()
    if enabled is None:
        os.environ.pop(_JSON_MODE_ENV, None)
    else:
        os.environ[_JSON_MODE_ENV] = "1" if enabled else "0"
    try:
        yield
    finally:
        if previous is _MISSING:
            os.environ.pop(_JSON_MODE_ENV, None)
        else:
            os.environ[_JSON_MODE_ENV] = str(previous)


__all__ = [
    "current_json_mode",
    "global_json_requested",
    "json_mode_exec_environment",
    "json_mode_scope",
    "resolve_cli_json_mode",
    "seed_legacy_cli_json_mode",
]
