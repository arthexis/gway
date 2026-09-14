from __future__ import annotations

import argparse
from collections.abc import Sequence

from .dispatcher.errors import DispatchError
from .history import last_run
from .logging import configure, current_context
from .solve import solve_values


def _resolve_argument(value: str) -> str:
    resolved = solve_values([value])
    return resolved if isinstance(resolved, str) else str(resolved)


def run_log(argv: Sequence[str]) -> dict[str, object]:
    """Inspect logging context or query structured GWAY command history."""
    parser = argparse.ArgumentParser(prog="gway log", add_help=False)
    parser.add_argument("--tags", action="append", default=[])
    parser.add_argument("--to", action="append", default=[])
    parser.add_argument("--last", action="store_true")
    parser.add_argument("--failed", action="store_true")
    parser.add_argument("--project")
    namespace, unknown = parser.parse_known_args([_resolve_argument(value) for value in argv])
    if unknown:
        raise DispatchError(f"unrecognized log arguments: {' '.join(unknown)}")

    if namespace.failed and not namespace.last:
        raise DispatchError("--failed requires --last")
    if namespace.project and not namespace.last:
        raise DispatchError("--project requires --last")
    if namespace.last:
        if namespace.tags or namespace.to:
            raise DispatchError("--last cannot be combined with --tags or --to")
        result = last_run(
            project=namespace.project,
            failed=True if namespace.failed else None,
            include_events=True,
        )
        if result is None:
            description = "failed " if namespace.failed else ""
            project = f" for project {namespace.project!r}" if namespace.project else ""
            raise DispatchError(f"no matching {description}GWAY run found{project}")
        return result

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
