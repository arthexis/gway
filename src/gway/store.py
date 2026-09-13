from __future__ import annotations

from collections.abc import Sequence

from .config import GwayPaths
from .dispatcher.errors import DispatchError
from .explain import record
from .solve import solve_values

_RESERVED_STORE_KEYS = frozenset({"result"})


def _store_name(option: str) -> str:
    name = option[2:].replace("-", "_")
    if not name or not name.isidentifier():
        raise DispatchError(f"invalid store option: {option!r}")
    if name in _RESERVED_STORE_KEYS:
        raise DispatchError(f"cannot store reserved context key: {name}")
    return name


def run_store(
    tokens: Sequence[str],
    *,
    paths: GwayPaths | None = None,
) -> dict[str, object]:
    """Return arbitrary named values for publication into the active GWAY context."""
    stored: dict[str, object] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("--") or token == "--":
            raise DispatchError("store accepts named options only")

        option, separator, attached = token.partition("=")
        if option.startswith("--no-") and not separator:
            name = _store_name(f"--{option[5:]}")
            stored[name] = False
            index += 1
            continue

        name = _store_name(option)
        if separator:
            raw_value = attached
        elif index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
            index += 1
            raw_value = tokens[index]
        else:
            stored[name] = True
            index += 1
            continue

        stored[name] = solve_values([raw_value], paths=paths)
        index += 1

    record(
        "context.store",
        "stored named values in active execution context",
        values=dict(stored),
    )
    return stored


__all__ = ["run_store"]
