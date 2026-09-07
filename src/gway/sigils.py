from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sigils import Context, Sigil

from .config import GwayPaths, default_paths
from .project import Project


def base_context(paths: GwayPaths | None = None) -> dict[str, object]:
    """Return the context available before project resolution."""
    active_paths = paths or default_paths()
    return {
        "cwd": str(Path.cwd()),
        "home": str(Path.home()),
        "gway": {
            "config_dir": str(active_paths.config_dir),
            "data_dir": str(active_paths.data_dir),
        },
    }


def project_context(
    project: Project,
    command_path: tuple[str, ...],
    *,
    paths: GwayPaths | None = None,
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


def resolve_cli_values(
    values: Sequence[str],
    project: Project,
    command_path: tuple[str, ...],
    *,
    paths: GwayPaths | None = None,
) -> list[str]:
    """Resolve CLI argument values using eager then project-aware lazy semantics."""
    templates = capture_cli_values(values, paths=paths)
    context = project_context(project, command_path, paths=paths)
    return [template.solve(context) for template in templates]


__all__ = [
    "base_context",
    "capture_cli_values",
    "project_context",
    "resolve_cli_values",
]
