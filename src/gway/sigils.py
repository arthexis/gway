from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from sigils import Context, SafeNamespace, Sigil

from .command import command_path_aliases
from .config import GwayPaths, default_paths
from .project import Project
from .registry import Registry

RESERVED_CONTEXT_KEYS = frozenset({"cwd", "home", "gway", "project", "command"})
_SIGILS_SUPPORTS_PROVIDER_CALLS = hasattr(Sigil, "_provider_callable")
_ENVIRONMENT_PREFIX = "GWAY_"
_ENVIRONMENT_SEPARATOR = re.compile(r"[^A-Za-z0-9]+")


def _normalize_environment_name(name: str) -> str:
    return _ENVIRONMENT_SEPARATOR.sub("_", name).strip("_").upper()


def semantic_environment_name(name: str) -> str:
    """Return the deterministic GWAY_* environment name for a semantic variable."""
    return f"{_ENVIRONMENT_PREFIX}{_normalize_environment_name(name)}"


def project_environment_name(project: Project, path: Sequence[str]) -> str | None:
    """Return a project's native environment route for an owned semantic path."""
    if project.environment_prefix is None or len(path) < 2:
        return None
    if path[0].casefold() != project.name.casefold():
        return None
    suffix = _normalize_environment_name(".".join(path[1:]))
    if not suffix:
        return None
    return f"{project.environment_prefix}_{suffix}"


def _resolve_semantic_value(
    value: object,
    path: tuple[str, ...],
    project: Project,
) -> object:
    """Resolve one manifest variable tree through native then GWAY_* overrides."""
    if isinstance(value, Mapping):
        return {
            str(key): _resolve_semantic_value(item, (*path, str(key)), project)
            for key, item in value.items()
        }

    native_name = project_environment_name(project, path)
    if native_name is not None and native_name in os.environ:
        return os.environ[native_name]

    semantic_name = ".".join(path)
    environment_name = semantic_environment_name(semantic_name)
    return os.environ.get(environment_name, value)


def _freeze(value: object) -> object:
    """Return a hashable representation suitable for per-evaluation memoization."""
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


def _alias_arguments(project: Project, project_name: str) -> tuple[str, ...]:
    return (project.alias_arguments or {}).get(project_name.casefold(), ())


class _GwayCommandCall:
    """Provider-approved callable wrapper around one registered GWAY command."""

    __sigils_safe_callable__ = True

    def __init__(
        self,
        registry: Registry,
        project_name: str,
        command,
        cache: dict[tuple[object, ...], object],
    ) -> None:
        self.registry = registry
        self.project_name = project_name
        self.command = command
        self.cache = cache
        project = registry.require(project_name)
        alias_arguments = _alias_arguments(project, project_name)
        self.__sigils_requires_args__ = not alias_arguments and any(
            parameter.required for parameter in command.parameters
        )

    def __call__(self, *args: object, **kwargs: object) -> object:
        if self.__sigils_requires_args__ and not args and not kwargs:
            return None

        project = self.registry.require(self.project_name)
        alias_arguments = _alias_arguments(project, self.project_name)
        cache_key = (
            project.name,
            alias_arguments,
            self.command.path,
            _freeze(args),
            _freeze(kwargs),
        )
        if cache_key in self.cache:
            return self.cache[cache_key]

        function = self.command.adapter_data
        if callable(function) and not alias_arguments:
            from .outcome import resolve_outcome

            result = resolve_outcome(function(*args, **kwargs))
        else:
            from .dispatcher import Dispatcher

            argv: list[str] = []
            for value in args:
                if isinstance(value, tuple):
                    argv.append(",".join(str(item) for item in value))
                else:
                    argv.append(str(value))
            for name, value in kwargs.items():
                option = f"--{name.replace('_', '-')}"
                if isinstance(value, bool):
                    argv.append(option if value else f"--no-{option[2:]}")
                else:
                    rendered = (
                        ",".join(str(item) for item in value)
                        if isinstance(value, tuple)
                        else str(value)
                    )
                    argv.extend((option, rendered))
            result = Dispatcher(registry=self.registry).run(
                self.project_name,
                (*self.command.path, *argv),
            )

        self.cache[cache_key] = result
        return result


class _GwayNamespaceProvider:
    """Resolve registered managed commands as protected Sigil values/callables."""

    def __init__(
        self,
        registry: Registry,
        project_name: str,
        *,
        prefix: tuple[str, ...] = (),
        cache: dict[tuple[object, ...], object] | None = None,
    ) -> None:
        self.registry = registry
        self.project_name = project_name
        self.prefix = prefix
        self.cache = cache if cache is not None else {}

    def resolve_sigil(self, key: str) -> object:
        command_key = key.replace("_", "-")
        path = (*self.prefix, command_key)

        from .dispatcher import Dispatcher

        dispatcher = Dispatcher(registry=self.registry)
        commands = dispatcher.commands(self.project_name)
        command_map = {command.path: command for command in commands}

        command = command_map.get(path)
        resolved_path = path
        if command is None:
            for candidate, item in command_map.items():
                aliases = command_path_aliases(candidate)[1:]
                if path in aliases:
                    command = item
                    resolved_path = candidate
                    break
        if command is not None:
            if not _SIGILS_SUPPORTS_PROVIDER_CALLS:
                if any(parameter.required for parameter in command.parameters):
                    raise KeyError(key)
                project = self.registry.require(self.project_name)
                alias_arguments = _alias_arguments(project, self.project_name)
                cache_key = (project.name, alias_arguments, resolved_path, (), ())
                if cache_key not in self.cache:
                    self.cache[cache_key] = dispatcher.run(self.project_name, resolved_path)
                return self.cache[cache_key]

            return _GwayCommandCall(
                self.registry,
                self.project_name,
                command,
                self.cache,
            )

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
    same managed command and arguments within that scope reuse its value;
    callers that need live values should call ``gway_context()`` again for each
    evaluation or render frame.
    """
    active_registry = registry or Registry(paths or default_paths())
    cache: dict[tuple[object, ...], object] = {}
    context: dict[str, object] = {}

    for project in active_registry.list():
        for name in (project.name, *project.aliases):
            if name in RESERVED_CONTEXT_KEYS:
                continue
            namespace = SafeNamespace(
                _GwayNamespaceProvider(
                    active_registry,
                    name,
                    cache=cache,
                )
            )
            context[name] = namespace
            context.setdefault(name.casefold(), namespace)

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
    """Return the lazy-resolution context for one dispatched command.

    Project ``[variables]`` values define semantic Sigil variables. Project-owned
    leaves may first resolve through a declared native environment prefix, then
    through the universal ``GWAY_*`` fallback. Runtime ``extra_context`` values
    have highest precedence. Framework-owned and managed namespaces stay protected.
    """
    context = base_context(paths)

    protected_names = set(context) | RESERVED_CONTEXT_KEYS
    for key, value in (project.variables or {}).items():
        if key in protected_names:
            continue
        context[key] = _resolve_semantic_value(value, (key,), project)

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
                "environment_prefix": project.environment_prefix,
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
    "project_environment_name",
    "resolve_captured_cli_values",
    "resolve_cli_values",
    "semantic_environment_name",
]
