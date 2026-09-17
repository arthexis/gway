"""Shared GWAY lifecycle operations used by CLI and runtime."""

from .install import install_project, uninstall_project
from .project import managed_status, runtime_component_record, upgrade_status
from .service import install_project_service, run_service
from .upgrade import run_upgrade

__all__ = [
    "install_project",
    "install_project_service",
    "managed_status",
    "run_service",
    "run_upgrade",
    "runtime_component_record",
    "uninstall_project",
    "upgrade_status",
]
