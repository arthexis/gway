from __future__ import annotations

from collections.abc import Sequence

from ..config import GwayPaths
from ..project import Project
from ..sigils import resolve_cli_values


def resolve_service_values(
    values: Sequence[str],
    project: Project,
    service: str,
    *,
    paths: GwayPaths | None = None,
) -> list[str]:
    """Resolve service templates with the owning project's Sigil context.

    This deliberately reuses GWay's existing project-aware Sigil resolution
    path. Service rendering will consume this helper in a follow-up change;
    keeping resolution here avoids duplicating variable precedence or Sigil
    semantics inside the systemd renderer.
    """
    return resolve_cli_values(
        values,
        project,
        ("service", service),
        paths=paths,
    )


__all__ = ["resolve_service_values"]
