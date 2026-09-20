"""Filesystem snapshot and restoration primitives for rollback journals."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any


class SnapshotError(RuntimeError):
    """Raised when a filesystem object cannot be snapshotted or restored safely."""


class DriftError(SnapshotError):
    """Raised when a rollback target no longer matches GWay's applied state."""


def _fingerprint_metadata(info) -> dict[str, int]:
    return {
        "mode": stat.S_IMODE(info.st_mode),
        "uid": int(info.st_uid),
        "gid": int(info.st_gid),
        "mtime_ns": int(info.st_mtime_ns),
    }


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_path(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Return a deterministic rollback-safety fingerprint for one path."""
    target = Path(path)
    try:
        info = target.lstat()
    except FileNotFoundError:
        return {
            "path": str(target),
            "existed": False,
        }

    kind = _kind(info.st_mode)
    fingerprint: dict[str, Any] = {
        "path": str(target),
        "existed": True,
        "type": kind,
        **_fingerprint_metadata(info),
    }

    if kind == "file":
        fingerprint["sha256"] = _file_digest(target)
    elif kind == "symlink":
        fingerprint["target"] = os.readlink(target)
    elif kind == "directory":
        children = []
        for child in sorted(target.iterdir(), key=lambda value: value.name):
            nested = fingerprint_path(child)
            nested["path"] = child.name
            children.append(nested)
        fingerprint["children"] = children

    return fingerprint


def verify_fingerprint(expected: dict[str, Any]) -> None:
    """Raise when a path has drifted from an expected applied-state fingerprint."""
    current = fingerprint_path(str(expected["path"]))
    if current != expected:
        raise DriftError(
            f"Rollback conflict: {expected['path']} changed after GWay applied it"
        )


def _kind(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    raise SnapshotError("unsupported filesystem object type")


def _metadata(path: Path, *, follow_symlinks: bool) -> dict[str, int]:
    value = path.stat() if follow_symlinks else path.lstat()
    return {
        "mode": stat.S_IMODE(value.st_mode),
        "uid": int(value.st_uid),
        "gid": int(value.st_gid),
        "atime_ns": int(value.st_atime_ns),
        "mtime_ns": int(value.st_mtime_ns),
    }


def _apply_owner(path: Path, uid: int, gid: int, *, follow_symlinks: bool) -> None:
    if not hasattr(os, "chown"):
        return
    try:
        current = path.stat() if follow_symlinks else path.lstat()
    except FileNotFoundError:
        return
    if current.st_uid == uid and current.st_gid == gid:
        return
    os.chown(path, uid, gid, follow_symlinks=follow_symlinks)


def _apply_times(
    path: Path,
    atime_ns: int,
    mtime_ns: int,
    *,
    follow_symlinks: bool,
) -> None:
    os.utime(
        path,
        ns=(int(atime_ns), int(mtime_ns)),
        follow_symlinks=follow_symlinks,
    )


def _apply_metadata(
    path: Path,
    snapshot: dict[str, Any],
    *,
    follow_symlinks: bool,
) -> None:
    if follow_symlinks:
        os.chmod(path, int(snapshot["mode"]))
    _apply_owner(
        path,
        int(snapshot["uid"]),
        int(snapshot["gid"]),
        follow_symlinks=follow_symlinks,
    )
    try:
        _apply_times(
            path,
            int(snapshot["atime_ns"]),
            int(snapshot["mtime_ns"]),
            follow_symlinks=follow_symlinks,
        )
    except (NotImplementedError, OSError):
        if follow_symlinks:
            raise


def _remove_existing(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise SnapshotError(f"cannot remove unsupported filesystem object: {path}")


def capture_path(
    path: str | os.PathLike[str],
    storage: str | os.PathLike[str],
) -> dict[str, Any]:
    """Capture one path and metadata into journal-owned storage."""
    target = Path(path)
    storage_path = Path(storage)
    storage_path.mkdir(parents=True, exist_ok=True, mode=0o700)
    storage_path.chmod(0o700)

    try:
        info = target.lstat()
    except FileNotFoundError:
        return {
            "path": str(target),
            "existed": False,
        }

    kind = _kind(info.st_mode)
    snapshot: dict[str, Any] = {
        "path": str(target),
        "existed": True,
        "type": kind,
        **_metadata(target, follow_symlinks=False),
    }

    if kind == "file":
        backup = storage_path / "data"
        shutil.copyfile(target, backup, follow_symlinks=False)
        backup.chmod(0o600)
        snapshot["snapshot"] = backup.name
    elif kind == "directory":
        backup = storage_path / "tree"
        shutil.copytree(
            target,
            backup,
            symlinks=True,
            copy_function=shutil.copy2,
        )
        snapshot["snapshot"] = backup.name
    elif kind == "symlink":
        snapshot["target"] = os.readlink(target)

    return snapshot


def _restore_file(path: Path, backup: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.gway-rollback-",
        dir=path.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(backup, temporary, follow_symlinks=False)
        _apply_metadata(temporary, snapshot, follow_symlinks=True)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _restore_directory(path: Path, backup: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{path.name}.gway-rollback-",
            dir=path.parent,
        )
    )
    temporary.rmdir()
    try:
        shutil.copytree(
            backup,
            temporary,
            symlinks=True,
            copy_function=shutil.copy2,
        )
        _apply_metadata(temporary, snapshot, follow_symlinks=True)
        _remove_existing(path)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _restore_symlink(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.gway-rollback-link-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    try:
        os.symlink(str(snapshot["target"]), temporary)
        _apply_metadata(temporary, snapshot, follow_symlinks=False)
        if path.is_dir() and not path.is_symlink():
            _remove_existing(path)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def restore_path(
    snapshot: dict[str, Any],
    storage: str | os.PathLike[str],
    *,
    expected: dict[str, Any] | None = None,
) -> Path:
    """Restore one captured path, optionally refusing to overwrite drifted state."""
    if expected is not None:
        verify_fingerprint(expected)
    path = Path(str(snapshot["path"]))

    if not bool(snapshot.get("existed")):
        _remove_existing(path)
        return path

    kind = str(snapshot["type"])
    storage_path = Path(storage)

    if kind == "file":
        if path.is_dir() and not path.is_symlink():
            _remove_existing(path)
        _restore_file(path, storage_path / str(snapshot["snapshot"]), snapshot)
        return path

    if kind == "directory":
        _restore_directory(
            path,
            storage_path / str(snapshot["snapshot"]),
            snapshot,
        )
        return path

    if kind == "symlink":
        _restore_symlink(path, snapshot)
        return path

    raise SnapshotError(f"unsupported snapshot type: {kind}")
