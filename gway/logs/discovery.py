"""Discover logical log sources from installed service state."""

from .identity import project_identity, service_identity
from .source import LogSource


def installed_sources(state):
    """Return project and service log sources from one install-state registry."""
    records = list(state.all())
    projects = sorted({record.project for record in records})
    sources = [
        LogSource(
            identity=project_identity(project),
            kind="project",
            project=project,
        )
        for project in projects
    ]

    sources.extend(
        LogSource(
            identity=service_identity(record.project, record.service),
            kind="service",
            project=record.project,
            service=record.service,
            backend=record.backend,
            backend_id=record.backend_id,
            system=record.system,
        )
        for record in sorted(
            records,
            key=lambda item: (
                item.project,
                item.service,
                item.backend,
                item.backend_id,
                item.system,
            ),
        )
    )
    return sources
