"""Built-in service policy for the Sous Chef daemon operation."""

from pathlib import Path

from ..install.paths import data_root
from ..service.model import Service


def definition(launchable):
    """Return service policy for the normal Sous Chef daemon launchable."""
    project_root = Path(__file__).resolve().parents[2]
    return Service(
        project="gway",
        name="sous-chef",
        root=project_root,
        launchable=launchable,
        description="Gway single-worker recipe scheduler",
        working_directory="{project}",
        state_root=data_root() / "services",
    )


def register(runtime):
    """Attach service lifecycle policy to the Sous Chef daemon operation."""
    from . import daemon

    runtime.wrap(
        "sous.chef.daemon",
        daemon.run,
        op="daemon",
        sub="chef",
    )
    launchable = runtime.launchables["sous.chef.daemon"]
    service = definition(launchable)
    runtime._services[service.identity] = service
    return service
