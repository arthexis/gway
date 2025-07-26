# file: gway/units.py
"""Utility functions for unit conversions."""

from __future__ import annotations


def yards_to_meters(value: float | str) -> float:
    """Convert yards to meters."""
    return float(value) * 0.9144


def meters_to_yards(value: float | str) -> float:
    """Convert meters to yards."""
    return float(value) / 0.9144
