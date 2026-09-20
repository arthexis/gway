"""Standard Python project metadata discovery."""

from importlib import import_module
from pathlib import Path
import sys

from .install.manifest import load as load_manifest
from .install.model import validate_name


def _source_roots(project):
    """Return conventional import roots for one Python project."""
    project = Path(project).expanduser().resolve()
    roots = []
    src = project / "src"
    if src.is_dir():
        roots.append(src)
    roots.append(project)
    return tuple(roots)


def _module_origin(module):
    """Return the filesystem origin of an imported module/package."""
    path = getattr(module, "__file__", None)
    if path is None:
        return None
    try:
        return Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return None


def _belongs_to_roots(module, roots):
    """Return whether an imported module belongs to one project."""
    origin = _module_origin(module)
    if origin is None:
        return False
    for root in roots:
        try:
            origin.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _evict_foreign_module(name, roots):
    """Drop a cached top-level module tree owned by another project."""
    top = name.split(".", 1)[0]
    existing = sys.modules.get(top)
    if existing is None or _belongs_to_roots(existing, roots):
        return

    for module_name in tuple(sys.modules):
        if module_name == top or module_name.startswith(f"{top}."):
            sys.modules.pop(module_name, None)


def _import_from_project(project, name):
    """Import a module using this project's roots, not stale global cache."""
    roots = _source_roots(project)
    _evict_foreign_module(name, roots)

    inserted = []
    for root in reversed(roots):
        text = str(root)
        if text not in sys.path:
            sys.path.insert(0, text)
            inserted.append(text)
    try:
        return import_module(name)
    finally:
        for text in inserted:
            try:
                sys.path.remove(text)
            except ValueError:
                pass


def _target(value, *, command):
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid [project.scripts] target for {command!r}: {value!r}"
        )
    module, separator, attribute = value.partition(":")
    if not separator or not module.strip() or not attribute.strip():
        raise ValueError(
            f"Invalid [project.scripts] target for {command!r}: {value!r}; "
            "expected module:callable"
        )
    parts = attribute.split(".")
    if not all(part.isidentifier() for part in module.split(".")):
        raise ValueError(
            f"Invalid [project.scripts] module for {command!r}: {module!r}"
        )
    if not all(part.isidentifier() for part in parts):
        raise ValueError(
            f"Invalid [project.scripts] callable for {command!r}: {attribute!r}"
        )
    return f"{module}:{attribute}"


def project_scripts(project):
    """Return validated standard console-script declarations for one project."""
    project = Path(project).expanduser().resolve()
    manifest = project / "pyproject.toml"
    if not manifest.is_file():
        return {}

    data = load_manifest(manifest)
    project_data = data.get("project") if isinstance(data, dict) else None
    values = project_data.get("scripts") if isinstance(project_data, dict) else None
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ValueError("[project.scripts] must be a TOML table")

    result = {}
    for command, target in values.items():
        validate_name(command)
        result[command] = _target(target, command=command)
    return result


def resolve_target(project, target):
    """Import and return a console-script callable from a project checkout."""
    project = Path(project).expanduser().resolve()
    module_name, attribute = target.split(":", 1)

    value = _import_from_project(project, module_name)
    for part in attribute.split("."):
        value = getattr(value, part)

    if not callable(value):
        raise TypeError(f"Project script target is not callable: {target}")
    return value


def main_packages(project):
    """Return conventional package entrypoints without scanning non-packages."""
    project = Path(project).expanduser().resolve()
    roots = [project]
    src = project / "src"
    if src.is_dir():
        roots.insert(0, src)

    discovered = {}

    def walk(directory, parts=()):
        try:
            children = tuple(directory.iterdir())
        except OSError:
            return

        for child in children:
            if not child.is_dir() or not child.name.isidentifier():
                continue
            if not (child / "__init__.py").is_file():
                continue

            child_parts = (*parts, child.name)
            if (child / "__main__.py").is_file():
                discovered.setdefault(
                    ".".join(child_parts),
                    child.resolve(),
                )
            walk(child, child_parts)

    for source_root in roots:
        walk(source_root)
    return discovered


def import_project_module(project, name):
    """Import one module with the project's conventional source roots visible."""
    return _import_from_project(project, name)
