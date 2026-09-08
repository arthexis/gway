"""GWAY project manager and command dispatcher."""

from .api import Gway, gw, gway
from .sigils import gway_context

__all__ = ["Gway", "gway", "gw", "gway_context", "__version__"]

__version__ = "1.0.1"
