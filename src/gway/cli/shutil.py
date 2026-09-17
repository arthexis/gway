"""Compatibility surface for legacy ``gway.cli.shutil`` monkeypatches."""

from shutil import get_terminal_size

__all__ = ["get_terminal_size"]
