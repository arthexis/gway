from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from .dispatcher.errors import DispatchError
from .event import DEFAULT_BACKEND, publish


class _EventParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise DispatchError(message)


def _value(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def run_event(argv: Sequence[str]) -> dict[str, Any]:
    if not argv:
        raise DispatchError("event requires publish (or pub)")
    operation = argv[0]
    if operation not in {"publish", "pub"}:
        raise DispatchError(f"unknown event operation: {operation}")

    parser = _EventParser(prog=f"gway event {operation}", add_help=False)
    parser.add_argument("event_type")
    parser.add_argument("--backend", default=DEFAULT_BACKEND)
    parser.add_argument("--path")
    namespace, fields = parser.parse_known_args(list(argv[1:]))

    data: dict[str, Any] = {}
    index = 0
    while index < len(fields):
        token = fields[index]
        if not token.startswith("--") or token == "--":
            raise DispatchError(f"invalid event field: {token}")
        key = token[2:].replace("-", "_")
        if not key:
            raise DispatchError("event field name cannot be empty")
        index += 1
        if index >= len(fields) or fields[index].startswith("--"):
            data[key] = True
            continue
        data[key] = _value(fields[index])
        index += 1

    try:
        return publish(
            namespace.event_type,
            backend_name=namespace.backend,
            path=namespace.path,
            **data,
        )
    except ValueError as exc:
        raise DispatchError(str(exc)) from exc


__all__ = ["run_event"]
