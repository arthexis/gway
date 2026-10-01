"""Structured command results that also carry a process exit status."""

from __future__ import annotations

from contextvars import ContextVar


_exit_code = ContextVar("gway_exit_code", default=0)


def reset_exit_code():
    """Reset structured-result process status for one CLI invocation."""
    _exit_code.set(0)


def current_exit_code():
    """Return the process status requested by the current structured result."""
    return int(_exit_code.get())


class ExitResult(dict):
    """A structured result with an explicit CLI process exit status.

    The mapping itself is the canonical public result. ``exit_code`` is execution
    metadata consumed by the CLI boundary and is intentionally not serialized as
    an extra envelope field.
    """

    def __init__(self, *args, exit_code=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.exit_code = int(exit_code)
        _exit_code.set(self.exit_code)
