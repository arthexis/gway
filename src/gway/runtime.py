from __future__ import annotations

import argparse
import re
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from importlib.metadata import version as distribution_version
from pathlib import Path

from .dispatcher import Dispatcher
from .dispatcher.errors import CommandNotFound, DispatchError
from .explain import record
from .expression import MANAGED_EXPRESSION_PROJECT, normalize_managed_args
from .install import Installer
from .project import Project
from .result import run_result
from .service import ServiceError, ServiceManager
from .stage import Stage
from .store import run_store
from .transfer import encode_transfer
from .upgrade import UpgradeError, Upgrader

_SELECTOR = re.compile(r"\[(?P<index>[1-9]\d*)\]\Z")
_WILDCARD = "[*]"
_RUNTIME_COMPONENTS = {"sigils": "gway-sigils"}
_CORE_OPERATIONS = frozenset({"install", "upgrade", "uninstall"})


class _RuntimeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise DispatchError(message)


class _Transferred:
    def __init__(self, value: object) -> None:
        self.value = value


def _selector_index(token: str) -> int | None:
    match = _SELECTOR.fullmatch(token)
    return int(match.group("index")) if match is not None else None


def _route_transfer(
    argv: Sequence[str],
    transfer: Sequence[object],
    *,
    selector_tokens: Sequence[str] | None = None,
) -> list[str | _Transferred]:
    selectors = argv if selector_tokens is None else selector_tokens
    numeric = [_selector_index(token) for token in selectors]
    explicit = any(index is not None for index in numeric) or _WILDCARD in selectors
    if not explicit:
        return [*(_Transferred(value) for value in transfer), *argv]

    if selectors.count(_WILDCARD) > 1:
        raise DispatchError("a chain stage may contain at most one [*] selector")

    selected = {index for index in numeric if index is not None}
    if selected and max(selected) > len(transfer):
        missing = max(selected)
        raise DispatchError(
            f"chain transfer selector [{missing}] is out of range for {len(transfer)} value(s)"
        )

    remainder = [value for index, value in enumerate(transfer, start=1) if index not in selected]
    routed: list[str | _Transferred] = []
    for token, selector, index in zip(argv, selectors, numeric, strict=True):
        if index is not None:
            routed.append(_Transferred(transfer[index - 1]))
        elif selector == _WILDCARD:
            routed.extend(_Transferred(value) for value in remainder)
        else:
            routed.append(token)
    return routed


def _encode_transfer_value(value: object) -> str:
    if isinstance(value, (str, bytes, bytearray)):
        return encode_transfer(value)
    if isinstance(value, (bool, int, float, Path)):
        return str(value)
    return encode_transfer(value)


def _encode_routed_values(values: Sequence[str | _Transferred]) -> list[str]:
    return [
        _encode_transfer_value(value.value) if isinstance(value, _Transferred) else value
        for value in values
    ]


def _managed_status(status: str, project: Project) -> dict[str, object]:
    record: dict[str, object] = {
        "status": status,
        "name": project.name,
        "path": project.path,
    }
    if project.repository:
        record["repository"] = project.repository
    if project.revision:
        record["revision"] = project.revision
    return record


def _runtime_component_record(name: str) -> dict[str, object] | None:
    distribution = _RUNTIME_COMPONENTS.get(name)
    if distribution is None:
        return None
    return {
        "status": "installed",
        "name": name,
        "distribution": distribution,
        "version": distribution_version(distribution),
    }


def _install_project_service(project: Project) -> dict[str, object]:
    try:
        manager = ServiceManager(project)
    except ServiceError as exc:
        if "does not declare [service] or [services]" not in str(exc):
            raise
        return {
            "status": "not-provided",
            "message": f"{project.name} does not provide a service",
        }
    unit = manager.install()
    return {"status": "installed", "unit": unit}


class GwayRuntime:
    """Execute complete GWAY statements through one reusable runtime boundary."""

    def __init__(self, dispatcher: Dispatcher | None = None) -> None:
        self.dispatcher = dispatcher or Dispatcher()

    @property
    def registry(self):
        return self.dispatcher.registry

    def execute(
        self,
        tokens: Sequence[str],
        *,
        context: MutableMapping[str, object] | None = None,
        interactive: bool = False,
        prompt: Callable[[str], str] | None = None,
    ) -> object:
        from .chain import run_statement

        return run_statement(
            self.dispatcher,
            tokens,
            interactive=interactive,
            prompt=prompt,
            context=context,
            runtime=self,
        )

    def execute_stage(
        self,
        stage: Stage,
        transfer: Sequence[object],
        *,
        interactive: bool,
        prompt: Callable[[str], str] | None = None,
    ) -> object:
        if not stage.tokens:
            raise DispatchError("empty GWAY operation")

        operation = stage.tokens[0]
        record(
            "runtime.operation.start",
            "executing GWAY operation",
            operation=operation,
            tokens=list(stage.raw_tokens),
        )
        if operation == "store":
            if transfer:
                raise DispatchError("store cannot receive chain positionals")
            result = run_store(
                stage.tokens[1:],
                interactive=interactive,
                prompt=prompt,
                paths=self.registry.paths,
            )
        elif operation == "result":
            result = run_result(
                stage.tokens[1:],
                interactive=interactive,
                prompt=prompt,
                paths=self.registry.paths,
            )
        elif operation in _CORE_OPERATIONS:
            if transfer:
                raise DispatchError(f"{operation} cannot receive chain positionals")
            result = self._run_core(stage.tokens)
        else:
            result = self._run_managed(stage, transfer, interactive=interactive)

        record(
            "runtime.operation.result",
            "completed GWAY operation",
            operation=operation,
            result=result,
        )
        return result

    def _run_core(self, tokens: Sequence[str]) -> object:
        operation = tokens[0]
        if operation == "install":
            return self._run_install(tokens[1:])
        if operation == "upgrade":
            return self._run_upgrade(tokens[1:])
        if operation == "uninstall":
            return self._run_uninstall(tokens[1:])
        raise DispatchError(f"unknown GWAY core operation: {operation}")

    def _run_install(self, argv: Sequence[str]) -> object:
        parser = _RuntimeParser(prog="gway install", add_help=False)
        parser.add_argument("project", nargs="?")
        parser.add_argument("--service", action="store_true")
        parser.add_argument("--self", dest="install_self", action="store_true")
        namespace, passthrough = parser.parse_known_args(list(argv))

        if namespace.install_self:
            if namespace.project is not None:
                raise DispatchError("--self cannot be combined with PROJECT")
            if passthrough:
                raise DispatchError("GWAY self-install does not accept project arguments")
            return self._run_upgrade(["gway"])

        if namespace.project is None:
            raise DispatchError("the following arguments are required: project")
        if namespace.project == "gway":
            if passthrough:
                raise DispatchError("GWAY self-install does not accept project arguments")
            return self._run_upgrade(["gway"])

        result = _runtime_component_record(namespace.project)
        if result is not None:
            if passthrough:
                raise DispatchError("built-in runtime component install does not accept arguments")
            if namespace.service:
                result["service"] = {
                    "status": "not-provided",
                    "message": f"{namespace.project} does not provide a service",
                }
            return result

        installer = Installer(self.registry)
        project = installer.install(namespace.project, arguments=passthrough)
        result = _managed_status("installed", project)
        if namespace.service:
            result["service"] = _install_project_service(project)
        return result

    def _run_uninstall(self, argv: Sequence[str]) -> object:
        parser = _RuntimeParser(prog="gway uninstall", add_help=False)
        parser.add_argument("project")
        namespace = parser.parse_args(list(argv))
        project = Installer(self.registry).uninstall(namespace.project)
        return _managed_status("uninstalled", project)

    def _run_upgrade(self, argv: Sequence[str]) -> object:
        parser = _RuntimeParser(prog="gway upgrade", add_help=False)
        parser.add_argument("projects", nargs="*")
        parser.add_argument("--all", action="store_true")
        parser.add_argument(
            "--self",
            dest="upgrade_self",
            action=argparse.BooleanOptionalAction,
            default=None,
        )
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--reload", action="store_true")
        parser.add_argument("--detail", action="store_true")
        namespace, passthrough = parser.parse_known_args(list(argv))

        targets = list(dict.fromkeys(namespace.projects))
        if targets and (namespace.all or namespace.upgrade_self is not None):
            raise UpgradeError("PROJECTS cannot be combined with --all, --self, or --no-self")

        include_self_target = "gway" in targets
        managed_targets = [target for target in targets if target != "gway"]
        if passthrough and len(managed_targets) != 1:
            raise UpgradeError("installer arguments require exactly one managed PROJECT")

        upgrader = Upgrader(self.registry)
        results: list[dict[str, object]] = []

        if targets:
            if include_self_target:
                upgrader.upgrade_self()
                results.append(
                    {
                        "status": "upgraded",
                        "name": "gway",
                        "repository": "arthexis/gway",
                        "revision": "main",
                    }
                )
            for target in managed_targets:
                changed = upgrader.project_result(
                    target,
                    force=namespace.force,
                    reload=namespace.reload,
                    arguments=passthrough if len(managed_targets) == 1 else (),
                )
                status = "upgraded" if changed.changed else "skipped"
                results.append(_managed_status(status, changed.project))
            return results[0] if len(results) == 1 else results

        default_mode = not namespace.all and namespace.upgrade_self is None
        include_self = namespace.upgrade_self is True or (
            namespace.upgrade_self is None and (default_mode or namespace.all)
        )
        include_projects = namespace.all or default_mode or namespace.upgrade_self is False

        if include_self:
            upgrader.upgrade_self()
            results.append(
                {
                    "status": "upgraded",
                    "name": "gway",
                    "repository": "arthexis/gway",
                    "revision": "main",
                }
            )
        if include_projects:
            for changed in upgrader.all_project_results(
                force=namespace.force,
                reload=namespace.reload,
            ):
                status = "upgraded" if changed.changed else "skipped"
                results.append(_managed_status(status, changed.project))
        return results

    def _run_managed(
        self,
        stage: Stage,
        transfer: Sequence[object],
        *,
        interactive: bool,
    ) -> object:
        project_name, project_args = normalize_managed_args(stage.tokens)
        _, raw_project_args = normalize_managed_args(stage.raw_tokens)

        if project_name == MANAGED_EXPRESSION_PROJECT:
            if transfer:
                raise DispatchError("fallback expressions cannot receive chain positionals")
            return self.dispatcher.run(project_name, project_args, interactive=interactive)

        project = self.registry.require(project_name)
        commands = self.dispatcher.commands(project_name)
        used_default = False
        try:
            command, argv = self.dispatcher._resolve_command(commands, project_args)
        except CommandNotFound:
            if not project.default_command:
                raise
            used_default = True
            command, argv = self.dispatcher._resolve_default_command(
                commands,
                project.default_command,
                project_args,
            )

        raw_argv = raw_project_args if used_default else raw_project_args[len(command.path) :]
        alias_arguments = (project.alias_arguments or {}).get(project_name, ())
        combined_argv = [*alias_arguments, *argv]
        selector_tokens = [*("" for _ in alias_arguments), *raw_argv]
        routed = _route_transfer(combined_argv, transfer, selector_tokens=selector_tokens)
        encoded = _encode_routed_values(routed)
        record(
            "transfer.route",
            "routed chain values into command arguments",
            project=project.name,
            command=list(command.path),
            incoming=list(transfer),
            selectors=list(selector_tokens),
            outgoing=list(encoded),
        )
        return self.dispatcher.run(
            project.name,
            [*command.path, *encoded],
            interactive=interactive,
        )


__all__ = ["GwayRuntime"]
