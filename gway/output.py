"""Structured sidecar output for CLI invocations."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


class OutputWriteError(RuntimeError):
    """Raised when a requested structured output sidecar cannot be written."""


def write_json_atomic(path, value):
    """Serialize *value* as JSON and atomically replace *path*.

    The destination's parent directory must already exist. Serialization is
    intentionally strict: unsupported values fail rather than being stringified,
    because sidecar output is a machine contract rather than presentation text.
    """
    target = Path(path)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
    except (OSError, TypeError, ValueError) as exception:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise OutputWriteError(f"cannot write structured output to {target}: {exception}") from exception
