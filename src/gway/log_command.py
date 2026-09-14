from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from .config import GwayPaths
from .dispatcher.errors import DispatchError
from .history import last_run
from .log_consumers import configure_consumers, normalize_consumers
from .logging import configure, current_context
from .solve import solve_values


def _resolve_argument(value: str) -> str:
    resolved = solve_values([value])
    return resolved if isinstance(resolved, str) else str(resolved)


def _default_dispatch(project: str, tokens: Sequence[str]) -> object:
    # Import lazily so the core log parser does not create a dispatcher unless a
    # consumer binding actually needs a managed provider capability.
    from .dispatcher import Dispatcher

    return Dispatcher().run(project, tokens)


def run_log(
    argv: Sequence[str],
    *,
    dispatch: Callable[[str, Sequence[str]], object] | None = None,
    paths: GwayPaths | None = None,
) -> dict[str, object]:
    """Inspect logging context, configure consumers, or query command history."""
    parser = argparse.ArgumentParser(prog="gway log", add_help=False)
    parser.add_argument("--tags", action="append", default=[])
    parser.add_argument("--to", action="append", default=[])
    parser.add_argument("--consumer", action="append", default=[])
    parser.add_argument("--consumers", action="append", default=[])
    parser.add_argument("--last", action="store_true")
    parser.add_argument("--failed", action="store_true")
    parser.add_argument("--project")
    namespace, unknown = parser.parse_known_args([_resolve_argument(value) for value in argv])
    if unknown:
        raise DispatchError(f"unrecognized log arguments: {' '.join(unknown)}")

    for consumer in namespace.consumer:
        if "," in consumer:
            raise DispatchError("--consumer accepts one consumer; use --consumers for comma-separated names")

    consumer_values = (*namespace.consumer, *namespace.consumers)
    if namespace.failed and not namespace.last:
        raise DispatchError("--failed requires --last")
    if namespace.project and not namespace.last:
        raise DispatchError("--project requires --last")
    if namespace.last:
        if namespace.tags or namespace.to or consumer_values:
            raise DispatchError(
                "--last cannot be combined with --tags, --to, --consumer, or --consumers"
            )
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
    consumers = normalize_consumers(consumer_values)
    binding: dict[str, object] | None = None
    if consumers:
        existing = current_context().get("to", [])
        existing_destinations = tuple(
            value for value in existing if isinstance(value, str)
        ) if isinstance(existing, list) else ()
        effective_destinations = tuple(
            dict.fromkeys((*existing_destinations, *destinations))
        )
        binding = configure_consumers(
            consumers,
            effective_destinations,
            dispatch=dispatch or _default_dispatch,
            paths=paths,
        )

    if tags or destinations or consumers:
        state = configure(tags=tags, to=destinations)
        if binding is not None:
            state["consumers"] = binding["consumers"]
            state["consumer_destination"] = binding["destination"]
            state["consumer_token_id"] = binding["token_id"]
        return state
    return current_context()


__all__ = ["run_log"]
