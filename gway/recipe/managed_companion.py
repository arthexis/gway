"""Namespace-aware registration for managed recipe companions."""

from ..ingestion.base import IngestedOperation, register_operation
from .companion import _proxy, _signature


def register_worker_operations(runtime, worker, *, root):
    """Register managed companion callables under the recipe's public root."""
    namespace = (str(root),)
    registered = []
    for description in worker.operations:
        name = description["name"]
        operation = IngestedOperation(
            (*namespace, name),
            _proxy(runtime, worker.recipe, name, _signature(description)),
            source=worker.companion,
            kind="recipe-companion-worker",
            metadata={
                "recipe": str(worker.recipe),
                "companion": str(worker.companion),
                "python": str(worker.python),
            },
        )
        existing = runtime.ops.resolve(operation.name)
        if existing is not None:
            continue
        registered.append(register_operation(runtime, operation))
    return registered


def unregister_worker_operations(runtime, worker, *, root):
    """Hide operations registered for a managed companion's public root."""
    namespace = str(root)
    removed = []
    for description in worker.operations:
        name = f"{namespace}.{description['name']}"
        operation = runtime.ops.resolve(name)
        if operation is None:
            continue
        metadata = getattr(operation, "__gway_metadata__", {})
        if (
            getattr(operation, "__gway_source_kind__", None)
            != "recipe-companion-worker"
            or metadata.get("companion") != str(worker.companion)
        ):
            continue
        runtime.ops.unregister(name)
        removed.append(name)
    return tuple(removed)
