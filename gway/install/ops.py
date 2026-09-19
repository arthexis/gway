"""Public install/uninstall operations."""

from pathlib import Path

from .model import InstallRequest, UninstallRequest


def _local_intent(source):
    if isinstance(source, Path):
        return True
    try:
        return Path(str(source)).expanduser().exists()
    except OSError:
        return False


def install(
    source: str | Path,
    *,
    ref: str | None = None,
    upgrade: bool = True,
    force: bool = False,
    stash: bool = False,
    system: bool = False,
):
    """Converge one local or Git project installation toward requested state."""
    request = InstallRequest(
        source=str(source),
        ref=ref,
        upgrade=upgrade,
        force=force,
        stash=stash,
        system=system,
    )

    from .transaction import install_local, install_materialized

    if _local_intent(source):
        return install_local(request)

    from .git import is_git_source, materialize

    if is_git_source(request.source):
        artifact = materialize(
            request.source,
            ref=request.ref,
        )
        return install_materialized(
            request,
            artifact.path,
            source_identity=artifact.source,
            requested_ref=artifact.requested_ref,
            resolved_revision=artifact.resolved_revision,
        )

    return install_local(request)


def uninstall(project, *, system: bool = False):
    """Converge one managed project toward absence."""
    request = UninstallRequest(
        project=str(project),
        system=system,
    )

    from .transaction import uninstall_local

    return uninstall_local(request)
