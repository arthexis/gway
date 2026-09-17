from __future__ import annotations

from collections.abc import Callable, Sequence

from ..install import Installer
from ..project import Project
from ..registry import Registry
from ..service import ServiceManager
from .project import managed_status, runtime_component_record
from .service import install_project_service

InstallerFactory = Callable[[Registry], Installer]
ServiceManagerFactory = Callable[[Project], ServiceManager]


def install_project(
    registry: Registry,
    project_name: str,
    *,
    arguments: Sequence[str] = (),
    service: bool = False,
    installer_factory: InstallerFactory = Installer,
    manager_factory: ServiceManagerFactory = ServiceManager,
) -> dict[str, object]:
    result = runtime_component_record(project_name)
    if result is not None:
        if arguments:
            raise ValueError("built-in runtime component install does not accept arguments")
        if service:
            result["service"] = {
                "status": "not-provided",
                "message": f"{project_name} does not provide a service",
            }
        return result

    installer = installer_factory(registry)
    if arguments:
        project = installer.install(project_name, arguments=arguments)
    else:
        project = installer.install(project_name)
    result = managed_status("installed", project)
    if service:
        result["service"] = install_project_service(project, manager_factory=manager_factory)
    return result


def uninstall_project(
    registry: Registry,
    project_name: str,
    *,
    installer_factory: InstallerFactory = Installer,
) -> dict[str, object]:
    project = installer_factory(registry).uninstall(project_name)
    return managed_status("uninstalled", project)
