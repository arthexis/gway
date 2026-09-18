from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..config import GwayPaths, default_paths
from ..project import Project
from .manifest import ServiceError

_STATE_ENV = "GWAY_SERVICE_ATTACHMENT_STATE"
_STATE_VERSION = 1
_ALL_SERVICES = "*"


@dataclass(frozen=True)
class ServiceAttachment:
    """Provider-owned files attached to one project service."""

    owner: str
    environment_files: tuple[Path, ...] = ()


def _state_path(paths: GwayPaths | None = None) -> Path:
    if paths is not None:
        return paths.data_dir / "service-attachments.json"
    inherited = os.environ.get(_STATE_ENV)
    if inherited:
        return Path(inherited).expanduser()
    return default_paths().data_dir / "service-attachments.json"


@contextmanager
def _state_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path.parent.chmod(0o700)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            while True:
                try:
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _read_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"version": _STATE_VERSION, "projects": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ServiceError(f"cannot read service attachment state {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != _STATE_VERSION:
        raise ServiceError(f"unsupported service attachment state in {path}")
    projects = data.get("projects")
    if not isinstance(projects, dict):
        raise ServiceError(f"unsupported service attachment state in {path}")
    return data


def _write_state(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _attachment_files(files: tuple[Path, ...] | list[Path]) -> list[str]:
    result: list[str] = []
    for value in files:
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ServiceError("service attachment environment files must be absolute paths")
        text = str(path)
        if "\0" in text or "\n" in text or "\r" in text:
            raise ServiceError(
                "service attachment environment files must not contain NUL characters or newlines"
            )
        if text not in result:
            result.append(text)
    return result


def attach_environment_files(
    project: str,
    *,
    owner: str,
    environment_files: tuple[Path, ...] | list[Path],
    service: str | None = None,
    paths: GwayPaths | None = None,
) -> None:
    """Replace one owner's environment-file attachment for a project service."""
    if not project or not owner:
        raise ServiceError("service attachment project and owner must be non-empty")
    target = _state_path(paths)
    with _state_lock(target):
        state = _read_state(target)
        projects = state["projects"]
        assert isinstance(projects, dict)
        project_state = projects.setdefault(project.casefold(), {})
        if not isinstance(project_state, dict):
            raise ServiceError(f"unsupported service attachment state for {project}")
        service_key = (service or _ALL_SERVICES).casefold()
        service_state = project_state.setdefault(service_key, {})
        if not isinstance(service_state, dict):
            raise ServiceError(f"unsupported service attachment state for {project}")
        files = _attachment_files(environment_files)
        if files:
            service_state[owner] = {"environment_files": files}
        else:
            service_state.pop(owner, None)
        if not service_state:
            project_state.pop(service_key, None)
        if not project_state:
            projects.pop(project.casefold(), None)
        _write_state(target, state)
    os.environ[_STATE_ENV] = str(target)


def detach_environment_files(
    project: str,
    *,
    owner: str,
    service: str | None = None,
    paths: GwayPaths | None = None,
) -> None:
    """Remove one owner's environment-file attachment if present."""
    attach_environment_files(
        project,
        owner=owner,
        environment_files=[],
        service=service,
        paths=paths,
    )


def service_environment_files(
    project: Project,
    service: str,
    *,
    paths: GwayPaths | None = None,
) -> tuple[Path, ...]:
    """Return generic environment files attached to one service."""
    state = _read_state(_state_path(paths))
    projects = state["projects"]
    assert isinstance(projects, dict)
    files: list[Path] = []
    identities = (project.name, *project.aliases)
    for identity in identities:
        project_state = projects.get(identity.casefold())
        if not isinstance(project_state, dict):
            continue
        for scope in (_ALL_SERVICES, service.casefold()):
            service_state = project_state.get(scope)
            if not isinstance(service_state, dict):
                continue
            for owner in sorted(service_state):
                attachment = service_state[owner]
                if not isinstance(attachment, dict):
                    continue
                values = attachment.get("environment_files", [])
                if not isinstance(values, list):
                    continue
                for value in values:
                    if not isinstance(value, str):
                        continue
                    path = Path(value)
                    if path not in files:
                        files.append(path)
    return tuple(files)


__all__ = [
    "ServiceAttachment",
    "attach_environment_files",
    "detach_environment_files",
    "service_environment_files",
]
