from __future__ import annotations

import argparse
import importlib
import os
import sys
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

from gway.command import Command, Parameter
from gway.project import Project

from . import AdapterError


def _environment_site_packages(environment: Path) -> Path:
    if sys.platform == "win32":
        return environment / "Lib" / "site-packages"
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return environment / "lib" / version / "site-packages"


@contextmanager
def _project_context(project: Project, settings: str | None):
    candidates = [project.path]
    src = project.path / "src"
    if src.is_dir():
        candidates.insert(0, src)
    if project.environment is not None:
        site_packages = _environment_site_packages(project.environment)
        if site_packages.is_dir():
            candidates.insert(0, site_packages)

    inserted: list[str] = []
    previous_settings = os.environ.get("DJANGO_SETTINGS_MODULE")
    try:
        for candidate in reversed(candidates):
            value = str(candidate)
            if value not in sys.path:
                sys.path.insert(0, value)
                inserted.append(value)
        if settings is not None:
            os.environ["DJANGO_SETTINGS_MODULE"] = settings
        yield
    finally:
        if settings is not None:
            if previous_settings is None:
                os.environ.pop("DJANGO_SETTINGS_MODULE", None)
            else:
                os.environ["DJANGO_SETTINGS_MODULE"] = previous_settings
        for value in inserted:
            try:
                sys.path.remove(value)
            except ValueError:
                pass


def _parameter_from_action(action: argparse.Action) -> Parameter | None:
    if isinstance(action, argparse._HelpAction):
        return None
    positional = not action.option_strings
    return Parameter(
        name=action.dest,
        required=action.required if not positional else action.nargs not in ("?", "*"),
        positional=positional,
        annotation=getattr(action, "type", None),
        default=action.default,
        help=action.help,
    )


class DjangoAdapter:
    """Expose Django management commands through GWAY."""

    def __init__(self, project: Project) -> None:
        self.project = project
        manage = project.adapter_config.get("manage", "manage.py")
        if not isinstance(manage, str) or not manage.strip():
            raise AdapterError("django adapter requires a valid adapter.manage path")
        self.manage = manage

        settings = project.adapter_config.get("settings")
        if settings is not None and (not isinstance(settings, str) or not settings.strip()):
            raise AdapterError("django adapter settings must be a non-empty string")
        self.settings = settings

        sigils = project.adapter_config.get("sigils")
        if sigils is not None and (not isinstance(sigils, str) or not sigils.strip()):
            raise AdapterError("django adapter sigils must be a module:function reference")
        self.sigils = sigils
        self._commands: dict[tuple[str, ...], Command] | None = None

    def _bootstrap(self):
        try:
            django = importlib.import_module("django")
            management = importlib.import_module("django.core.management")
            base = importlib.import_module("django.core.management.base")
        except (ImportError, ModuleNotFoundError) as exc:
            raise AdapterError(f"cannot import Django for {self.project.name}: {exc}") from exc

        try:
            django.setup()
        except Exception as exc:
            raise AdapterError(f"cannot initialize Django for {self.project.name}: {exc}") from exc
        return management, base

    def _load_sigil_provider(self):
        if self.sigils is None:
            return None
        module_name, separator, attribute = self.sigils.partition(":")
        if not separator or not module_name.strip() or not attribute.strip():
            raise AdapterError("django adapter sigils must use module:function syntax")
        try:
            module = importlib.import_module(module_name)
        except (ImportError, ModuleNotFoundError) as exc:
            raise AdapterError(
                f"cannot import Django Sigil provider {module_name!r}: {exc}"
            ) from exc
        try:
            provider = getattr(module, attribute)
        except AttributeError as exc:
            raise AdapterError(f"Django Sigil provider {self.sigils!r} does not exist") from exc
        if not callable(provider):
            raise AdapterError(f"Django Sigil provider {self.sigils!r} is not callable")
        return provider

    def sigil_context(self, command_path: tuple[str, ...]) -> Mapping[str, object]:
        """Return project-provided lazy Sigil context after Django initialization."""
        if self.sigils is None:
            return {}
        with _project_context(self.project, self.settings):
            self._bootstrap()
            provider = self._load_sigil_provider()
            if provider is None:
                return {}
            context = provider(project=self.project, command_path=command_path)
        if not isinstance(context, Mapping):
            raise AdapterError(f"Django Sigil provider {self.sigils!r} must return a mapping")
        return context

    @staticmethod
    def _load_command(name: str, source: object, management, base):
        if isinstance(source, base.BaseCommand):
            return source
        try:
            return management.load_command_class(source, name)
        except AttributeError as exc:
            if getattr(exc, "name", None) == "Command":
                return None
            raise AdapterError(f"cannot load Django command {name!r}: {exc}") from exc
        except Exception as exc:
            raise AdapterError(f"cannot load Django command {name!r}: {exc}") from exc

    def _discover(self) -> dict[tuple[str, ...], Command]:
        commands: dict[tuple[str, ...], Command] = {}
        with _project_context(self.project, self.settings):
            management, base = self._bootstrap()
            try:
                discovered = management.get_commands()
            except Exception as exc:
                raise AdapterError(f"cannot discover Django commands: {exc}") from exc

            for name, source in discovered.items():
                command = self._load_command(name, source, management, base)
                if command is None:
                    continue
                try:
                    parser = command.create_parser(f"gway {self.project.name}", name)
                except Exception as exc:
                    raise AdapterError(f"cannot describe Django command {name!r}: {exc}") from exc
                parameters = tuple(
                    parameter
                    for action in parser._actions
                    if (parameter := _parameter_from_action(action)) is not None
                )
                help_text = getattr(command, "help", None) or None
                commands[(name,)] = Command(
                    path=(name,),
                    summary=help_text,
                    description=help_text,
                    parameters=parameters,
                    adapter_data=command,
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
            raise AdapterError(f"unknown Django command: {' '.join(path)}") from exc

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        command = self.describe(path)
        django_command = command.adapter_data
        if django_command is None:
            raise AdapterError(f"Django command {' '.join(path)} is unavailable")

        with _project_context(self.project, self.settings):
            self._bootstrap()
            django_command.run_from_argv([f"gway {self.project.name}", path[0], *argv])
        return None
