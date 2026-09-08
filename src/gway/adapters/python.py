from __future__ import annotations

import argparse
import importlib
import inspect
import pkgutil
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, UnionType
from typing import Literal, Union, get_args, get_origin, get_type_hints

from gway.command import Command, Parameter
from gway.expression import STRUCTURED_TUPLE_PREFIX
from gway.project import Project

from . import AdapterError

_NONE_TYPE = type(None)
_SUPPORTED_SCALARS = {str, int, float, bool, Path}


def _cli_name(name: str) -> str:
    return name.replace("_", "-")


def _summary_and_description(obj: object) -> tuple[str | None, str | None]:
    description = inspect.getdoc(obj)
    if not description:
        return None, None
    return description.splitlines()[0], description


def _optional_inner(annotation: object) -> object:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        args = get_args(annotation)
        non_none = tuple(arg for arg in args if arg is not _NONE_TYPE)
        if len(non_none) == 1 and len(non_none) != len(args):
            return non_none[0]
    return annotation


def _converter(annotation: object):
    annotation = _optional_inner(annotation)
    origin = get_origin(annotation)
    if origin is Literal:
        values = get_args(annotation)
        if not values:
            return str, None
        value_type = type(values[0])
        if value_type not in _SUPPORTED_SCALARS:
            raise AdapterError(f"unsupported Literal type: {value_type!r}")
        return value_type, values
    if origin is tuple or annotation is tuple:
        return str, None
    if annotation in _SUPPORTED_SCALARS:
        return annotation, None
    if annotation in (inspect.Signature.empty, None, object):
        return str, None
    raise AdapterError(f"unsupported parameter annotation: {annotation!r}")


def _bool_value(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean value, got {value!r}")


def _argument_value(value: str, converter):
    """Preserve structured tuple markers through argparse conversion."""
    if value.startswith(STRUCTURED_TUPLE_PREFIX):
        return value
    return _bool_value(value) if converter is bool else converter(value)


def _argument_converter(converter):
    def convert(value: str):
        return _argument_value(value, converter)

    return convert


def _decode_structured_value(value: object) -> object:
    """Convert an internally marked comma group to one Python tuple value."""
    if isinstance(value, str) and value.startswith(STRUCTURED_TUPLE_PREFIX):
        payload = value[len(STRUCTURED_TUPLE_PREFIX) :]
        return tuple(payload.split(",")) if payload else ()
    if isinstance(value, list):
        return [_decode_structured_value(item) for item in value]
    return value


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AdapterError(message)


def _environment_site_packages(environment: Path) -> Path:
    if sys.platform == "win32":
        return environment / "Lib" / "site-packages"
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return environment / "lib" / version / "site-packages"


@contextmanager
def _project_import_path(project: Project):
    candidates = [project.path]
    src = project.path / "src"
    if src.is_dir():
        candidates.insert(0, src)
    if project.environment is not None:
        site_packages = _environment_site_packages(project.environment)
        if site_packages.is_dir():
            candidates.insert(0, site_packages)

    inserted: list[str] = []
    try:
        for candidate in reversed(candidates):
            value = str(candidate)
            if value not in sys.path:
                sys.path.insert(0, value)
                inserted.append(value)
        yield
    finally:
        for value in inserted:
            try:
                sys.path.remove(value)
            except ValueError:
                pass


class PythonAdapter:
    """Expose public Python functions as managed GWAY commands."""

    def __init__(self, project: Project) -> None:
        self.project = project
        module_name = project.adapter_config.get("module")
        if not isinstance(module_name, str) or not module_name.strip():
            raise AdapterError("python adapter requires adapter.module")
        self.module_name = module_name
        self._commands: dict[tuple[str, ...], Command] | None = None

    def _import_module(self, module_name: str) -> ModuleType:
        with _project_import_path(self.project):
            try:
                return importlib.import_module(module_name)
            except (ImportError, ModuleNotFoundError) as exc:
                message = f"cannot import Python adapter module {module_name!r}: {exc}"
                raise AdapterError(message) from exc

    def _modules(self) -> tuple[ModuleType, ...]:
        root = self._import_module(self.module_name)
        modules = [root]
        module_path = getattr(root, "__path__", None)
        if module_path is None:
            return tuple(modules)

        with _project_import_path(self.project):
            for item in pkgutil.walk_packages(module_path, prefix=f"{root.__name__}."):
                relative = item.name[len(root.__name__) + 1 :]
                if any(part.startswith("_") for part in relative.split(".")):
                    continue
                modules.append(self._import_module(item.name))
        return tuple(modules)

    def _parameter_metadata(self, function) -> tuple[Parameter, ...]:
        signature = inspect.signature(function)
        try:
            hints = get_type_hints(function)
        except (NameError, TypeError) as exc:
            message = f"cannot resolve type hints for {function.__name__}: {exc}"
            raise AdapterError(message) from exc

        parameters: list[Parameter] = []
        for parameter in signature.parameters.values():
            if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                raise AdapterError(
                    f"unsupported **{parameter.name} parameter in {function.__name__}"
                )
            annotation = hints.get(parameter.name, parameter.annotation)
            required = parameter.default is inspect.Parameter.empty and parameter.kind not in (
                inspect.Parameter.VAR_POSITIONAL,
            )
            positional = (
                parameter.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.VAR_POSITIONAL,
                )
                and parameter.default is inspect.Parameter.empty
            )
            parameters.append(
                Parameter(
                    name=parameter.name,
                    required=required,
                    positional=positional,
                    annotation=annotation,
                    default=None
                    if parameter.default is inspect.Parameter.empty
                    else parameter.default,
                )
            )
        return tuple(parameters)

    def _discover(self) -> dict[tuple[str, ...], Command]:
        commands: dict[tuple[str, ...], Command] = {}
        with _project_import_path(self.project):
            modules = self._modules()
            for module in modules:
                if module.__name__ == self.module_name:
                    prefix: tuple[str, ...] = ()
                else:
                    relative = module.__name__[len(self.module_name) + 1 :]
                    prefix = tuple(_cli_name(part) for part in relative.split("."))

                for name, function in inspect.getmembers(module, inspect.isfunction):
                    if name.startswith("_"):
                        continue
                    if function.__module__ != module.__name__:
                        continue
                    path = (*prefix, _cli_name(name))
                    summary, description = _summary_and_description(function)
                    commands[path] = Command(
                        path=path,
                        summary=summary,
                        description=description,
                        parameters=self._parameter_metadata(function),
                        adapter_data=function,
                    )
        return commands

    def _command_map(self) -> dict[tuple[str, ...], Command]:
        if self._commands is None:
            self._commands = self._discover()
        return self._commands

    def commands(self) -> tuple[Command, ...]:
        commands = self._command_map()
        return tuple(commands[path] for path in sorted(commands))

    def describe(self, path: tuple[str, ...]) -> Command:
        try:
            return self._command_map()[path]
        except KeyError as exc:
            raise AdapterError(f"unknown Python command: {' '.join(path)}") from exc

    def _parser_for(self, command: Command) -> _ArgumentParser:
        function = command.adapter_data
        if not callable(function):
            raise AdapterError(f"Python command {' '.join(command.path)} is not callable")

        parser = _ArgumentParser(
            prog=f"gway {self.project.name} {' '.join(command.path)}",
            description=command.description,
            add_help=False,
        )

        signature = inspect.signature(function)
        hints = get_type_hints(function)
        for parameter in signature.parameters.values():
            annotation = hints.get(parameter.name, parameter.annotation)
            converter, choices = _converter(annotation)
            option = f"--{_cli_name(parameter.name)}"
            value_type = _argument_converter(converter)

            if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
                parser.add_argument(
                    parameter.name,
                    nargs="*",
                    type=value_type,
                    choices=choices,
                )
                continue
            if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                raise AdapterError(
                    f"unsupported **{parameter.name} parameter in {function.__name__}"
                )

            required_positional = (
                parameter.kind
                in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                and parameter.default is inspect.Parameter.empty
            )
            if required_positional:
                parser.add_argument(
                    parameter.name,
                    type=value_type,
                    choices=choices,
                )
                continue

            if converter is bool:
                default = (
                    None if parameter.default is inspect.Parameter.empty else parameter.default
                )
                required = (
                    parameter.kind is inspect.Parameter.KEYWORD_ONLY
                    and parameter.default is inspect.Parameter.empty
                )
                parser.add_argument(
                    option,
                    action=argparse.BooleanOptionalAction,
                    default=default,
                    required=required,
                )
            else:
                required = (
                    parameter.kind is inspect.Parameter.KEYWORD_ONLY
                    and parameter.default is inspect.Parameter.empty
                )
                parser.add_argument(
                    option,
                    dest=parameter.name,
                    type=value_type,
                    choices=choices,
                    default=None
                    if parameter.default is inspect.Parameter.empty
                    else parameter.default,
                    required=required,
                )
        return parser

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        command = self.describe(path)
        function = command.adapter_data
        if not callable(function):
            raise AdapterError(f"Python command {' '.join(path)} is not callable")

        parser = self._parser_for(command)
        if "--help" in argv or "-h" in argv:
            parser.print_help()
            return None

        namespace = parser.parse_args(argv)
        values = {key: _decode_structured_value(value) for key, value in vars(namespace).items()}
        signature = inspect.signature(function)
        positional: list[object] = []
        keywords: dict[str, object] = {}
        for parameter in signature.parameters.values():
            value = values.get(parameter.name)
            if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
                positional.extend(value or [])
            elif parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
                positional.append(value)
            elif (
                parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
                and parameter.default is inspect.Parameter.empty
            ):
                positional.append(value)
            elif value is not None:
                keywords[parameter.name] = value

        with _project_import_path(self.project):
            return function(*positional, **keywords)
