"""Managed project installation primitives."""

from .git import GitArtifact
from .model import Installation, InstallRequest, UninstallRequest
from .ops import install, uninstall
from .paths import InstallPaths, bin_root, data_root, install_paths, product_root
from .stash import Stash
from .state import InstallState

__all__ = [
    "GitArtifact",
    "Installation",
    "InstallPaths",
    "InstallRequest",
    "InstallState",
    "Stash",
    "UninstallRequest",
    "bin_root",
    "data_root",
    "install",
    "install_paths",
    "product_root",
    "uninstall",
]
