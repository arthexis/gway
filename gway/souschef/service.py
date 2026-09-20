"""Built-in service policy for the Sous Chef package entrypoint."""

from pathlib import Path

from ..install.paths import data_root
from ..service.model import Service


def definition(launchable):
    """Return service policy for the normal Sous Chef launchable."""
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
    """Attach service lifecycle policy to the Sous Chef package entrypoint."""
    from . import __main__

    runtime.wrap(
        "sous.chef",
        __main__,
        op="chef",
        sub="sous",
    )
    launchable = runtime.launchables["sous.chef"]
    service = definition(launchable)
    runtime._service_presets[service.identity] = service
    return service
