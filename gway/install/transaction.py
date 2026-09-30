"""Transactional local project installation and removal."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

from .. import log as gway_log
from .activation import activate as activate_project, deactivate as deactivate_project
from .model import Installation, InstallRequest, UninstallRequest, validate_name
from .paths import install_paths
from .source import fingerprint, local_source, project_name
from .stash import preserve as preserve_stash
from .state import InstallState


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
        raise RuntimeError(f"Managed installation is not a directory: {destination}")
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
    drifted = actual is not None and (
        existing.fingerprint is None or actual != existing.fingerprint
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


def _product_python(project):
    """Return the interpreter path inside a product-owned virtual environment."""
    project = Path(project)
    return project / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )


def _product_runtime_ready(project, selected):
    """Return whether a product runtime has an interpreter and consistent packages."""
    from ..recipe.uv import ensure_uv

    python = _product_python(project)
    if not python.is_file():
        return False

    uv = ensure_uv(
        system=selected.scope == "system",
        root=selected.root,
    )
    result = subprocess.run(
        [str(uv), "pip", "check", "--python", str(python)],
        cwd=project,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _provision_product_runtime(project, selected):
    """Create an isolated runtime and install one product with its dependencies."""
    from ..recipe.uv import ensure_uv

    uv = ensure_uv(
        system=selected.scope == "system",
        root=selected.root,
    )
    project = Path(project)
    subprocess.run(
        [str(uv), "venv", ".venv"],
        cwd=project,
        check=True,
    )
    python = _product_python(project)
    if not python.is_file():
        raise RuntimeError(
            f"uv completed without creating product interpreter: {python}"
        )
    subprocess.run(
        [str(uv), "pip", "install", "--python", str(python), "."],
        cwd=project,
        check=True,
    )


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
    kind="extension",
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
        kind=kind,
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


def _paths_and_state(request, *, paths=None, state=None):
    selected = install_paths(system=request.system) if paths is None else paths
    registry = InstallState(selected.state) if state is None else state
    return selected, registry



def _add_recovery_note(primary, label, error):
    """Attach recovery diagnostics without replacing the forward failure."""
    note = f"Install recovery failure during {label}: {error}"
    add_note = getattr(primary, "add_note", None)
    if add_note is not None:
        add_note(note)
        return
    notes = list(getattr(primary, "__notes__", ()))
    notes.append(note)
    primary.__notes__ = notes


def _attempt_recovery(primary, label, action):
    """Attempt one recovery step independently and retain any failure as context."""
    try:
        action()
    except Exception as error:
        _add_recovery_note(primary, label, error)
        return False
    return True


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
    destination_root = selected.products if request.kind == "product" else selected.projects
    destination = destination_root / name

    if _is_within(selected.root, source):
        raise ValueError(
            "GWAY installation data cannot be stored inside the source project"
        )
    if source == destination.resolve() or _is_within(source, destination):
        raise ValueError("Cannot install a project from its managed destination")

    existing = registry.get(name, scope=selected.scope)
    previous_destination = None
    kind_changed = False
    drifted = False
    desired_changed = True
    if existing is None:
        if destination.exists() or destination.is_symlink():
            raise RuntimeError(
                f"Managed destination exists without installation state: {destination}"
            )
    else:
        previous_root = (
            selected.products if existing.kind == "product" else selected.projects
        )
        previous_destination = previous_root / name
        _expected_destination(existing, previous_destination)
        kind_changed = existing.kind != request.kind
        desired_changed = kind_changed or _desired_changed(
            existing,
            source_identity=source_identity,
            requested_ref=requested_ref,
            resolved_revision=resolved_revision,
            fingerprint_value=desired_fingerprint,
        )
        actual = _managed_fingerprint(existing, previous_destination)
        drifted = actual is not None and (
            existing.fingerprint is None or actual != existing.fingerprint
        )
        _handle_drift(
            request,
            existing,
            previous_destination,
            actual,
            desired_changed,
            selected.stashes,
        )
        if (
            kind_changed
            and (destination.exists() or destination.is_symlink())
            and destination.resolve() != previous_destination.resolve()
        ):
            if not request.force:
                raise RuntimeError(
                    f"New {request.kind} destination already exists: {destination}"
                )
            if destination.is_symlink() or not destination.is_dir():
                raise RuntimeError(
                    f"Cannot force {request.kind} migration over non-directory "
                    f"destination: {destination}"
                )
            try:
                destination_name = project_name(destination)
            except (OSError, ValueError) as error:
                raise RuntimeError(
                    f"Cannot verify existing {request.kind} destination: {destination}"
                ) from error
            if destination_name != name:
                raise RuntimeError(
                    f"Cannot force {request.kind} migration over destination for "
                    f"different project {destination_name!r}: {destination}"
                )

        runtime_ready = (
            request.kind != "product"
            or _product_runtime_ready(destination, selected)
        )
        same = (
            not kind_changed
            and not drifted
            and not desired_changed
            and destination.is_dir()
            and runtime_ready
        )
        if same:
            if request.kind == "extension":
                launcher = activate_project(name, destination, selected)
                launcher.commit()
            return existing

        if (
            not kind_changed
            and not drifted
            and destination.is_dir()
            and existing.fingerprint == desired_fingerprint
            and runtime_ready
        ):
            if not request.upgrade:
                return existing
            record = _record_for(
                source_identity,
                name,
                desired_fingerprint,
                destination,
                selected.scope,
                kind=request.kind,
                requested_ref=requested_ref,
                resolved_revision=resolved_revision,
                installed_at=existing.installed_at,
            )
            launcher = (
                activate_project(name, destination, selected)
                if request.kind == "extension"
                else None
            )
            try:
                stored = registry.put(record)
            except Exception as primary:
                if launcher is not None:
                    _attempt_recovery(primary, "launcher rollback", launcher.rollback)
                raise
            if launcher is not None:
                launcher.commit()
            return stored

        if not request.upgrade:
            if not destination.is_dir() and desired_changed:
                raise RuntimeError(
                    f"Managed project {name!r} is missing and desired state changed; "
                    "repair would require an upgrade"
                )
            if destination.is_dir() and not drifted and runtime_ready:
                return existing

    stage = _stage_project(
        source,
        name,
        desired_fingerprint,
        destination_root,
    )
    backup = None
    activated = False
    try:
        if destination.exists() or destination.is_symlink():
            backup = destination_root / (f".{name}.replace-{uuid.uuid4().hex}")
            os.replace(destination, backup)

        os.replace(stage, destination)
        activated = True

        if request.kind == "product":
            try:
                _provision_product_runtime(destination, selected)
            except Exception as primary:
                if destination.exists() or destination.is_symlink():
                    _attempt_recovery(
                        primary,
                        "failed product removal",
                        lambda: _remove_path(destination),
                    )
                if backup is not None and (backup.exists() or backup.is_symlink()):
                    _attempt_recovery(
                        primary,
                        "previous product restoration",
                        lambda: os.replace(backup, destination),
                    )
                activated = False
                raise

        record = _record_for(
            source_identity,
            name,
            desired_fingerprint,
            destination,
            selected.scope,
            kind=request.kind,
            requested_ref=requested_ref,
            resolved_revision=resolved_revision,
        )
        launcher = None
        previous_launcher = None
        state_written = False
        try:
            if kind_changed and existing.kind == "extension":
                previous_launcher = deactivate_project(name, selected)
            launcher = (
                activate_project(name, destination, selected)
                if request.kind == "extension"
                else None
            )
            stored = registry.put(record)
            state_written = True
        except Exception as primary:
            if state_written:
                if existing is None:
                    _attempt_recovery(
                        primary,
                        "installation state removal",
                        lambda: registry.remove(name, scope=selected.scope),
                    )
                else:
                    _attempt_recovery(
                        primary,
                        "installation state restoration",
                        lambda: registry.put(existing),
                    )

            if launcher is not None:
                _attempt_recovery(primary, "launcher rollback", launcher.rollback)
            if previous_launcher is not None:
                _attempt_recovery(
                    primary,
                    "previous launcher restoration",
                    previous_launcher.rollback,
                )

            if destination.exists() or destination.is_symlink():
                _attempt_recovery(
                    primary,
                    "replacement project removal",
                    lambda: _remove_path(destination),
                )

            if backup is not None and (backup.exists() or backup.is_symlink()):
                _attempt_recovery(
                    primary,
                    "previous project restoration",
                    lambda: os.replace(backup, destination),
                )

            activated = False
            raise

        if launcher is not None:
            launcher.commit()
        if previous_launcher is not None:
            previous_launcher.commit()
        if (
            kind_changed
            and previous_destination is not None
            and previous_destination != destination
            and (previous_destination.exists() or previous_destination.is_symlink())
        ):
            try:
                _remove_path(previous_destination)
            except OSError:
                gway_log.warning(
                    "Installed %s as %s but could not remove previous %s path %s",
                    name,
                    request.kind,
                    existing.kind,
                    previous_destination,
                )
        if backup is not None and (backup.exists() or backup.is_symlink()):
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

    destination_root = (
        selected.products if existing.kind == "product" else selected.projects
    )
    destination = destination_root / request.project

    _expected_destination(existing, destination)

    tombstone = None
    if destination.exists() or destination.is_symlink():
        destination_root.mkdir(parents=True, exist_ok=True)
        tombstone = destination_root / (
            f".{request.project}.remove-{uuid.uuid4().hex}"
        )
        os.replace(destination, tombstone)

    launcher = None
    try:
        launcher = (
            deactivate_project(request.project, selected)
            if existing.kind == "extension"
            else None
        )
        removed = registry.remove(request.project, scope=selected.scope)
        if not removed:
            raise RuntimeError(
                f"Installation state disappeared while removing {request.project!r}"
            )
    except Exception:
        if launcher is not None:
            launcher.rollback()
        if tombstone is not None and (tombstone.exists() or tombstone.is_symlink()):
            os.replace(tombstone, destination)
        raise

    if launcher is not None:
        launcher.commit()
    if tombstone is not None and (tombstone.exists() or tombstone.is_symlink()):
        _remove_path(tombstone)
    return existing
