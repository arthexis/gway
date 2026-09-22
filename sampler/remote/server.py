"""Managed entrypoint for the shared G-Way remote OAuth/account service."""

from gway.remote.server import serve as _serve


def serve(
    host="127.0.0.1",
    port=8001,
    public_origin="https://remote.arthexis.com",
    resource_path="/mcp",
):
    """Serve the shared remote OAuth/account surface until supervised shutdown."""
    return _serve(
        host,
        int(port),
        public_origin=public_origin,
        resource_path=resource_path,
    )
