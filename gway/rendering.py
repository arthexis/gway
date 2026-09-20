"""Sigil-aware text rendering with optional rollback journaling."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

from .journal_fs import capture_path


def _resolved_path(runtime, value) -> Path:
    return Path(str(runtime.resolve(str(value)))).expanduser()


def _destination(runtime, template: Path, to) -> Path:
    destination = _resolved_path(runtime, to)
    if destination.is_dir():
        return destination / template.name
    return destination


def _write_atomic(destination: Path, content: str) -> Path:
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.gway-",
        dir=destination.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists() and not destination.is_symlink():
            temporary.chmod(destination.stat().st_mode & 0o7777)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


class Renderer:
    """Runtime-bound render operation for integration rebuild."""

    def __init__(self, runtime):
        self.runtime = runtime

    def render(self, template, to, rollback=None):
        """Render a sigil-aware text template to an atomic destination.

        Args:
            template: Template file path.
            to: Destination file or existing directory.
            rollback: Optional rollback journal name to capture destination state.
        """
        source = _resolved_path(self.runtime, template)
        if not source.is_file():
            raise FileNotFoundError(source)

        destination = _destination(self.runtime, source, to)
        content = source.read_text(encoding="utf-8")
        rendered = self.runtime.resolve(content)
        if not isinstance(rendered, str):
            rendered = str(rendered)

        entry = None
        if rollback is not None:
            entry = self.runtime.journal.prepare(
                rollback,
                kind="filesystem",
                data={
                    "operation": "render",
                    "path": str(destination),
                },
            )
            storage = self.runtime.journal.entry_storage(
                rollback,
                entry.sequence,
            )
            snapshot = capture_path(destination, storage)
            self.runtime.journal.update_entry_data(
                rollback,
                entry.sequence,
                {
                    "operation": "render",
                    "paths": [snapshot],
                },
            )

        result = _write_atomic(destination, rendered)

        if entry is not None:
            self.runtime.journal.mark_applied(rollback, entry.sequence)

        return result
