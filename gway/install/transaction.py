"""Transactional local project installation and removal."""

import os
from pathlib import Path
import shutil
import tempfile
import uuid

from .model import Installation, InstallRequest, UninstallRequest, validate_name
from .paths import install_paths
from .source import fingerprint, local_source, project_name
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


def _paths_and_state(request, *, paths=None, state=None):
    selected = install_paths(system=request.system) if paths is None else paths
    registry = InstallState(selected.state) if state is None else state
    return selected, registry


def install_local(request, *, paths=None, state=None):
    """Install one local project through staging and atomic activation."""
    if not isinstance(request, InstallRequest):
        raise TypeError("install_local requires an InstallRequest")
    if request.ref is not None:
        raise ValueError("--ref is not supported for local install sources")

    selected, registry = _paths_and_state(
        request,
        paths=paths,
        state=state,
    )
    source = local_source(request.source)
    name = project_name(source)
    validate_name(name)
    desired_fingerprint = fingerprint(source)
    destination = selected.projects / name

    if _is_within(selected.root, source):
        raise ValueError(
            "GWAY installation data cannot be stored inside the source project"
        )
    if source == destination.resolve() or _is_within(source, destination):
        raise ValueError("Cannot install a project from its managed destination")

    existing = registry.get(name, scope=selected.scope)
    if existing is not None:
        same = (
            Path(existing.install_path).resolve() == destination.resolve()
            and existing.source == str(source)
            and existing.fingerprint == desired_fingerprint
            and destination.is_dir()
        )
        if same:
            return existing
        if not request.upgrade:
            return existing
        raise RuntimeError(
            f"Project {name!r} is already installed with different state; "
            "replacement reconciliation is not implemented yet"
        )

    if destination.exists() or destination.is_symlink():
        raise RuntimeError(
            f"Managed destination exists without installation state: {destination}"
        )

    selected.projects.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{name}.stage-",
            dir=selected.projects,
        )
    )

    activated = False
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

        os.replace(stage, destination)
        activated = True

        record = Installation(
            name=name,
            source=str(source),
            requested_ref=None,
            resolved_revision=None,
            fingerprint=desired_fingerprint,
            install_path=destination,
            scope=selected.scope,
        )
        try:
            return registry.put(record)
        except Exception:
            _remove_path(destination)
            activated = False
            raise
    finally:
        if not activated and stage.exists():
            _remove_path(stage)


def uninstall_local(request, *, paths=None, state=None):
    """Remove one managed local installation transactionally and idempotently."""
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

    destination = selected.projects / request.project
    if Path(existing.install_path).resolve() != destination.resolve():
        raise RuntimeError(
            "Installation state points outside the managed project location: "
            f"{existing.install_path}"
        )

    if not destination.exists() and not destination.is_symlink():
        registry.remove(request.project, scope=selected.scope)
        return existing

    selected.projects.mkdir(parents=True, exist_ok=True)
    tombstone = selected.projects / (
        f".{request.project}.remove-{uuid.uuid4().hex}"
    )
    os.replace(destination, tombstone)

    try:
        removed = registry.remove(request.project, scope=selected.scope)
        if not removed:
            raise RuntimeError(
                f"Installation state disappeared while removing {request.project!r}"
            )
    except Exception:
        if tombstone.exists() or tombstone.is_symlink():
            os.replace(tombstone, destination)
        raise

    _remove_path(tombstone)
    return existing
