from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..config import GwayPaths
from ..dispatcher.errors import DispatchError

_STATE_VERSION = 1


def state_path(paths: GwayPaths) -> Path:
    return paths.data_dir / "log-consumers.json"


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def read_state_path(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"version": _STATE_VERSION, "bindings": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DispatchError(f"cannot read log consumer state {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != _STATE_VERSION:
        raise DispatchError(f"unsupported log consumer state in {path}")
    bindings = data.get("bindings")
    if not isinstance(bindings, dict):
        raise DispatchError(f"unsupported log consumer state in {path}")
    return data


def read_state(paths: GwayPaths) -> dict[str, object]:
    return read_state_path(state_path(paths))


def atomic_private_write(path: Path, payload: bytes) -> None:
    private_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_state(paths: GwayPaths, data: dict[str, object]) -> None:
    path = state_path(paths)
    payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_private_write(path, payload)


@contextmanager
def state_lock(paths: GwayPaths) -> Iterator[None]:
    """Serialize logging-state transactions across GWAY processes."""
    path = state_path(paths).with_suffix(".lock")
    private_directory(path.parent)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(path, flags, 0o600)
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


__all__ = [
    "atomic_private_write",
    "read_state",
    "read_state_path",
    "state_lock",
    "state_path",
    "write_state",
]
