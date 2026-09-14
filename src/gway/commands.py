from __future__ import annotations

RUNTIME_COMMAND_NAMES = frozenset(
    {"install", "log", "recipe", "reload", "result", "store", "uninstall", "upgrade"}
)
CORE_OPERATION_NAMES = frozenset({"install", "log", "uninstall", "upgrade"})
CLI_COMMAND_NAMES = frozenset(
    {"list", "info", "path", "solve", "register", "service", "shell"}
)
TOP_LEVEL_COMMAND_NAMES = RUNTIME_COMMAND_NAMES | CLI_COMMAND_NAMES

__all__ = [
    "CLI_COMMAND_NAMES",
    "CORE_OPERATION_NAMES",
    "RUNTIME_COMMAND_NAMES",
    "TOP_LEVEL_COMMAND_NAMES",
]
