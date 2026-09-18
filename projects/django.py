# file: projects/django.py
"""Virtual project providing access to Django models via attribute lookup.

If ``DJANGO_SETTINGS_MODULE`` isn't set the project tries to import
``arthexis.settings`` or ``config.settings`` before initialising Django.
Models from the configured project can then be accessed as attributes from
``gw.django``.
"""

from __future__ import annotations

import importlib
import os

import django
from django.apps import apps


def _ensure_setup():
    """Initialize Django if it hasn't been configured yet."""
    if "DJANGO_SETTINGS_MODULE" not in os.environ:
        for candidate in ("arthexis.settings", "config.settings"):
            try:
                importlib.import_module(candidate)
            except Exception:
                continue
            os.environ["DJANGO_SETTINGS_MODULE"] = candidate
            break
    if not apps.ready:
        django.setup()


def list_models() -> list[str]:
    """Return a sorted list of model names from the current Django project."""
    _ensure_setup()
    return sorted(model.__name__ for model in apps.get_models())


def __getattr__(self, name: str):
    """Return a model class from the current Django project.

    Example
    -------
    ``gw.django.User`` → ``django.contrib.auth.models.User``
    """
    _ensure_setup()
    for model in apps.get_models():
        if model.__name__ == name:
            setattr(self, name, model)
            return model
    raise AttributeError(f"Model '{name}' not found")

