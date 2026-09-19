"""Optional Django project ingestion and lazy registry indexing."""

import ast
from collections import Counter
from dataclasses import dataclass, field
from importlib import import_module
import inspect
import os
from pathlib import Path
import sys

from .base import IngestedOperation, normalize_path, register_operation, remember_object


@dataclass
class DjangoProject:
    """One mounted Django project/registry in a Gateway."""

    root: Path
    settings: str | None
    name: str | None
    registry: object = field(repr=False)
    apps: tuple[object, ...] = field(default_factory=tuple, repr=False)
    management_indexed: bool = False

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


def _django_types():
    """Return Django ORM base types, or None when Django is unavailable."""
    try:
        models = import_module("django.db.models")
    except ModuleNotFoundError as exc:
        if exc.name == "django" or str(exc.name).startswith("django."):
            return None
        raise
    return models.Model, models.Manager


def source_kind(source):
    """Return the Django ORM source kind for an object, if any."""
    types = _django_types()
    if types is None:
        return None

    model_type, manager_type = types
    if inspect.isclass(source):
        try:
            if issubclass(source, model_type):
                return "model"
        except TypeError:
            pass
    if isinstance(source, model_type):
        return "instance"
    if isinstance(source, manager_type):
        return "manager"
    return None


def _model_for(source, kind=None):
    kind = kind or source_kind(source)
    if kind == "model":
        return source
    if kind == "instance":
        return type(source)
    if kind == "manager":
        return source.model
    raise TypeError("Source is not a Django model, model instance, or manager")


def _model_identity(model, *, path=None):
    """Return canonical root and semantic subject for one Django model."""
    meta = model._meta
    subject = str(meta.model_name)
    app_label = getattr(meta, "app_label", None)
    if app_label:
        return (str(app_label), subject), subject
    if path is not None:
        root = normalize_path(path)
        if root[-1] == subject:
            return root, subject
    return (subject,), subject


def _public_bound_methods(source):
    """Yield safe public bound callables without evaluating arbitrary properties."""
    cls = source if inspect.isclass(source) else type(source)
    for name in dir(cls):
        if name.startswith("_"):
            continue
        try:
            descriptor = inspect.getattr_static(cls, name)
        except AttributeError:
            continue
        if not callable(descriptor) and not isinstance(
            descriptor,
            (classmethod, staticmethod),
        ):
            continue
        try:
            value = getattr(source, name)
        except Exception:
            continue
        if callable(value):
            yield name, value


def _class_operations(model):
    """Yield only class/static methods from a model class."""
    for name in dir(model):
        if name.startswith("_"):
            continue
        try:
            descriptor = inspect.getattr_static(model, name)
        except AttributeError:
            continue
        if not isinstance(descriptor, (classmethod, staticmethod)):
            continue
        try:
            value = getattr(model, name)
        except Exception:
            continue
        if callable(value):
            yield name, value


def _register_surface(gateway, source, methods, root, subject, kind):
    """Register one Django callable surface under its model identity."""
    record = remember_object(gateway, source, root)
    wrapped = []
    for name, callable_ in methods:
        operation_path = (*root, name)
        existing = record.operations.get(operation_path)
        if existing is not None:
            continue
        operation = IngestedOperation(
            operation_path,
            callable_,
            source=source,
            kind=kind,
            op=name,
            sub=subject,
            metadata={
                "model": subject,
                "object": source,
            },
        )
        registered = register_operation(gateway, operation)
        record.operations[operation_path] = registered
        if record.operation is None:
            record.operation = registered
        record.registered = True
        wrapped.append(registered)
    return wrapped


def ingest_manager(gateway, manager, *, path=None, **kwargs):
    """Expose public manager/query operations on the manager's model subject."""
    model = _model_for(manager, "manager")
    root, subject = _model_identity(model, path=path)
    wrapped = _register_surface(
        gateway,
        manager,
        _public_bound_methods(manager),
        root,
        subject,
        "django-manager",
    )
    record = remember_object(gateway, manager, root, expander=ingest_manager)
    _register_path_aliases(gateway, wrapped, record.paths)
    record.expanded = True
    return wrapped


def _register_path_aliases(gateway, wrapped, roots):
    """Register alternate semantic paths for already-wrapped operations."""
    for operation in wrapped:
        path = getattr(operation, "__gway_path__", None)
        if not path:
            continue
        name = path[-1]
        for root in roots:
            alias = ".".join((*root, name))
            gateway.ops.register_alias(alias, operation)


def ingest_model(gateway, model, *, path=None, **kwargs):
    """Expose one model's manager and class-level operations."""
    root, subject = _model_identity(model, path=path)
    record = remember_object(gateway, model, root, expander=ingest_model)
    if record.expanded:
        return []

    wrapped = []
    manager = getattr(model, "_default_manager", None)
    if manager is not None:
        wrapped.extend(ingest_manager(gateway, manager, path=root))
    wrapped.extend(
        _register_surface(
            gateway,
            model,
            _class_operations(model),
            root,
            subject,
            "django-model",
        )
    )
    record.expanded = True
    return wrapped


def ingest_instance(gateway, instance, *, path=None, **kwargs):
    """Expose bound instance methods and bind the object to its model subject."""
    model = _model_for(instance, "instance")
    root, subject = _model_identity(model, path=path)

    # Make the explicitly ingested object available for semantic completion.
    gateway.context[subject] = instance

    wrapped = ingest_model(gateway, model, path=root)
    record = remember_object(
        gateway,
        instance,
        root,
        expander=ingest_instance,
    )
    if not record.expanded:
        wrapped.extend(
            _register_surface(
                gateway,
                instance,
                _public_bound_methods(instance),
                root,
                subject,
                "django-instance",
            )
        )
        record.expanded = True
    return wrapped


def ingest_app(gateway, app, *, path=None, **kwargs):
    """Mark one Django app registry node expanded; models remain lazy children."""
    root = normalize_path(path) if path is not None else (app.label,)
    record = remember_object(gateway, app, root, expander=ingest_app)
    record.expanded = True
    return []


def ingest_orm(gateway, source, *, path=None, **kwargs):
    """Route a Django ORM object to its model-scoped ingestor."""
    kind = source_kind(source)
    if kind == "model":
        return ingest_model(gateway, source, path=path, **kwargs)
    if kind == "instance":
        return ingest_instance(gateway, source, path=path, **kwargs)
    if kind == "manager":
        return ingest_manager(gateway, source, path=path, **kwargs)
    raise TypeError("Source is not a Django ORM object")


def _management_api():
    """Return Django management discovery/execution functions lazily."""
    try:
        management = import_module("django.core.management")
    except ModuleNotFoundError as exc:
        if exc.name == "django" or str(exc.name).startswith("django."):
            raise ModuleNotFoundError(
                "Django ingestion requires Django to be installed"
            ) from exc
        raise
    return management.get_commands, management.call_command


@dataclass(frozen=True)
class DjangoCommand:
    """Lazy reference to one command on one named Django project."""

    mount: DjangoProject
    name: str


def _command_callable(command_name):
    """Create a lightweight GWAY operation backed by Django call_command()."""
    def invoke(*args, **options):
        _, call_command = _management_api()
        return call_command(command_name, *args, **options)

    invoke.__name__ = str(command_name)
    invoke.__doc__ = f"Run Django management command {command_name!r}."
    return invoke


def ingest_command(gateway, command, *, path=None, **kwargs):
    """Expose one lazily indexed Django management command."""
    mount = command.mount
    if not mount.management_enabled:
        return []

    root = (mount.name, command.name)
    record = remember_object(
        gateway,
        command,
        root,
        expander=ingest_command,
    )
    if record.expanded:
        return []

    human_name = command.name.replace("_", " ")
    operation = IngestedOperation(
        root,
        _command_callable(command.name),
        source=mount,
        kind="django-command",
        aliases=(
            f"{human_name} {mount.name}",
            f"{mount.name} {human_name}",
        ),
        op=command.name,
        sub=mount.name,
        metadata={
            "project": mount.name,
            "command": command.name,
            "settings": mount.settings,
        },
    )
    registered = register_operation(gateway, operation)
    record.operations[root] = registered
    record.operation = registered
    record.registered = True
    record.expanded = True
    return [registered]


def ingest_commands(gateway, mount, *, path=None, **kwargs):
    """Expand every indexed management command for an explicitly requested mount."""
    if not mount.management_enabled:
        return []

    _index_management(gateway, mount)
    wrapped = []
    for record in tuple(gateway._ingested.values()):
        value = record.value
        if isinstance(value, DjangoCommand) and value.mount is mount:
            wrapped.extend(ingest_command(gateway, value))
    return wrapped


def _index_management(gateway, mount):
    """Index command names as lazy project-qualified resolution branches."""
    if not mount.management_enabled or mount.management_indexed:
        return mount

    get_commands, _ = _management_api()
    for command_name in sorted(get_commands()):
        name = str(command_name)
        command = DjangoCommand(mount, name)
        human = tuple(part for part in name.split("_") if part)
        paths = {
            (name, mount.name),
            (*human, mount.name),
            (mount.name, name),
            (mount.name, *human),
        }
        for command_path in paths:
            remember_object(
                gateway,
                command,
                command_path,
                expander=ingest_command,
            )

    mount.management_indexed = True
    return mount


def _index_registry(gateway, mount):
    """Remember apps/models under global and project-qualified lazy paths."""
    apps = tuple(mount.registry.get_app_configs())
    mount.apps = apps

    models = []
    for app in apps:
        app_name = str(app.label)
        app_paths = [(app_name,)]
        if mount.name is not None:
            app_paths.append((mount.name, app_name))

        for app_path in app_paths:
            remember_object(gateway, app, app_path, expander=ingest_app)

        for model in app.get_models():
            model_name = str(model._meta.model_name)
            models.append((app, model, model_name))
            for app_path in app_paths:
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
            if mount.name is not None:
                remember_object(
                    gateway,
                    model,
                    (mount.name, model_name),
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
        _index_management(gateway, mount)
        return mount

    if name is not None:
        if mount.name is not None and mount.name != name:
            raise ValueError(
                f"Django project is already mounted as {mount.name!r}"
            )
        mount.name = name
        _index_management(gateway, mount)

    return mount
