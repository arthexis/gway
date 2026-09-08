from __future__ import annotations

from django.apps import apps
from sigils import SafeNamespace


def context(*, project, command_path):
    """Return protected fixture context after Django is ready."""
    assert apps.ready
    return {
        "THING": SafeNamespace(
            {
                "name": "demo",
                "project": project.name,
                "command": " ".join(command_path),
            }
        )
    }
