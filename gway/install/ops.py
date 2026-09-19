"""Public install/uninstall operation contracts."""

from pathlib import Path

from .model import InstallRequest, UninstallRequest


def install(
    source: str | Path,
    *,
    ref: str | None = None,
    upgrade: bool = True,
    force: bool = False,
    stash: bool = False,
    system: bool = False,
):
    """Describe a convergent project installation request."""
    return InstallRequest(
        source=str(source),
        ref=ref,
        upgrade=upgrade,
        force=force,
        stash=stash,
        system=system,
    )


def uninstall(project, *, system: bool = False):
    """Describe an idempotent project removal request."""
    return UninstallRequest(
        project=str(project),
        system=system,
    )
