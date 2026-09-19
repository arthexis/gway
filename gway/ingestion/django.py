"""Optional Django project ingestion and lazy registry indexing."""

import ast
from collections import Counter
from dataclasses import dataclass, field
from importlib import import_module
import os
from pathlib import Path
import sys

from .base import normalize_path, remember_object


@dataclass
class DjangoProject:
    """One mounted Django project/registry in a Gateway."""

    root: Path
    settings: str | None
    name: str | None
    registry: object = field(repr=False)
    apps: tuple[object, ...] = field(default_factory=tuple, repr=False)

    @property
    def management_enabled(self):
        """Whether application-wide management commands may be exposed."""
        return self.name is not None


def is_project_path(source):
    """Return whether a filesystem source is a conventional Django project."""
    path = Path(source).expanduser()
    if path.is_file():
        return path.name == "manage.py"
    return path.is_dir() and (path / "manage.py").is_file()


def _project_filesystem(source):
    """Return (project root, manage.py) for a conventional project source."""
    path = Path(source).expanduser().resolve()
    if path.is_file() and path.name == "manage.py":
        return path.parent, path
    if path.is_dir() and (path / "manage.py").is_file():
        return path, path / "manage.py"
    raise ValueError(f"Not a Django project source: {path}")


def _settings_from_manage(path):
    """Extract the conventional DJANGO_SETTINGS_MODULE default from manage.py."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) < 2:
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "setdefault":
            continue
        key, value = node.args[:2]
        if (
            isinstance(key, ast.Constant)
            and key.value == "DJANGO_SETTINGS_MODULE"
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            return value.value
    return None


def _load_django():
    """Load Django lazily so core GWAY keeps no mandatory Django dependency."""
    try:
        django = import_module("django")
        registry = import_module("django.apps").apps
    except ModuleNotFoundError as exc:
        if exc.name == "django" or str(exc.name).startswith("django."):
            raise ModuleNotFoundError(
                "Django ingestion requires Django to be installed"
            ) from exc
        raise
    return django, registry


def _setup_project(root, *, settings=None):
    """Configure Django for one project and return its populated app registry."""
    root = Path(root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    if settings is not None:
        current = os.environ.get("DJANGO_SETTINGS_MODULE")
        if current is not None and current != settings:
            raise RuntimeError(
                "DJANGO_SETTINGS_MODULE is already configured as "
                f"{current!r}, not {settings!r}"
            )
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings)

    django, registry = _load_django()
    if not getattr(registry, "ready", False):
        django.setup()
    return registry


def _mark_expanded(gateway, source, path, expander):
    record = remember_object(gateway, source, path, expander=expander)
    record.expanded = True
    return []


def ingest_app(gateway, app, *, path=None, **kwargs):
    """Expand one Django app registry node.

    ORM operations are intentionally added by the later model-ingestion layer.
    """
    root = normalize_path(path) if path is not None else (app.label,)
    return _mark_expanded(gateway, app, root, ingest_app)


def ingest_model(gateway, model, *, path=None, **kwargs):
    """Expand one Django model registry node.

    ORM operations are intentionally added by the later model-ingestion layer.
    """
    root = (
        normalize_path(path)
        if path is not None
        else (model._meta.model_name,)
    )
    return _mark_expanded(gateway, model, root, ingest_model)


def _index_registry(gateway, mount):
    """Remember apps and models as lazy GWAY branches without exposing methods."""
    apps = tuple(mount.registry.get_app_configs())
    mount.apps = apps

    models = []
    for app in apps:
        app_path = (str(app.label),)
        remember_object(gateway, app, app_path, expander=ingest_app)
        for model in app.get_models():
            model_name = str(model._meta.model_name)
            models.append((app, model, model_name))
            remember_object(
                gateway,
                model,
                (*app_path, model_name),
                expander=ingest_model,
            )

    counts = Counter(model_name for _, _, model_name in models)
    for _, model, model_name in models:
        if counts[model_name] == 1:
            remember_object(
                gateway,
                model,
                (model_name,),
                expander=ingest_model,
            )

    return mount


def _mounts(gateway):
    mounts = getattr(gateway, "_django_projects", None)
    if mounts is None:
        mounts = {}
        gateway._django_projects = mounts
    return mounts


def ingest_project(
    gateway,
    source,
    *,
    name=None,
    settings=None,
    **kwargs,
):
    """Mount one Django project and index its apps/models lazily.

    A project name authorizes later management-command ingestion. Unnamed
    projects intentionally expose only their app/model registry.
    """
    if isinstance(source, os.PathLike) or is_project_path(source):
        root, manage = _project_filesystem(source)
        settings = (
            settings
            or os.environ.get("DJANGO_SETTINGS_MODULE")
            or _settings_from_manage(manage)
        )
    elif isinstance(source, str):
        root = Path.cwd().resolve()
        settings = settings or source
    else:
        raise TypeError("Django project source must be a path or settings module")

    if not settings:
        raise ValueError(
            "Unable to determine DJANGO_SETTINGS_MODULE; pass settings= explicitly"
        )

    registry = _setup_project(root, settings=settings)
    key = (root.resolve(), settings)
    mounts = _mounts(gateway)
    mount = mounts.get(key)

    if mount is None:
        mount = DjangoProject(
            root=root.resolve(),
            settings=settings,
            name=name,
            registry=registry,
        )
        mounts[key] = mount
        _index_registry(gateway, mount)
        return mount

    if name is not None:
        if mount.name is not None and mount.name != name:
            raise ValueError(
                f"Django project is already mounted as {mount.name!r}"
            )
        mount.name = name

    return mount
