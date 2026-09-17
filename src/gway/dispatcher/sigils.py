from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..adapters.base import SigilContextAdapter
from ..command import Command
from ..config import GwayPaths
from ..explain import record
from ..project import Project
from ..sigils import (
    RESERVED_CONTEXT_KEYS,
    capture_cli_values,
    resolve_captured_cli_values,
)
from .errors import DispatchError


def resolve_dispatch_arguments(
    argv: Sequence[str],
    *,
    project: Project,
    command: Command,
    adapter: object,
    chain_context: Mapping[str, object],
    paths: GwayPaths,
) -> list[str]:
    """Resolve dispatch-time Sigils using adapter and chain context."""
    templates = capture_cli_values(argv, paths=paths)
    record(
        "sigil.capture",
        "captured command argument templates",
        project=project.name,
        command=list(command.path),
        argv=list(argv),
    )

    extra_context: dict[str, object] = {}
    if isinstance(adapter, SigilContextAdapter):
        provided_context = adapter.sigil_context(command.path)
        if not isinstance(provided_context, Mapping):
            raise DispatchError("adapter sigil_context() must return a mapping")
        extra_context.update(provided_context)
        record(
            "sigil.context",
            "added adapter-provided Sigil context",
            project=project.name,
            command=list(command.path),
            keys=sorted(str(key) for key in provided_context),
        )

    extra_context.update(
        (key, value)
        for key, value in chain_context.items()
        if key not in RESERVED_CONTEXT_KEYS
    )
    try:
        resolved = resolve_captured_cli_values(
            templates,
            project,
            command.path,
            paths=paths,
            extra_context=extra_context or None,
        )
    except ValueError as exc:
        record(
            "sigil.resolve",
            "Sigil resolution failed",
            project=project.name,
            command=list(command.path),
            error=str(exc),
        )
        raise DispatchError(str(exc)) from exc

    record(
        "sigil.resolve",
        "resolved command argument templates",
        project=project.name,
        command=list(command.path),
        before=list(argv),
        after=list(resolved),
    )
    return list(resolved)


__all__ = ["resolve_dispatch_arguments"]
