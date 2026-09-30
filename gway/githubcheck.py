"""Compatibility import for the sampler-owned GitHub CI checks."""

from .sampler import load

Controller = load("github").Controller

__all__ = ["Controller"]
