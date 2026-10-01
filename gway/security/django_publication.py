"""Derive semantic scope publications from ingested Django operations."""

from collections import defaultdict

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


def derive_django_publications(gateway):
    """Derive project/app/access leaves from registered Django ORM operations.

    Django apps partition authority; merely installing an app never creates a
    scope. Only operations that have actually been registered are grouped, and
    Gway's existing mutation contract determines whether each operation belongs
    to the read or write leaf. Unknown callables are conservatively mutating and
    therefore never acquire read authority by inference.
    """
    ownership = {}
    for mount in _django_mounts(gateway):
        for app in mount.apps:
            ownership[id(app)] = (str(mount.name).strip().lower(), str(app.label).strip().lower())

    grouped = defaultdict(set)
    for record in gateway.ops.records():
        operation = record.callable
        kind = getattr(operation, "__gway_source_kind__", "") or ""
        if not str(kind).startswith("django-"):
            continue
        app = _operation_app(operation)
        identity = ownership.get(id(app))
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
