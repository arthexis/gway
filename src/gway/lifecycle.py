from __future__ import annotations

from .adapters import AdapterRegistry
from .project import Project


def run_hook(project: Project, name: str) -> object:
    """Run one optional project lifecycle hook through its normal adapter."""
    config = project.lifecycle_config or {}
    command_name = config.get(name)
    if command_name is None:
        return None
    adapter = AdapterRegistry().create(project)
    return adapter.run((str(command_name),), [])
