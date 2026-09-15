from __future__ import annotations

from collections.abc import Sequence

from . import runtime_base as _base
from .event_command import run_event

# Keep the established runtime implementation intact and extend only its core
# operation registry. This isolates the event addition from unrelated routing
# and upgrade behavior.
_base._CORE_OPERATIONS = frozenset((*_base._CORE_OPERATIONS, "event"))


class GwayRuntime(_base.GwayRuntime):
    """Gway runtime with the core event operation enabled."""

    def _run_core(self, tokens: Sequence[str]) -> object:
        if tokens[0] == "event":
            return run_event(tokens[1:])
        return super()._run_core(tokens)


def __getattr__(name: str) -> object:
    return getattr(_base, name)


__all__ = ["GwayRuntime"]
