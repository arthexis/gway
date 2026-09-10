from __future__ import annotations

import secrets
from contextlib import contextmanager
from contextvars import ContextVar

TRANSFER_PREFIX = "\0gway-transfer:"
_TRANSFER_VALUES: ContextVar[dict[str, object] | None] = ContextVar(
    "gway_transfer_values",
    default=None,
)


@contextmanager
def transfer_scope():
    """Create invocation-local storage for opaque transferred values."""
    token = _TRANSFER_VALUES.set({})
    try:
        yield
    finally:
        _TRANSFER_VALUES.reset(token)


def _normalize_transfer_value(value: object) -> object:
    """Retain P1 byte-scalar behavior while keeping the value opaque to argv parsing."""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    if isinstance(value, bytearray):
        return bytes(value).decode(errors="replace")
    return value


def encode_transfer(value: object) -> str:
    """Store one native value and return an argv-safe scope-specific token for it."""
    values = _TRANSFER_VALUES.get()
    if values is None:
        raise RuntimeError("transfer token created outside an active transfer scope")
    while True:
        token = f"{TRANSFER_PREFIX}{secrets.token_urlsafe(18)}"
        if token not in values:
            break
    values[token] = _normalize_transfer_value(value)
    return token


def decode_transfer(value: object) -> object:
    """Restore only values represented by tokens emitted in the active transfer scope."""
    if not isinstance(value, str) or not value.startswith(TRANSFER_PREFIX):
        return value
    values = _TRANSFER_VALUES.get()
    if values is None:
        return value
    return values.get(value, value)


def render_transfer(value: object) -> str:
    """Restore an opaque transfer and render it for a string-only adapter boundary."""
    restored = decode_transfer(value)
    return restored if isinstance(restored, str) else str(restored)


__all__ = [
    "TRANSFER_PREFIX",
    "decode_transfer",
    "encode_transfer",
    "render_transfer",
    "transfer_scope",
]
