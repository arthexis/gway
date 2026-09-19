"""Public GWAY core interface."""

from .cache import Cache
from .gateway import Gateway, gw
from .install import Installation, InstallRequest, InstallState, Stash, UninstallRequest
from .operations import Operations, Subjects
from .console import cli_main, process
from .recipes import load_recipe
from .sigil import Sigil, Resolver, Spool, __
from .structs import Results

__all__ = [
    "Cache",
    "Gateway",
    "Installation",
    "InstallRequest",
    "InstallState",
    "Stash",
    "Operations",
    "Subjects",
    "Resolver",
    "Results",
    "Sigil",
    "Spool",
    "UninstallRequest",
    "__",
    "cli_main",
    "gw",
    "load_recipe",
    "process",
]
