"""Local project source inspection and content identity."""

import hashlib
import os
from pathlib import Path

from gway import toml
from .model import validate_name


_IGNORED_PARTS = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)


def local_source(value):
    """Resolve and validate one local project directory."""
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"Local install source does not exist: {value}")
    if not path.is_dir():
        raise ValueError(f"Local install source must be a directory: {path}")
    return path


def project_name(root):
    """Read the required [project].name from a local gway.toml."""
    root = local_source(root)
    manifest = root / "gway.toml"
    if not manifest.is_file():
        raise ValueError(f"Install source requires gway.toml: {root}")

    data = toml.load(manifest)
    project = data.get("project") if isinstance(data, dict) else None
    name = project.get("name") if isinstance(project, dict) else None
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Install source requires non-empty [project].name")
    try:
        return validate_name(name)
    except ValueError as exc:
        raise ValueError(f"Invalid [project].name: {exc}") from exc


def _ignored(path, root):
    relative = path.relative_to(root)
    return any(part in _IGNORED_PARTS for part in relative.parts)


def fingerprint(root):
    """Return a stable content fingerprint for one local project tree."""
    root = local_source(root)
    value = hashlib.sha256()

    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if _ignored(path, root):
            continue

        relative = path.relative_to(root).as_posix().encode("utf-8")
        stat = path.lstat()
        mode = stat.st_mode & 0o777

        if path.is_symlink():
            value.update(b"L\0")
            value.update(relative)
            value.update(b"\0")
            value.update(f"{mode:o}".encode("ascii"))
            value.update(b"\0")
            value.update(os.readlink(path).encode("utf-8"))
            value.update(b"\0")
            continue

        if path.is_dir():
            value.update(b"D\0")
            value.update(relative)
            value.update(b"\0")
            value.update(f"{mode:o}".encode("ascii"))
            value.update(b"\0")
            continue

        if path.is_file():
            value.update(b"F\0")
            value.update(relative)
            value.update(b"\0")
            value.update(f"{mode:o}".encode("ascii"))
            value.update(b"\0")
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    value.update(block)
            value.update(b"\0")

    return f"sha256:{value.hexdigest()}"
