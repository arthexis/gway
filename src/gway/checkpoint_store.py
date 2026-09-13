from __future__ import annotations

import errno
import json
import os
import stat
import uuid
from pathlib import Path

from .checkpoint import CheckpointError, ResumeCheckpoint
from .checkpoint_stack import CONTINUATION_STACK_VERSION, ContinuationStackCheckpoint

_UNSUPPORTED_DIR_FSYNC_ERRNOS = {
    value
    for value in (
        errno.EINVAL,
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
    )
    if value is not None
}

CheckpointDocument = ResumeCheckpoint | ContinuationStackCheckpoint


def checkpoint_directory(data_dir: Path) -> Path:
    """Return the directory reserved for resumable runtime checkpoints."""
    return Path(data_dir) / "checkpoints"


def _ensure_private_directory(directory: Path) -> None:
    """Create a private checkpoint directory or reject an insecure existing one."""
    created = False
    try:
        directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        created = True
    except FileExistsError:
        pass
    except OSError as exc:
        raise CheckpointError(f"cannot prepare checkpoint directory {directory}: {exc}") from exc

    try:
        info = directory.stat()
    except OSError as exc:
        raise CheckpointError(f"cannot inspect checkpoint directory {directory}: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise CheckpointError(f"checkpoint path is not a directory: {directory}")

    if os.name == "nt":
        return

    geteuid = getattr(os, "geteuid", None)
    if callable(geteuid) and info.st_uid != geteuid():
        raise CheckpointError(f"checkpoint directory is not owned by the current user: {directory}")
    mode = stat.S_IMODE(info.st_mode)
    if created:
        try:
            os.chmod(directory, 0o700)
        except OSError as exc:
            raise CheckpointError(
                f"cannot restrict checkpoint directory {directory}: {exc}"
            ) from exc
    elif mode & 0o077:
        raise CheckpointError(
            f"checkpoint directory must not be accessible by group or others: {directory}"
        )


def write_checkpoint_atomic(checkpoint: CheckpointDocument, data_dir: Path) -> Path:
    """Persist one checkpoint atomically and return its final path."""
    directory = checkpoint_directory(data_dir)
    _ensure_private_directory(directory)

    checkpoint_id = uuid.uuid4().hex
    target = directory / f"{checkpoint_id}.json"
    temporary = directory / f".{checkpoint_id}.tmp"
    try:
        payload = (checkpoint.to_json() + "\n").encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CheckpointError(f"checkpoint contains text that cannot be encoded as UTF-8: {exc}") from exc

    descriptor: int | None = None
    replaced = False
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        replaced = True
        if os.name != "nt":
            os.chmod(target, 0o600)
        _sync_directory(directory)
    except (OSError, CheckpointError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        if replaced:
            try:
                target.unlink(missing_ok=True)
            except OSError as cleanup_exc:
                raise CheckpointError(
                    f"cannot persist checkpoint in {directory}: {exc}; "
                    f"failed checkpoint may remain at {target}: {cleanup_exc}"
                ) from exc
        if isinstance(exc, CheckpointError):
            raise
        raise CheckpointError(f"cannot persist checkpoint in {directory}: {exc}") from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    return target


def claim_checkpoint(path: str | Path) -> Path:
    """Atomically claim a checkpoint so only one resume process can execute it."""
    original = Path(path)
    claimed = original.with_name(
        f".{original.name}.{os.getpid()}.{uuid.uuid4().hex}.in-progress"
    )
    try:
        os.replace(original, claimed)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            raise CheckpointError(
                f"cannot read checkpoint; cannot claim checkpoint {original}: {exc}"
            ) from exc
        raise CheckpointError(f"cannot claim checkpoint {original}: {exc}") from exc
    try:
        _sync_directory(original.parent)
    except CheckpointError:
        try:
            os.replace(claimed, original)
            _sync_directory(original.parent)
        except (OSError, CheckpointError):
            pass
        raise
    return claimed


def restore_checkpoint(claimed: str | Path, original: str | Path) -> None:
    """Restore a claimed checkpoint after a failed resume attempt."""
    claimed_path = Path(claimed)
    original_path = Path(original)
    if original_path.exists():
        raise CheckpointError(
            f"cannot restore checkpoint because target already exists: {original_path}"
        )
    try:
        os.replace(claimed_path, original_path)
    except OSError as exc:
        raise CheckpointError(
            f"cannot restore checkpoint {original_path}: {exc}"
        ) from exc
    _sync_directory(original_path.parent)


def read_checkpoint(path: str | Path) -> CheckpointDocument:
    """Read and validate one persisted v1 or v2 checkpoint without consuming it."""
    checkpoint_path = Path(path)
    try:
        payload = checkpoint_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CheckpointError(f"cannot read checkpoint {checkpoint_path}: {exc}") from exc

    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return ResumeCheckpoint.from_json(payload)
    if isinstance(decoded, dict) and decoded.get("version") == CONTINUATION_STACK_VERSION:
        return ContinuationStackCheckpoint.from_json(payload)
    return ResumeCheckpoint.from_json(payload)


def remove_checkpoint(path: str | Path) -> None:
    """Remove a successfully consumed checkpoint."""
    checkpoint_path = Path(path)
    try:
        checkpoint_path.unlink()
    except OSError as exc:
        raise CheckpointError(f"cannot remove checkpoint {checkpoint_path}: {exc}") from exc
    _sync_directory(checkpoint_path.parent)


def _sync_directory(directory: Path) -> None:
    """Fsync a directory, ignoring only filesystems that explicitly do not support it."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor: int | None = None
    try:
        descriptor = os.open(directory, flags)
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_DIR_FSYNC_ERRNOS:
            return
        raise CheckpointError(f"cannot sync checkpoint directory {directory}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


__all__ = [
    "CheckpointDocument",
    "checkpoint_directory",
    "claim_checkpoint",
    "read_checkpoint",
    "remove_checkpoint",
    "restore_checkpoint",
    "write_checkpoint_atomic",
]
