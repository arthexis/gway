from __future__ import annotations

import os
import uuid
from pathlib import Path

from .checkpoint import CheckpointError, ResumeCheckpoint


def checkpoint_directory(data_dir: Path) -> Path:
    """Return the directory reserved for resumable runtime checkpoints."""
    return Path(data_dir) / "checkpoints"


def write_checkpoint_atomic(checkpoint: ResumeCheckpoint, data_dir: Path) -> Path:
    """Persist one checkpoint atomically and return its final path."""
    directory = checkpoint_directory(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    checkpoint_id = uuid.uuid4().hex
    target = directory / f"{checkpoint_id}.json"
    temporary = directory / f".{checkpoint_id}.tmp"
    payload = checkpoint.to_json() + "\n"

    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        _sync_directory(directory)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise CheckpointError(f"cannot persist checkpoint in {directory}: {exc}") from exc
    return target


def read_checkpoint(path: str | Path) -> ResumeCheckpoint:
    """Read and validate one persisted checkpoint without consuming it."""
    checkpoint_path = Path(path)
    try:
        payload = checkpoint_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckpointError(f"cannot read checkpoint {checkpoint_path}: {exc}") from exc
    return ResumeCheckpoint.from_json(payload)


def remove_checkpoint(path: str | Path) -> None:
    """Remove a successfully consumed checkpoint."""
    checkpoint_path = Path(path)
    try:
        checkpoint_path.unlink()
    except OSError as exc:
        raise CheckpointError(f"cannot remove checkpoint {checkpoint_path}: {exc}") from exc


def _sync_directory(directory: Path) -> None:
    """Best-effort fsync of a directory after the atomic rename."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor: int | None = None
    try:
        descriptor = os.open(directory, flags)
        os.fsync(descriptor)
    except OSError:
        # The file itself is already fsynced and atomically renamed. Some
        # filesystems do not permit directory fsync, so this remains best-effort.
        return
    finally:
        if descriptor is not None:
            os.close(descriptor)


__all__ = [
    "checkpoint_directory",
    "read_checkpoint",
    "remove_checkpoint",
    "write_checkpoint_atomic",
]
