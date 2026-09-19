"""Parsing for declarative Sous Chef jobs."""

import re
from pathlib import Path

from .. import toml
from ..install.model import validate_name
from .model import DEFAULT_TIMEOUT, Job


_DURATION = re.compile(r"^(?P<value>\d+(?:\.\d+)?)(?P<unit>[smhd])$")
_FACTORS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}
_FIELDS = {"recipe", "every", "watch", "down", "timeout"}


def duration(value, field):
    """Normalize a compact duration string to seconds."""
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a duration such as '15m'")
    if isinstance(value, (int, float)):
        if value <= 0:
            raise ValueError(f"{field} must be greater than zero")
        return float(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a duration such as '15m'")

    match = _DURATION.fullmatch(value.strip().lower())
    if match is None:
        raise ValueError(f"{field} must be a duration such as '15m'")

    seconds = float(match.group("value")) * _FACTORS[match.group("unit")]
    if seconds <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return seconds


def _path(root, value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty path string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(root) / path
    return path.resolve()


def _target(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty target string")
    return value.strip()


def job_from_data(name, data, *, root):
    """Normalize one [sous-chef.<name>] table."""
    validate_name(name)
    if not isinstance(data, dict):
        raise ValueError(f"[sous-chef.{name}] must be a table")

    unknown = sorted(set(data) - _FIELDS)
    if unknown:
        raise ValueError(
            f"[sous-chef.{name}] has unknown fields: {', '.join(unknown)}"
        )

    recipe = _path(root, data.get("recipe"), f"[sous-chef.{name}].recipe")
    every = (
        duration(data["every"], f"[sous-chef.{name}].every")
        if "every" in data
        else None
    )
    watch = (
        _path(root, data["watch"], f"[sous-chef.{name}].watch")
        if "watch" in data
        else None
    )
    down = (
        _target(data["down"], f"[sous-chef.{name}].down")
        if "down" in data
        else None
    )
    timeout = (
        duration(data["timeout"], f"[sous-chef.{name}].timeout")
        if "timeout" in data
        else float(DEFAULT_TIMEOUT)
    )

    return Job(
        name=name,
        root=root,
        recipe=recipe,
        every=every,
        watch=watch,
        down=down,
        timeout=timeout,
    )


def jobs_from_data(data, *, root):
    """Normalize all Sous Chef jobs from one manifest mapping."""
    if not isinstance(data, dict):
        raise ValueError("gway.toml root must be a table")

    jobs = data.get("sous-chef", {})
    if jobs is None:
        jobs = {}
    if not isinstance(jobs, dict):
        raise ValueError("[sous-chef] must be a table")

    return tuple(
        job_from_data(name, value, root=root)
        for name, value in jobs.items()
    )


def load(path):
    """Load Sous Chef jobs from one gway.toml."""
    path = Path(path).expanduser().resolve()
    return jobs_from_data(toml.load(path), root=path.parent)
