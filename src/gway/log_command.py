from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from .config import GwayPaths
from .dispatcher.errors import DispatchError
from .history import last_run
from .log_consumers import ConsumerResolver, configure_consumers, normalize_consumers
from .logging import configure, current_context
from .solve import solve_values


def _resolve_argument(value: str) -> str:
    resolved = solve_values([value])
    return resolved if isinstance(resolved, str) else str(resolved)


def _default_access(
    paths: GwayPaths | None,
) -> tuple[Callable[[str, Sequence[str]], object], ConsumerResolver]:
    # Import lazily so ordinary log inspection does not construct a dispatcher.
    from .dispatcher import Dispatcher
    from .registry import Registry

    registry = Registry(paths=paths)
    dispatcher = Dispatcher(registry=registry)
    return dispatcher.run, registry.get


def _bound_registry(dispatch: Callable[[str, Sequence[str]], object] | None):
    owner = getattr(dispatch, "__self__", None)
    return getattr(owner, "registry", None)


def run_log(
    argv: Sequence[str],
    *,
    dispatch: Callable[[str, Sequence[str]], object] | None = None,
    paths: GwayPaths | None = None,
    resolve_consumer: ConsumerResolver | None = None,
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
        active_dispatch = dispatch
        active_resolver = resolve_consumer
        active_paths = paths
        registry = _bound_registry(active_dispatch)
        if registry is not None:
            if active_paths is None:
                active_paths = registry.paths
            if active_resolver is None:
                active_resolver = registry.get
        if active_dispatch is None or active_resolver is None:
            default_dispatch, default_resolver = _default_access(active_paths)
            active_dispatch = active_dispatch or default_dispatch
            active_resolver = active_resolver or default_resolver

        existing = current_context().get("to", [])
        existing_destinations = (
            tuple(value for value in existing if isinstance(value, str))
            if isinstance(existing, list)
            else ()
        )
        # An explicit --to declaration moves/configures the consumer against
        # that destination even when this run is already publishing elsewhere.
        # Existing run sinks are only a fallback when --to is omitted.
        effective_destinations = destinations or existing_destinations
        binding = configure_consumers(
            consumers,
            effective_destinations,
            dispatch=active_dispatch,
            paths=active_paths,
            resolve_consumer=active_resolver,
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
