from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

TRANSFER_PREFIX = "\0gway-transfer:"
_TRANSFER_VALUES: ContextVar[list[object] | None] = ContextVar(
    "gway_transfer_values",
    default=None,
)


@contextmanager
def transfer_scope():
    """Create invocation-local storage for opaque transferred values."""
    token = _TRANSFER_VALUES.set([])
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
    """Store one native value and return an argv-safe opaque token for it."""
    values = _TRANSFER_VALUES.get()
    if values is None:
        raise RuntimeError("transfer token created outside an active transfer scope")
    index = len(values)
    values.append(_normalize_transfer_value(value))
    return f"{TRANSFER_PREFIX}{index}"


def decode_transfer(value: object) -> object:
    """Restore one native value when ``value`` is an active transfer token."""
    if not isinstance(value, str) or not value.startswith(TRANSFER_PREFIX):
        return value
    values = _TRANSFER_VALUES.get()
    if values is None:
        return value
    suffix = value[len(TRANSFER_PREFIX) :]
    if not suffix.isdigit():
        return value
    index = int(suffix)
    if index >= len(values):
        return value
    return values[index]


__all__ = ["TRANSFER_PREFIX", "decode_transfer", "encode_transfer", "transfer_scope"]
