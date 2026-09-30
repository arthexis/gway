"""Public GWAY core interface."""

from . import githubops as _githubops
from .githubcheck import Controller as _GitHubController

_githubops.Controller = _GitHubController

from .cache import Cache
from .gateway import Gateway, gw
from .install import Installation, InstallRequest, InstallState, Stash, UninstallRequest
from .launchable import Launchable, Launchables
from .operations import Operations, Subjects
from .mutation import MutationError
from .console import cli_main as _console_cli_main, process
from .outcome import current_exit_code, reset_exit_code
from .recipe import load_recipe
from .sigil import Sigil, Resolver, Spool, __
from .structs import Results


def cli_main():
    """Run the CLI and honor structured results that request a non-zero status."""
    reset_exit_code()
    status = _console_cli_main()
    if status:
        return status
    return current_exit_code()


__all__ = [
    "Cache",
    "Gateway",
    "Installation",
    "InstallRequest",
    "InstallState",
    "Launchable",
    "Launchables",
    "MutationError",
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
