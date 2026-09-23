"""Generic remote acceptance dispatch."""

from urllib.parse import urlsplit


def _protocol(resource, explicit=None):
    if explicit is not None:
        value = str(explicit).strip().casefold()
        if not value:
            raise ValueError("protocol must be non-empty when provided")
        return value

    path = urlsplit(str(resource)).path.rstrip("/")
    inferred = path.rsplit("/", 1)[-1].casefold() if path else ""
    return inferred or "mcp"


def accept(runtime, resource, *, protocol=None):
    """Run the maintained acceptance flow for one remote protocol resource.

    Args:
        resource: Public remote resource URL.
        protocol: Optional protocol name. When omitted, infer it semantically
            from the resource path and default to MCP for an origin/root URL.
    """
    resource = str(resource).strip()
    if not resource:
        raise ValueError("remote resource URL is required")
    selected = _protocol(resource, protocol)
    return runtime._run_sampler_recipe(
        f"{selected}/accept",
        resource=resource,
        protocol=selected,
    )
