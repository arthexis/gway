"""Service-install backend selection."""

from . import systemd


_BACKENDS = {
    "systemd": systemd,
}


def names():
    """Return supported service-install backend names."""
    return tuple(sorted(_BACKENDS))


def get(name):
    """Return one supported service-install backend module."""
    try:
        return _BACKENDS[name]
    except KeyError as exc:
        supported = ", ".join(names())
        raise ValueError(
            f"Unsupported service backend {name!r}; supported: {supported}"
        ) from exc
