from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sigils import Context, SafeNamespace, Sigil

from .config import GwayPaths, default_paths
from .project import Project
from .registry import Registry

RESERVED_CONTEXT_KEYS = frozenset({"cwd", "home", "gway", "project", "command"})


class _GwayNamespaceProvider:
    """Resolve a managed project's zero-argument commands as Sigil values."""

    def __init__(
        self,
        registry: Registry,
        project_name: str,
        *,
        prefix: tuple[str, ...] = (),
        cache: dict[tuple[str, tuple[str, ...]], object] | None = None,
    ) -> None:
        self.registry = registry
        self.project_name = project_name
        self.prefix = prefix
        self.cache = cache if cache is not None else {}

    def resolve_sigil(self, key: str) -> object:
        # Python command names are exposed by GWAY with underscores normalized
        # to the same hyphenated spelling used by the CLI.
        command_key = key.replace("_", "-")
        path = (*self.prefix, command_key)

        # Import lazily to avoid a module cycle: Dispatcher itself uses this
        # module for command-argument Sigil resolution.
        from .dispatcher import Dispatcher

        dispatcher = Dispatcher(registry=self.registry)
        commands = dispatcher.commands(self.project_name)
        command_map = {command.path: command for command in commands}

        command = command_map.get(path)
        if command is not None:
            # Sigil invocation intentionally supplies no arguments. Commands
            # with required parameters therefore are not value-resolvable yet.
            if any(parameter.required for parameter in command.parameters):
                raise KeyError(key)

            project = self.registry.require(self.project_name)
            cache_key = (project.name, path)
            if cache_key not in self.cache:
                self.cache[cache_key] = dispatcher.run(self.project_name, path)
            return self.cache[cache_key]

        if any(candidate[: len(path)] == path for candidate in command_map):
            return SafeNamespace(
                _GwayNamespaceProvider(
                    self.registry,
                    self.project_name,
                    prefix=path,
                    cache=self.cache,
                )
            )

        raise KeyError(key)


def gway_context(
    paths: GwayPaths | None = None,
    *,
    registry: Registry | None = None,
) -> dict[str, object]:
    """Return lazy managed-project namespaces for one Sigil evaluation scope.

    Each call creates a fresh memoization scope. Repeated references to the
    same managed command within that scope reuse its value; callers that need
    live values, such as display render loops, should call ``gway_context()``
    again for each render.
    """
    active_registry = registry or Registry(paths or default_paths())
    cache: dict[tuple[str, tuple[str, ...]], object] = {}
    context: dict[str, object] = {}

    for project in active_registry.list():
        provider = SafeNamespace(
            _GwayNamespaceProvider(
                active_registry,
                project.name,
                cache=cache,
            )
        )
        for name in (project.name, *project.aliases):
            if name not in RESERVED_CONTEXT_KEYS:
                context[name] = provider

    return context


def base_context(paths: GwayPaths | None = None) -> dict[str, object]:
    """Return the context available before project resolution."""
    active_paths = paths or default_paths()
    context = gway_context(active_paths)
    context.update(
        {
            "cwd": str(Path.cwd()),
            "home": str(Path.home()),
            "gway": {
                "config_dir": str(active_paths.config_dir),
                "data_dir": str(active_paths.data_dir),
            },
        }
    )
    return context


def project_context(
    project: Project,
    command_path: tuple[str, ...],
    *,
    paths: GwayPaths | None = None,
    extra_context: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return the lazy-resolution context for one dispatched command."""
    context = base_context(paths)
    context.update(
        {
            "project": {
                "name": project.name,
                "path": str(project.path),
                "adapter": project.adapter_type,
                "aliases": list(project.aliases),
                "repository": project.repository,
                "revision": project.revision,
                "environment": (
                    str(project.environment) if project.environment is not None else None
                ),
            },
            "command": {
                "path": " ".join(command_path),
                "name": command_path[-1] if command_path else "",
            },
        }
    )
    if extra_context:
        collisions = RESERVED_CONTEXT_KEYS.intersection(extra_context)
        if collisions:
            names = ", ".join(sorted(collisions))
            raise ValueError(f"adapter Sigil context cannot replace reserved keys: {names}")
        context.update(extra_context)
    return context


def capture_cli_values(
    values: Sequence[str],
    *,
    paths: GwayPaths | None = None,
) -> tuple[Sigil, ...]:
    """Capture eager sigils while leaving lazy sigils unresolved."""
    context = base_context(paths)
    with Context(context):
        return tuple(Sigil(value) for value in values)


def resolve_captured_cli_values(
    templates: Sequence[Sigil],
    project: Project,
    command_path: tuple[str, ...],
    *,
    paths: GwayPaths | None = None,
    extra_context: dict[str, object] | None = None,
) -> list[str]:
    """Resolve already-captured CLI templates with project-aware lazy context."""
    context = project_context(
        project,
        command_path,
        paths=paths,
        extra_context=extra_context,
    )
    return [template.solve(context) for template in templates]


def resolve_cli_values(
    values: Sequence[str],
    project: Project,
    command_path: tuple[str, ...],
    *,
    paths: GwayPaths | None = None,
    extra_context: dict[str, object] | None = None,
) -> list[str]:
    """Resolve CLI argument values using eager then project-aware lazy semantics."""
    templates = capture_cli_values(values, paths=paths)
    return resolve_captured_cli_values(
        templates,
        project,
        command_path,
        paths=paths,
        extra_context=extra_context,
    )


__all__ = [
    "RESERVED_CONTEXT_KEYS",
    "base_context",
    "capture_cli_values",
    "gway_context",
    "project_context",
    "resolve_captured_cli_values",
    "resolve_cli_values",
]
