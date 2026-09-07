"""Public Python API for GWAY.

The facade is intentionally small. Managed project resolution and command dispatch
will be connected as the registry/adapter chunks are implemented.
"""

from __future__ import annotations


class Gway:
    """Stable Python facade for managed GWAY projects.

    Future managed command access will mirror the CLI namespace, for example::

        from gway import gway as gw
        gw.wireguard.status()
        gw.arthexis.check()

    The facade will delegate through the same registry, adapter, dispatcher, and
    runner used by the CLI so managed project environments remain isolated.
    """

    def __getattr__(self, name: str):
        raise AttributeError(
            f"managed project access is not implemented yet: {name!r}; "
            "see PLAN.md implementation chunks 1-3"
        )


gway = Gway()
# Compatibility alias for older code that imported ``gw`` directly.
gw = gway

__all__ = ["Gway", "gway", "gw"]
