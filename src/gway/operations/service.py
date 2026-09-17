from __future__ import annotations

from collections.abc import Callable

from ..project import Project
from ..registry import Registry
from ..service import ServiceError, ServiceManager

ServiceManagerFactory = Callable[[Project], ServiceManager]


def install_project_service(
    project: Project,
    *,
    manager_factory: ServiceManagerFactory = ServiceManager,
) -> dict[str, object]:
    try:
        manager = manager_factory(project)
    except ServiceError as exc:
        if "does not declare [service] or [services]" not in str(exc):
            raise
        return {
            "status": "not-provided",
            "message": f"{project.name} does not provide a service",
        }
    unit = manager.install()
    return {"status": "installed", "unit": unit}


def run_service(
    registry: Registry,
    *,
    action: str,
    project_name: str,
    user: str | None = None,
    enable: bool = True,
    start: bool = True,
    manager_factory: ServiceManagerFactory = ServiceManager,
) -> object:
    project = registry.require(project_name)
    manager = manager_factory(project)
    if action == "install":
        unit = manager.install(user=user, enable=enable, start=start)
        return {"status": "installed", "project": project.name, "unit": unit}
    if action == "uninstall":
        removed = manager.uninstall()
        return {"status": "uninstalled", "project": project.name, "removed": removed}
    if action == "start":
        manager.start()
        return {"status": "started", "project": project.name, "unit": manager.unit_name}
    if action == "stop":
        manager.stop()
        return {"status": "stopped", "project": project.name, "unit": manager.unit_name}
    if action == "restart":
        manager.restart()
        return {"status": "restarted", "project": project.name, "unit": manager.unit_name}
    return manager.status()
