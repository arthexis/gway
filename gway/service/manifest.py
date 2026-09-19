"""Parsing for declarative project service manifests."""

from pathlib import Path

from .. import toml
from ..install.model import validate_name
from .model import Catalog, Service


_SERVICE_FIELDS = {
    "description",
    "command",
    "working_directory",
    "writable_paths",
    "profiles",
    "environment",
    "restart",
    "restart_sec",
    "autostart",
}


def _string(value, field, *, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _strings(value, field):
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array of strings")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain only non-empty strings")
        result.append(item)
    return tuple(result)


def _environment(value, field):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a table")
    result = {}
    for name, item in value.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{field} keys must be non-empty strings")
        if not isinstance(item, str):
            raise ValueError(f"{field}.{name} must be a string")
        result[name] = item
    return result


def _restart_sec(value, field):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a non-negative number")
    if value < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return float(value)


def service_from_data(project, root, name, data):
    """Normalize one [services.<name>] table."""
    validate_name(name)
    if not isinstance(data, dict):
        raise ValueError(f"[services.{name}] must be a table")

    unknown = sorted(set(data) - _SERVICE_FIELDS)
    if unknown:
        joined = ", ".join(unknown)
        raise ValueError(f"[services.{name}] has unknown fields: {joined}")

    command = _strings(data.get("command"), f"[services.{name}].command")
    if not command:
        raise ValueError(f"[services.{name}].command must not be empty")

    autostart = data.get("autostart", False)
    if not isinstance(autostart, bool):
        raise ValueError(f"[services.{name}].autostart must be a boolean")

    return Service(
        project=project,
        name=name,
        root=root,
        description=_string(
            data.get("description"),
            f"[services.{name}].description",
            optional=True,
        ),
        command=command,
        working_directory=_string(
            data.get("working_directory"),
            f"[services.{name}].working_directory",
            optional=True,
        ),
        writable_paths=_strings(
            data.get("writable_paths"),
            f"[services.{name}].writable_paths",
        ),
        profiles=_strings(
            data.get("profiles"),
            f"[services.{name}].profiles",
        ),
        environment=_environment(
            data.get("environment"),
            f"[services.{name}].environment",
        ),
        restart=_string(
            data.get("restart"),
            f"[services.{name}].restart",
            optional=True,
        ),
        restart_sec=_restart_sec(
            data.get("restart_sec"),
            f"[services.{name}].restart_sec",
        ),
        autostart=autostart,
    )


def catalog_from_data(data, *, root):
    """Normalize all service declarations from one project manifest mapping."""
    if not isinstance(data, dict):
        raise ValueError("gway.toml root must be a table")

    project_data = data.get("project")
    if not isinstance(project_data, dict):
        raise ValueError("[project] table is required for services")

    project = project_data.get("name")
    validate_name(project)

    profile_file = project_data.get("service_profile_file")
    if profile_file is not None:
        profile_file = _string(
            profile_file,
            "[project].service_profile_file",
        )

    services_data = data.get("services", {})
    if services_data is None:
        services_data = {}
    if not isinstance(services_data, dict):
        raise ValueError("[services] must be a table")

    services = tuple(
        service_from_data(project, root, name, service_data)
        for name, service_data in services_data.items()
    )
    return Catalog(
        project=project,
        root=root,
        services=services,
        profile_file=profile_file,
    )


def load(path):
    """Load and normalize one project's service catalog."""
    path = Path(path).expanduser().resolve()
    return catalog_from_data(toml.load(path), root=path.parent)
