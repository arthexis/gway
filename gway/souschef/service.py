"""Built-in service declaration for Sous Chef."""

from pathlib import Path

from ..install.paths import data_root
from ..launchable import Launchable
from ..service.model import Service


def definition():
    """Return the built-in gway/sous-chef service definition."""
    project_root = Path(__file__).resolve().parents[2]
    launchable = Launchable.command_target(
        "sous-chef",
        ("{python}", "-m", "gway.souschef.daemon"),
        root=project_root,
        metadata={"builtin": "sous-chef"},
    )
    return Service(
        project="gway",
        name="sous-chef",
        root=project_root,
        launchable=launchable,
        description="Gway single-worker recipe scheduler",
        working_directory="{project}",
        restart="on-failure",
        restart_sec=5.0,
        state_root=data_root() / "services",
    )


def register(runtime):
    """Register the built-in Sous Chef service on one Gateway."""
    service = definition()
    runtime._services[service.identity] = service
    return service
