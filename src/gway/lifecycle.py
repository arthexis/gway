from __future__ import annotations

from .adapters import AdapterRegistry
from .project import Project
from .runner import RunnerError


class LifecycleError(RunnerError):
    pass


def run_hook(project: Project, name: str) -> object:
    """Run one optional project lifecycle hook through its normal adapter."""
    config = project.lifecycle_config or {}
    command_name = config.get(name)
    if command_name is None:
        return None
    adapter = AdapterRegistry().create(project)
    try:
        return adapter.run((str(command_name),), [])
    except SystemExit as exc:
        if exc.code in (None, 0):
            return None
        raise LifecycleError(
            f"lifecycle hook {name!r} failed with exit status {exc.code}"
        ) from exc
