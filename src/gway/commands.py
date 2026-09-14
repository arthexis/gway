from __future__ import annotations

RUNTIME_COMMAND_NAMES = frozenset(
    {"install", "log", "recipe", "reload", "result", "store", "uninstall", "upgrade"}
)
CORE_OPERATION_NAMES = frozenset({"install", "log", "uninstall", "upgrade"})

__all__ = ["CORE_OPERATION_NAMES", "RUNTIME_COMMAND_NAMES"]
