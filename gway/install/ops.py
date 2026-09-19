"""Public install/uninstall operations."""

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
    """Converge one local project installation toward the requested state."""
    request = InstallRequest(
        source=str(source),
        ref=ref,
        upgrade=upgrade,
        force=force,
        stash=stash,
        system=system,
    )

    from .transaction import install_local

    return install_local(request)


def uninstall(project, *, system: bool = False):
    """Converge one managed project toward absence."""
    request = UninstallRequest(
        project=str(project),
        system=system,
    )

    from .transaction import uninstall_local

    return uninstall_local(request)
