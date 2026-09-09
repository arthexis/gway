from __future__ import annotations

import re
import tomllib
from typing import Any

from ..project import Project


class ServiceError(ValueError):
    pass


_SERVICE_KEY = re.compile(r"^[A-Za-z0-9_.-]+$")


def _strings(value: object, field: str, section: str = "service") -> list[str]:
    valid = isinstance(value, list) and all(isinstance(item, str) and item for item in value)
    if value is None:
        return []
    if not valid:
        message = f"[{section}].{field} must be an array of non-empty strings"
        raise ServiceError(message)
    return list(value)


def _manifest_services(project: Project) -> tuple[dict[str, dict[str, Any]], bool]:
    manifest = project.path / "gway.toml"
    try:
        with manifest.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ServiceError(f"cannot read service manifest for {project.name}: {exc}") from exc

    legacy = data.get("service")
    services = data.get("services")
    if legacy is not None and services is not None:
        raise ServiceError("gway.toml cannot declare both [service] and [services]")
    if legacy is not None:
        if not isinstance(legacy, dict):
            raise ServiceError("[service] must be a table")
        return {"default": dict(legacy)}, True
    if services is None:
        message = f"project does not declare [service] or [services]: {project.name}"
        raise ServiceError(message)
    if not isinstance(services, dict) or not services:
        raise ServiceError("[services] must contain at least one service table")

    result: dict[str, dict[str, Any]] = {}
    for key, config in services.items():
        if not isinstance(key, str) or not _SERVICE_KEY.fullmatch(key):
            raise ServiceError(f"invalid service key: {key!r}")
        if not isinstance(config, dict):
            raise ServiceError(f"[services.{key}] must be a table")
        result[key] = dict(config)
    return result, False
