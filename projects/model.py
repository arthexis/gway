# file: projects/model.py
"""Virtual project exposing Django models from the Arthexis application.

This project lazily loads Django and makes all registered models available
as attributes. Model names may be referenced using their original CamelCase
form or via CLI friendly variants like ``energy-account``. Any model method
can then be called directly from the CLI. If ``DJANGO_SETTINGS_MODULE`` is
unset the project attempts to import ``arthexis.settings`` or
``config.settings`` before falling back to an existing environment
variable.

Example
=======

``gway model energy-account generate-report --params``

Aliases ``mod`` and ``%`` are available for convenience.
"""

from __future__ import annotations

import importlib
import os
import warnings
from typing import Dict, List

try:  # pragma: no cover - optional dependency
    import django
    from django.apps import apps
except Exception:  # pragma: no cover - runtime error if accessed
    django = None
    apps = None


_MODEL_MAP: Dict[str, type] | None = None


def _ensure_setup() -> None:
    """Configure Django once and build the model map."""
    global _MODEL_MAP

    if django is None:  # pragma: no cover - handled at runtime
        raise RuntimeError("Django is required for the 'model' project")

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

    if _MODEL_MAP is None:
        models_map: Dict[str, type] = {}
        for model in apps.get_models():
            name = model.__name__
            if name in models_map:
                warnings.warn(
                    f"Duplicate model name '{name}' encountered; using first occurrence",
                    RuntimeWarning,
                )
                continue
            models_map[name] = model
        _MODEL_MAP = models_map


def list_models() -> List[str]:
    """Return a sorted list of model names from the current Django project."""
    _ensure_setup()
    return sorted(_MODEL_MAP or [])


def _camelize(name: str) -> str:
    parts = name.replace("-", "_").split("_")
    return "".join(part.capitalize() for part in parts if part)


def __getattr__(self, name: str):
    """Return a model class matching ``name``.

    ``name`` may be provided in kebab/underscore/camel case forms.
    """
    _ensure_setup()
    target = _camelize(name)
    if _MODEL_MAP and target in _MODEL_MAP:
        model = _MODEL_MAP[target]
        setattr(self, name, model)
        setattr(self, model.__name__, model)
        return model
    raise AttributeError(f"Model '{name}' not found")
