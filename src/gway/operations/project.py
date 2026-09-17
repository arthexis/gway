from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import version as distribution_version

from ..project import Project
from ..upgrade import UpgradeResult

RUNTIME_COMPONENTS = {"sigils": "gway-sigils"}


def runtime_component_record(
    name: str,
    *,
    version_resolver: Callable[[str], str] = distribution_version,
) -> dict[str, object] | None:
    distribution = RUNTIME_COMPONENTS.get(name)
    if distribution is None:
        return None
    return {
        "status": "installed",
        "name": name,
        "distribution": distribution,
        "version": version_resolver(distribution),
    }


def managed_status(status: str, project: Project) -> dict[str, object]:
    record: dict[str, object] = {
        "status": status,
        "name": project.name,
        "path": project.path,
    }
    if project.repository:
        record["repository"] = project.repository
    if project.revision:
        record["revision"] = project.revision
    return record


def upgrade_status(status: str, result: UpgradeResult) -> dict[str, object]:
    record = managed_status(status, result.project)
    record["force_used"] = bool(getattr(result, "force_used", False))
    force_error_type = getattr(result, "force_error_type", None)
    force_error = getattr(result, "force_error", None)
    dirty_files = getattr(result, "dirty_files", ())
    if force_error_type is not None:
        record["force_error_type"] = force_error_type
    if force_error is not None:
        record["force_error"] = force_error
    if dirty_files:
        record["dirty_files"] = [
            {
                "status": entry.status,
                "path": entry.path,
                **(
                    {"original_path": entry.original_path}
                    if entry.original_path is not None
                    else {}
                ),
            }
            for entry in dirty_files
        ]
    return record
