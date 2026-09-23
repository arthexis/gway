"""Built-in service policy for the shared remote OAuth/account server."""

from pathlib import Path

from ..service.model import Service


def definition(launchable, *, state_root):
    """Return service policy for the normal remote-access server launchable."""
    project_root = Path(__file__).resolve().parents[2]
    return Service(
        project="gway",
        name="remote-auth",
        root=project_root,
        launchable=launchable,
        description="Gway remote OAuth and account service",
        working_directory="{project}",
        state_root=Path(state_root),
    )


def register(runtime):
    """Expose remote.serve and attach its stable service identity."""
    from .server import serve

    runtime.wrap(
        "remote.serve",
        serve,
        op="serve",
        sub="remote",
    )
    launchable = runtime.launchables["remote.serve"]
    service = definition(
        launchable,
        state_root=runtime.data_root() / "services",
    )
    runtime._service_presets[service.identity] = service
    return service
