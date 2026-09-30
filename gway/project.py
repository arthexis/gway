"""Standard Python project metadata discovery."""

from importlib import import_module
import ast
from pathlib import Path
import os
import pickle
import subprocess
import sys
import tempfile

from .install.metadata import load as load_metadata
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
    """Drop a cached top-level module tree owned by another project.

    Never replace Gway's own runtime package after process startup. A local
    Gway checkout may be the current project, but switching package trees
    mid-process would duplicate class identities and corrupt the runtime.
    """
    top = name.split(".", 1)[0]
    if top == __package__.split(".", 1)[0]:
        return
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
        raise ValueError(f"Invalid [project.scripts] target for {command!r}: {value!r}")
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
    metadata = project / "pyproject.toml"
    if not metadata.is_file():
        return {}

    data = load_metadata(metadata)
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


def project_python(project):
    """Return the project-owned Python interpreter when one is installed."""
    project = Path(project).expanduser().resolve()
    candidate = project / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    return candidate if candidate.is_file() else Path(sys.executable)


def _settings_from_manage_py(project):
    """Return DJANGO_SETTINGS_MODULE declared by a conventional manage.py."""
    manage = Path(project).expanduser().resolve() / "manage.py"
    if not manage.is_file():
        return None
    tree = ast.parse(manage.read_text(encoding="utf-8"), filename=str(manage))
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


_PROJECT_DJANGO_DISCOVERY = r"""
import os
import pickle
import sys

project, settings, response_path = sys.argv[1:4]
os.chdir(project)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings)

import django
django.setup()

from django.core import management

result = tuple(sorted(str(name) for name in management.get_commands()))

with open(response_path, "wb") as stream:
    pickle.dump(result, stream, protocol=pickle.HIGHEST_PROTOCOL)
"""


_PROJECT_DJANGO_CONTRACT = r"""
import inspect
import os
import pickle
import sys

project, settings, command_name, response_path = sys.argv[1:5]
os.chdir(project)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings)

import django
django.setup()

from django.core import management

app_name = management.get_commands()[command_name]
command = management.load_command_class(app_name, command_name)
handle = getattr(command, "handle", None)
mutate_default = None
if callable(handle):
    parameter = inspect.signature(handle).parameters.get("mutate")
    if parameter is not None and isinstance(parameter.default, bool):
        mutate_default = parameter.default

with open(response_path, "wb") as stream:
    pickle.dump(
        {"mutate_default": mutate_default},
        stream,
        protocol=pickle.HIGHEST_PROTOCOL,
    )
"""


_PROJECT_DJANGO_CALL = r"""
import os
import pickle
import sys

project, settings, command, request_path, response_path = sys.argv[1:6]
os.chdir(project)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings)

import django
django.setup()

from django.core.management import call_command

with open(request_path, "rb") as stream:
    args, kwargs = pickle.load(stream)

result = call_command(command, *args, **kwargs)

with open(response_path, "wb") as stream:
    pickle.dump(result, stream, protocol=pickle.HIGHEST_PROTOCOL)
"""


def project_management_commands(project):
    """Discover Django management commands inside a project's own runtime."""
    project = Path(project).expanduser().resolve()
    settings = _settings_from_manage_py(project)
    if settings is None:
        return {}

    python = project_python(project)
    with tempfile.TemporaryDirectory(prefix="gway-django-discovery-") as directory:
        response = Path(directory) / "response.pkl"
        subprocess.run(
            [
                str(python),
                "-c",
                _PROJECT_DJANGO_DISCOVERY,
                str(project),
                settings,
                str(response),
            ],
            cwd=project,
            check=True,
        )
        with response.open("rb") as stream:
            result = pickle.load(stream)

    if not isinstance(result, tuple) or any(
        not isinstance(name, str) for name in result
    ):
        raise TypeError("Django management discovery returned invalid command names")
    return result


def project_management_command_contract(project, command):
    """Inspect one Django management command inside the project runtime."""
    project = Path(project).expanduser().resolve()
    settings = _settings_from_manage_py(project)
    if settings is None:
        raise ValueError(f"Not a conventional Django project: {project}")

    python = project_python(project)
    with tempfile.TemporaryDirectory(prefix="gway-django-contract-") as directory:
        response = Path(directory) / "response.pkl"
        subprocess.run(
            [
                str(python),
                "-c",
                _PROJECT_DJANGO_CONTRACT,
                str(project),
                settings,
                str(command),
                str(response),
            ],
            cwd=project,
            check=True,
        )
        with response.open("rb") as stream:
            result = pickle.load(stream)

    if not isinstance(result, dict) or set(result) != {"mutate_default"}:
        raise TypeError("Django management command contract is invalid")
    mutate_default = result["mutate_default"]
    if mutate_default is not None and not isinstance(mutate_default, bool):
        raise TypeError("Django management mutate default must be boolean")
    return result


def invoke_management_command(project, command, *args, **kwargs):
    """Run one Django management command inside the project's own runtime."""
    project = Path(project).expanduser().resolve()
    settings = _settings_from_manage_py(project)
    if settings is None:
        raise ValueError(f"Not a conventional Django project: {project}")

    python = project_python(project)
    with tempfile.TemporaryDirectory(prefix="gway-django-command-") as directory:
        request = Path(directory) / "request.pkl"
        response = Path(directory) / "response.pkl"
        with request.open("wb") as stream:
            pickle.dump((args, kwargs), stream, protocol=pickle.HIGHEST_PROTOCOL)
        subprocess.run(
            [
                str(python),
                "-c",
                _PROJECT_DJANGO_CALL,
                str(project),
                settings,
                str(command),
                str(request),
                str(response),
            ],
            cwd=project,
            check=True,
        )
        with response.open("rb") as stream:
            return pickle.load(stream)


_PROJECT_CALL = r"""
import asyncio
import importlib
import inspect
import pickle
import sys

roots_path, target, request_path, response_path = sys.argv[1:5]
with open(roots_path, "rb") as stream:
    roots = pickle.load(stream)
for root in reversed(roots):
    sys.path.insert(0, root)
module_name, attribute = target.split(":", 1)
value = importlib.import_module(module_name)
for part in attribute.split("."):
    value = getattr(value, part)
with open(request_path, "rb") as stream:
    args, kwargs = pickle.load(stream)

parameters = inspect.signature(value).parameters
if not parameters:
    arguments = [str(argument) for argument in args]
    for key, item in kwargs.items():
        option = "--" + str(key).replace("_", "-")
        if isinstance(item, bool):
            arguments.append(option if item else "--no-" + str(key).replace("_", "-"))
        elif isinstance(item, (list, tuple)):
            for nested in item:
                arguments.extend((option, str(nested)))
        else:
            arguments.extend((option, str(item)))
    previous = sys.argv
    sys.argv = [module_name, *arguments]
    try:
        result = value()
    finally:
        sys.argv = previous
else:
    result = value(*args, **kwargs)
if inspect.isawaitable(result):
    result = asyncio.run(result)
with open(response_path, "wb") as stream:
    pickle.dump(result, stream, protocol=pickle.HIGHEST_PROTOCOL)
"""


_PROJECT_MAIN = r"""
import pickle
import runpy
import sys

roots_path, package, request_path, response_path = sys.argv[1:5]
with open(roots_path, "rb") as stream:
    roots = pickle.load(stream)
for root in reversed(roots):
    sys.path.insert(0, root)
with open(request_path, "rb") as stream:
    arguments = pickle.load(stream)
previous = sys.argv
sys.argv = [package, *map(str, arguments)]
try:
    namespace = runpy.run_module(
        f"{package}.__main__",
        run_name="__main__",
        alter_sys=True,
    )
finally:
    sys.argv = previous
result = {}
for key, value in namespace.items():
    if key.startswith("__"):
        continue
    try:
        pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        continue
    result[key] = value
with open(response_path, "wb") as stream:
    pickle.dump(result, stream, protocol=pickle.HIGHEST_PROTOCOL)
"""


def invoke_target(project, target, *args, **kwargs):
    """Invoke project-owned Python inside that project's interpreter."""
    project = Path(project).expanduser().resolve()
    python = project_python(project)
    with tempfile.TemporaryDirectory(prefix="gway-project-") as directory:
        request = Path(directory) / "request.pkl"
        response = Path(directory) / "response.pkl"
        with request.open("wb") as stream:
            pickle.dump((args, kwargs), stream, protocol=pickle.HIGHEST_PROTOCOL)
        roots = Path(directory) / "roots.pkl"
        with roots.open("wb") as stream:
            pickle.dump(
                tuple(str(root) for root in _source_roots(project)),
                stream,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        subprocess.run(
            [
                str(python),
                "-c",
                _PROJECT_CALL,
                str(roots),
                target,
                str(request),
                str(response),
            ],
            cwd=project,
            check=True,
        )
        with response.open("rb") as stream:
            return pickle.load(stream)


def invoke_package_main(project, package, *arguments):
    """Run a project package __main__ and return its serializable namespace."""
    project = Path(project).expanduser().resolve()
    python = project_python(project)
    with tempfile.TemporaryDirectory(prefix="gway-project-main-") as directory:
        request = Path(directory) / "request.pkl"
        response = Path(directory) / "response.pkl"
        with request.open("wb") as stream:
            pickle.dump(arguments, stream, protocol=pickle.HIGHEST_PROTOCOL)
        roots = Path(directory) / "roots.pkl"
        with roots.open("wb") as stream:
            pickle.dump(
                tuple(str(root) for root in _source_roots(project)),
                stream,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        subprocess.run(
            [
                str(python),
                "-c",
                _PROJECT_MAIN,
                str(roots),
                package,
                str(request),
                str(response),
            ],
            cwd=project,
            check=True,
        )
        with response.open("rb") as stream:
            return pickle.load(stream)


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
