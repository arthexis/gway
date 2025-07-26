# file: gway/units.py
"""Utility functions for unit conversions."""

from __future__ import annotations


def yards_to_meters(value: float | str) -> float:
    """Convert yards to meters."""
    return float(value) * 0.9144


def meters_to_yards(value: float | str) -> float:
    """Convert meters to yards."""
    return float(value) / 0.9144


def seconds_to_interval(value: float | str) -> float:
    """Identity conversion for interval seconds."""
    return float(value)


def minutes_to_interval(value: float | str) -> float:
    """Convert minutes to seconds for interval parameters."""
    return float(value) * 60


def hours_to_interval(value: float | str) -> float:
    """Convert hours to seconds for interval parameters."""
    return float(value) * 3600


def days_to_interval(value: float | str) -> float:
    """Convert days to seconds for interval parameters."""
    return float(value) * 86400
