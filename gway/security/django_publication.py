"""Derive semantic scope publications from ingested Django operations."""

from collections import defaultdict
from pathlib import Path

from .publication import PublishedScope, normalize_publications


def _django_mounts(gateway):
    """Return named Django project mounts known to the ingestion registry."""
    try:
        from ..ingestion.django import DjangoProject
    except ModuleNotFoundError:
        return ()

    mounts = []
    for record in getattr(gateway, "_ingested", {}).values():
        value = getattr(record, "value", None)
        if isinstance(value, DjangoProject) and value.name:
            mounts.append(value)
    return tuple(mounts)


def _inside(root, path):
    """Return whether path is physically owned by one mounted project root."""
    try:
        root = Path(root).resolve()
        path = Path(path).resolve()
        path.relative_to(root)
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    return True


def _owned_apps(mount):
    """Yield apps whose filesystem path proves ownership by the mounted project."""
    for app in mount.apps:
        path = getattr(app, "path", None)
        if path is not None and _inside(mount.root, path):
            yield app


def _operation_app(operation):
    """Return the Django app config owning one ORM-backed operation."""
    source = getattr(operation, "__gway_source__", None)
    model = getattr(source, "model", None)
    if model is None:
        if isinstance(source, type):
            model = source
        elif source is not None:
            model = type(source)
    meta = getattr(model, "_meta", None)
    return None if meta is None else getattr(meta, "app_config", None)


def _command_sources():
    """Return Django's command-name to app-name registry lazily."""
    from ..ingestion.django import _management_api

    get_commands, _ = _management_api()
    return get_commands()


def _ownership_indexes(gateway):
    """Return object and command-source indexes for project-owned Django apps."""
    by_object = {}
    by_name = {}
    mounts = {}
    for mount in _django_mounts(gateway):
        product = str(mount.name).strip().lower()
        mounts[id(mount)] = mount
        for app in _owned_apps(mount):
            app_label = str(app.label).strip().lower()
            identity = (product, app_label)
            by_object[id(app)] = identity
            for value in (getattr(app, "name", None), getattr(app, "label", None)):
                if isinstance(value, str) and value.strip():
                    by_name[(id(mount), value.strip())] = identity
    return mounts, by_object, by_name


def _operation_identity(operation, mounts, by_object, by_name, commands):
    """Return verified product/app identity for one registered Django operation."""
    kind = getattr(operation, "__gway_source_kind__", "") or ""
    if kind == "django-command":
        mount = getattr(operation, "__gway_source__", None)
        if id(mount) not in mounts:
            return None
        metadata = getattr(operation, "__gway_metadata__", {}) or {}
        command = metadata.get("command")
        if not isinstance(command, str) or not command:
            return None
        app_name = commands.get(command)
        if not isinstance(app_name, str) or not app_name:
            return None
        return by_name.get((id(mount), app_name))

    app = _operation_app(operation)
    return by_object.get(id(app))


def derive_django_publications(gateway):
    """Derive project/app/access leaves from registered Django operations.

    Django apps partition authority; merely installing an app never creates a
    scope. Only operations that have actually been registered are grouped, and
    Gway's existing mutation contract determines whether each operation belongs
    to the read or write leaf. Unknown callables are conservatively mutating and
    therefore never acquire read authority by inference.

    Ownership is fail-closed: an app must live beneath the mounted project root.
    Django's management-command registry is used only to map an already exposed
    command back to that verified app; command names themselves never imply a
    semantic boundary or read/write classification.
    """
    mounts, by_object, by_name = _ownership_indexes(gateway)
    try:
        commands = _command_sources()
    except ModuleNotFoundError:
        commands = {}

    grouped = defaultdict(set)
    for record in gateway.ops.records():
        operation = record.callable
        kind = getattr(operation, "__gway_source_kind__", "") or ""
        if not str(kind).startswith("django-"):
            continue
        identity = _operation_identity(
            operation,
            mounts,
            by_object,
            by_name,
            commands,
        )
        if identity is None:
            # Framework/third-party apps, and operations whose ownership cannot
            # be proved, do not publish product authority.
            continue
        product, app_label = identity
        access = "write" if bool(getattr(operation, "mutates", True)) else "read"
        grouped[(product, app_label, access)].add(record.name)

    publications = []
    for (product, app_label, access), operations in sorted(grouped.items()):
        terms = frozenset({product, app_label, access})
        publications.append(
            PublishedScope(
                name="-".join((product, app_label, access)),
                source=f"django:{product}:{app_label}",
                operations=frozenset(operations),
                semantic_terms=terms,
            )
        )
    return tuple(publications)


def collect_django_publications(gateway):
    """Replace runtime-derived Django publications without touching manual ones."""
    current = normalize_publications(getattr(gateway, "_published_scopes", {}))
    current = {
        name: publication
        for name, publication in current.items()
        if not publication.source.startswith("django:")
    }
    for publication in derive_django_publications(gateway):
        existing = current.get(publication.name)
        if existing is not None and existing != publication:
            raise ValueError(
                f"Derived Django scope conflicts with existing publication: {publication.name}"
            )
        current[publication.name] = publication

    gateway._published_scopes = {
        name: publication.as_definition()
        for name, publication in sorted(current.items())
    }
    return gateway._published_scopes
