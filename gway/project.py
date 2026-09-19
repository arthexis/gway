"""Standard Python project metadata discovery."""

from importlib import import_module
from pathlib import Path
import sys
import warnings

from .install.manifest import load as load_manifest
from .install.model import validate_name


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


def legacy_scripts(project):
    """Return deprecated [install.scripts] declarations, when present."""
    project = Path(project).expanduser().resolve()
    manifest = project / "gway.toml"
    if not manifest.is_file():
        return {}

    data = load_manifest(manifest)
    install = data.get("install") if isinstance(data, dict) else None
    values = install.get("scripts") if isinstance(install, dict) else None
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ValueError("[install.scripts] must be a TOML table")

    warnings.warn(
        "[install.scripts] in gway.toml is deprecated; use "
        "[project.scripts] in pyproject.toml",
        DeprecationWarning,
        stacklevel=2,
    )
    result = {}
    for command, target in values.items():
        validate_name(command)
        result[command] = _target(target, command=command)
    return result


def scripts(project):
    """Return project launchables, preferring standard Python metadata."""
    standard = project_scripts(project)
    legacy = legacy_scripts(project)
    if not legacy:
        return standard

    # Standard Python metadata wins when both formats declare the same command.
    return {**legacy, **standard}


def resolve_target(project, target):
    """Import and return a console-script callable from a project checkout."""
    project = Path(project).expanduser().resolve()
    module_name, attribute = target.split(":", 1)

    inserted = False
    project_text = str(project)
    if project_text not in sys.path:
        sys.path.insert(0, project_text)
        inserted = True
    try:
        value = import_module(module_name)
        for part in attribute.split("."):
            value = getattr(value, part)
    finally:
        if inserted:
            try:
                sys.path.remove(project_text)
            except ValueError:
                pass

    if not callable(value):
        raise TypeError(f"Project script target is not callable: {target}")
    return value


def main_packages(project):
    """Return import names and paths for conventional package __main__.py files."""
    project = Path(project).expanduser().resolve()
    roots = [project]
    src = project / "src"
    if src.is_dir():
        roots.insert(0, src)

    discovered = {}
    for source_root in roots:
        for main in source_root.rglob("__main__.py"):
            package = main.parent
            try:
                relative = package.relative_to(source_root)
            except ValueError:
                continue

            parts = relative.parts
            if not parts or not all(part.isidentifier() for part in parts):
                continue

            current = source_root
            conventional = True
            for part in parts:
                current = current / part
                if not (current / "__init__.py").is_file():
                    conventional = False
                    break
            if not conventional:
                continue

            name = ".".join(parts)
            discovered.setdefault(name, package.resolve())
    return discovered


def import_project_module(project, name):
    """Import one module with the project's conventional source roots visible."""
    project = Path(project).expanduser().resolve()
    roots = []
    src = project / "src"
    if src.is_dir():
        roots.append(src)
    roots.append(project)

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
