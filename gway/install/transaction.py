"""Transactional local project installation and removal."""

import os
from pathlib import Path
import shutil
import tempfile
import uuid

from .. import log as gway_log
from .activation import activate as activate_project, deactivate as deactivate_project
from .model import Installation, InstallRequest, UninstallRequest, validate_name
from .paths import install_paths
from .source import fingerprint, local_source, project_name
from .stash import preserve as preserve_stash
from .state import InstallState
from .systemd import UnitState, install_units, uninstall_units


def _is_within(path, parent):
    path = Path(path).resolve()
    parent = Path(parent).resolve()
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _copy_project(source, stage):
    shutil.copytree(
        source,
        stage,
        symlinks=True,
        dirs_exist_ok=True,
    )


def _remove_path(path):
    path = Path(path)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _expected_destination(existing, destination):
    if Path(existing.install_path).resolve() != destination.resolve():
        raise RuntimeError(
            "Installation state points outside the managed project location: "
            f"{existing.install_path}"
        )


def _managed_fingerprint(existing, destination):
    """Return the live managed fingerprint after validating its location."""
    _expected_destination(existing, destination)
    if not destination.exists() and not destination.is_symlink():
        return None
    if not destination.is_dir():
        raise RuntimeError(
            f"Managed installation is not a directory: {destination}"
        )
    return fingerprint(destination)


def _handle_drift(
    request,
    existing,
    destination,
    actual,
    desired_changed,
    stashes,
):
    """Validate or preserve/discard managed drift before reconciliation."""
    drifted = (
        actual is not None
        and (
            existing.fingerprint is None
            or actual != existing.fingerprint
        )
    )
    if not drifted:
        return None

    if not request.force and not request.stash:
        raise RuntimeError(
            f"Managed project {existing.name!r} has local modifications; "
            "use --stash to preserve them or --force to discard them"
        )

    if not request.upgrade and desired_changed:
        raise RuntimeError(
            f"Managed project {existing.name!r} has local modifications and "
            "the source has changed; --no-upgrade prevents using the changed "
            "source as a repair baseline"
        )

    if request.stash:
        snapshot = preserve_stash(
            existing,
            destination,
            actual,
            stashes,
        )
        gway_log.warning(
            "Preserved local modifications for %s at %s",
            existing.name,
            snapshot.path,
        )
        return snapshot

    gway_log.warning(
        "Discarding local modifications for %s because --force was requested",
        existing.name,
    )
    return None


def _stage_project(source, name, desired_fingerprint, projects):
    projects.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{name}.stage-",
            dir=projects,
        )
    )
    try:
        _copy_project(source, stage)

        staged_name = project_name(stage)
        if staged_name != name:
            raise RuntimeError(
                f"Project identity changed while staging: {name!r} -> {staged_name!r}"
            )

        staged_fingerprint = fingerprint(stage)
        if staged_fingerprint != desired_fingerprint:
            raise RuntimeError("Project source changed while installation was staging")
        return stage
    except Exception:
        if stage.exists():
            _remove_path(stage)
        raise


def _record_for(
    source_identity,
    name,
    fingerprint_value,
    destination,
    scope,
    *,
    requested_ref=None,
    resolved_revision=None,
    installed_at=None,
):
    return Installation(
        name=name,
        source=source_identity,
        requested_ref=requested_ref,
        resolved_revision=resolved_revision,
        fingerprint=fingerprint_value,
        install_path=destination,
        scope=scope,
        installed_at=installed_at,
    )


def _desired_changed(
    existing,
    *,
    source_identity,
    requested_ref,
    resolved_revision,
    fingerprint_value,
):
    return any(
        (
            existing.source != source_identity,
            existing.requested_ref != requested_ref,
            existing.resolved_revision != resolved_revision,
            existing.fingerprint != fingerprint_value,
        )
    )


def _unit_state_root(paths):
    return paths.root / "systemd"


def _selected_service_names(request, paths, project):
    if request.services:
        return tuple(request.services)
    return tuple(
        record.service
        for record in UnitState(_unit_state_root(paths)).get(project)
    )


def _service_definitions(root, project, names):
    names = tuple(names)
    if not names:
        return ()

    from ..service.manifest import load as load_services

    manifest = Path(root) / "gway.toml"
    catalog = load_services(manifest)
    if catalog.project != project:
        raise RuntimeError(
            f"Service manifest project mismatch: {catalog.project!r} != {project!r}"
        )
    available = {service.name: service for service in catalog.services}
    missing = [name for name in names if name not in available]
    if missing:
        raise ValueError(
            f"Unknown service(s) for {project!r}: {', '.join(missing)}"
        )
    return tuple(available[name] for name in names)


def _converge_services(request, paths, project, root):
    names = _selected_service_names(request, paths, project)
    if not names:
        return []
    services = _service_definitions(root, project, names)
    return install_units(
        project,
        services,
        state_root=_unit_state_root(paths),
        system=request.system,
        name=request.name,
    )


def _paths_and_state(request, *, paths=None, state=None):
    selected = install_paths(system=request.system) if paths is None else paths
    registry = InstallState(selected.state) if state is None else state
    return selected, registry


def install_materialized(
    request,
    source,
    *,
    source_identity,
    requested_ref=None,
    resolved_revision=None,
    paths=None,
    state=None,
):
    """Install/reconcile one already-materialized project tree."""
    if not isinstance(request, InstallRequest):
        raise TypeError("install_materialized requires an InstallRequest")

    selected, registry = _paths_and_state(
        request,
        paths=paths,
        state=state,
    )
    source = local_source(source)
    name = project_name(source)
    validate_name(name)
    desired_fingerprint = fingerprint(source)
    destination = selected.projects / name

    # Validate explicit or previously materialized service selections before
    # mutating the managed installation.
    selected_names = _selected_service_names(request, selected, name)
    _service_definitions(source, name, selected_names)

    if _is_within(selected.root, source):
        raise ValueError(
            "GWAY installation data cannot be stored inside the source project"
        )
    if source == destination.resolve() or _is_within(source, destination):
        raise ValueError("Cannot install a project from its managed destination")

    existing = registry.get(name, scope=selected.scope)
    drifted = False
    desired_changed = True
    if existing is None:
        if destination.exists() or destination.is_symlink():
            raise RuntimeError(
                f"Managed destination exists without installation state: {destination}"
            )
    else:
        desired_changed = _desired_changed(
            existing,
            source_identity=source_identity,
            requested_ref=requested_ref,
            resolved_revision=resolved_revision,
            fingerprint_value=desired_fingerprint,
        )
        actual = _managed_fingerprint(existing, destination)
        drifted = (
            actual is not None
            and (
                existing.fingerprint is None
                or actual != existing.fingerprint
            )
        )
        _handle_drift(
            request,
            existing,
            destination,
            actual,
            desired_changed,
            selected.stashes,
        )

        same = (
            not drifted
            and not desired_changed
            and destination.is_dir()
        )
        if same:
            launcher = activate_project(name, destination, selected)
            try:
                _converge_services(request, selected, name, destination)
            except Exception:
                launcher.rollback()
                raise
            launcher.commit()
            return existing

        if (
            not drifted
            and destination.is_dir()
            and existing.fingerprint == desired_fingerprint
        ):
            if not request.upgrade:
                return existing
            record = _record_for(
                source_identity,
                name,
                desired_fingerprint,
                destination,
                selected.scope,
                requested_ref=requested_ref,
                resolved_revision=resolved_revision,
                installed_at=existing.installed_at,
            )
            launcher = activate_project(name, destination, selected)
            try:
                stored = registry.put(record)
            except Exception:
                launcher.rollback()
                raise
            try:
                _converge_services(request, selected, name, destination)
            except Exception:
                registry.put(existing)
                launcher.rollback()
                raise
            launcher.commit()
            return stored

        if not request.upgrade:
            if not destination.is_dir() and desired_changed:
                raise RuntimeError(
                    f"Managed project {name!r} is missing and desired state changed; "
                    "repair would require an upgrade"
                )
            if destination.is_dir() and not drifted:
                return existing

    stage = _stage_project(
        source,
        name,
        desired_fingerprint,
        selected.projects,
    )
    backup = None
    activated = False
    try:
        if destination.exists() or destination.is_symlink():
            backup = selected.projects / (
                f".{name}.replace-{uuid.uuid4().hex}"
            )
            os.replace(destination, backup)

        os.replace(stage, destination)
        activated = True

        record = _record_for(
            source_identity,
            name,
            desired_fingerprint,
            destination,
            selected.scope,
            requested_ref=requested_ref,
            resolved_revision=resolved_revision,
        )
        launcher = None
        try:
            launcher = activate_project(name, destination, selected)
            stored = registry.put(record)
            _converge_services(request, selected, name, destination)
        except Exception:
            if existing is None:
                registry.remove(name, scope=selected.scope)
            else:
                registry.put(existing)
            if launcher is not None:
                launcher.rollback()
            if destination.exists() or destination.is_symlink():
                _remove_path(destination)
            if backup is not None and (
                backup.exists() or backup.is_symlink()
            ):
                os.replace(backup, destination)
            activated = False
            raise

        launcher.commit()
        if backup is not None and (
            backup.exists() or backup.is_symlink()
        ):
            try:
                _remove_path(backup)
            except OSError:
                pass
        return stored
    except Exception:
        if not activated and stage.exists():
            _remove_path(stage)
        raise
    finally:
        if stage.exists():
            _remove_path(stage)


def install_local(request, *, paths=None, state=None):
    """Install or reconcile one local project through atomic activation."""
    if not isinstance(request, InstallRequest):
        raise TypeError("install_local requires an InstallRequest")
    if request.ref is not None:
        raise ValueError("--ref is not supported for local install sources")

    source = local_source(request.source)
    return install_materialized(
        request,
        source,
        source_identity=str(source),
        paths=paths,
        state=state,
    )


def uninstall_local(request, *, paths=None, state=None):
    """Remove one managed installation and its owned launchers transactionally."""
    if not isinstance(request, UninstallRequest):
        raise TypeError("uninstall_local requires an UninstallRequest")

    validate_name(request.project)
    selected, registry = _paths_and_state(
        request,
        paths=paths,
        state=state,
    )
    existing = registry.get(request.project, scope=selected.scope)
    if existing is None:
        return None

    uninstall_units(
        request.project,
        state_root=_unit_state_root(selected),
    )

    destination = selected.projects / request.project
    _expected_destination(existing, destination)

    tombstone = None
    if destination.exists() or destination.is_symlink():
        selected.projects.mkdir(parents=True, exist_ok=True)
        tombstone = selected.projects / (
            f".{request.project}.remove-{uuid.uuid4().hex}"
        )
        os.replace(destination, tombstone)

    launcher = None
    try:
        launcher = deactivate_project(request.project, selected)
        removed = registry.remove(request.project, scope=selected.scope)
        if not removed:
            raise RuntimeError(
                f"Installation state disappeared while removing {request.project!r}"
            )
    except Exception:
        if launcher is not None:
            launcher.rollback()
        if tombstone is not None and (
            tombstone.exists() or tombstone.is_symlink()
        ):
            os.replace(tombstone, destination)
        raise

    launcher.commit()
    if tombstone is not None and (
        tombstone.exists() or tombstone.is_symlink()
    ):
        _remove_path(tombstone)
    return existing

