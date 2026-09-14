from __future__ import annotations

import argparse
from collections.abc import Sequence

from .dispatcher.errors import DispatchError
from .logging import configure, current_context
from .solve import solve_values


def _resolve_argument(value: str) -> str:
    resolved = solve_values([value])
    return resolved if isinstance(resolved, str) else str(resolved)


def run_log(argv: Sequence[str]) -> dict[str, object]:
    """Inspect or update the logging context for the current GWAY run."""
    parser = argparse.ArgumentParser(prog="gway log", add_help=False)
    parser.add_argument("--tags", action="append", default=[])
    parser.add_argument("--to", action="append", default=[])
    namespace, unknown = parser.parse_known_args([_resolve_argument(value) for value in argv])
    if unknown:
        raise DispatchError(f"unrecognized log arguments: {' '.join(unknown)}")

    tags = tuple(
        tag.strip()
        for value in namespace.tags
        for tag in value.split(",")
        if tag.strip()
    )
    destinations = tuple(value.strip() for value in namespace.to if value.strip())
    if tags or destinations:
        return configure(tags=tags, to=destinations)
    return current_context()


__all__ = ["run_log"]
