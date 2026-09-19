"""Managed project installation primitives."""

from .model import Installation, InstallRequest, UninstallRequest
from .ops import install, uninstall
from .paths import InstallPaths, data_root, install_paths
from .stash import Stash
from .state import InstallState

__all__ = [
    "Installation",
    "InstallPaths",
    "InstallRequest",
    "InstallState",
    "Stash",
    "UninstallRequest",
    "data_root",
    "install",
    "install_paths",
    "uninstall",
]
