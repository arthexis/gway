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
    """Expose remote operations and attach the server's stable service identity."""
    from .acceptance import accept
    from .server import serve

    def serve_remote(
        host="127.0.0.1",
        port=8001,
        *,
        public_origin="https://remote.arthexis.com",
        resource_path="/mcp",
    ):
        return serve(
            host,
            port,
            public_origin=public_origin,
            resource_path=resource_path,
            runtime=runtime,
        )

    runtime.wrap(
        "remote.accept",
        lambda resource, protocol=None: accept(
            runtime,
            resource,
            protocol=protocol,
        ),
        op="accept",
        sub="remote",
    )
    runtime.wrap(
        "remote.serve",
        serve_remote,
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
