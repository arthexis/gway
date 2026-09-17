from __future__ import annotations

import argparse
import re
from collections.abc import Callable, Iterator, Mapping, MutableMapping, Sequence
from contextlib import contextmanager
from importlib.metadata import version as distribution_version
from pathlib import Path

from .chain_context import current_chain_context
from .dispatcher import Dispatcher
from .dispatcher.errors import CommandNotFound, DispatchError
from .explain import record
from .expression import MANAGED_EXPRESSION_PROJECT, normalize_managed_args
from .install import Installer
from .log_command import run_log
from .operations.install import install_project, uninstall_project
from .operations.project import (
    managed_status as _shared_managed_status,
    runtime_component_record as _shared_runtime_component_record,
    upgrade_status as _shared_upgrade_status,
)
from .operations.service import install_project_service as _shared_install_project_service
from .operations.upgrade import run_upgrade as _shared_run_upgrade
from .project import Project
from .provenance import ExecutionFrame, ExecutionFrameStack
from .result import run_result
from .service import ServiceManager
from .stage import Stage
from .store import run_store
from .transfer import encode_transfer
from .upgrade import UpgradeResult, Upgrader

_SELECTOR = re.compile(r"\[(?P<index>[1-9]\d*)\]\Z")
_WILDCARD = "[*]"
_RUNTIME_COMPONENTS = {"sigils": "gway-sigils"}
_CORE_OPERATIONS = frozenset({"install", "upgrade", "uninstall", "log"})


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
    return _shared_managed_status(status, project)


def _upgrade_status(status: str, result: UpgradeResult) -> dict[str, object]:
    return _shared_upgrade_status(status, result)


def _runtime_component_record(name: str) -> dict[str, object] | None:
    return _shared_runtime_component_record(name, version_resolver=distribution_version)


def _install_project_service(project: Project) -> dict[str, object]:
    return _shared_install_project_service(project, manager_factory=ServiceManager)


class GwayRuntime:
    """Execute complete GWAY statements through one reusable runtime boundary."""

    def __init__(
        self,
        dispatcher: Dispatcher | None = None,
        *,
        on_progress: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self.dispatcher = dispatcher or Dispatcher()
        self.on_progress = on_progress
        self.frames = ExecutionFrameStack()

    @property
    def registry(self):
        return self.dispatcher.registry

    @property
    def current_frame(self) -> ExecutionFrame | None:
        return self.frames.current

    @contextmanager
    def frame_scope(
        self,
        kind: str,
        *,
        operation: str | None = None,
        tokens: Sequence[str] = (),
        recipe_path: str | None = None,
        recipe_line: int | None = None,
    ) -> Iterator[ExecutionFrame]:
        with self.frames.scope(
            kind,
            operation=operation,
            tokens=tokens,
            recipe_path=recipe_path,
            recipe_line=recipe_line,
        ) as frame:
            data: dict[str, object] = {
                "frame_id": frame.id,
                "frame_kind": frame.kind,
                "parent_frame_id": frame.parent_id,
            }
            if frame.operation is not None:
                data["operation"] = frame.operation
            if frame.tokens:
                data["tokens"] = list(frame.tokens)
            if frame.recipe_path is not None:
                data["recipe_path"] = frame.recipe_path
            if frame.recipe_line is not None:
                data["recipe_line"] = frame.recipe_line
            record("runtime.frame.enter", "entering execution frame", **data)
            try:
                yield frame
            finally:
                record("runtime.frame.exit", "leaving execution frame", **data)

    def execute(
        self,
        tokens: Sequence[str],
        *,
        context: MutableMapping[str, object] | None = None,
        interactive: bool = False,
        prompt: Callable[[str], str] | None = None,
        recipe_path: str | None = None,
        recipe_line: int | None = None,
    ) -> object:
        from .chain import run_statement

        with self.frame_scope(
            "statement",
            tokens=tokens,
            recipe_path=recipe_path,
            recipe_line=recipe_line,
        ):
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
        previous_result: object = None,
        has_previous_result: bool = False,
    ) -> object:
        if not stage.tokens:
            raise DispatchError("empty GWAY operation")
        operation = stage.tokens[0]
        with self.frame_scope(
            "operation",
            operation=operation,
            tokens=stage.raw_tokens,
        ) as frame:
            record(
                "runtime.operation.start",
                "executing GWAY operation",
                operation=operation,
                tokens=list(stage.raw_tokens),
                frame_id=frame.id,
                parent_frame_id=frame.parent_id,
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
            elif operation == "recipe":
                result = self._run_recipe_stage(
                    stage.tokens[1:],
                    previous_result=previous_result,
                    has_previous_result=has_previous_result,
                    interactive=interactive,
                    prompt=prompt,
                )
            elif operation in _CORE_OPERATIONS:
                if transfer:
                    raise DispatchError(f"{operation} cannot receive chain positionals")
                result = self._run_core(stage.tokens)
            else:
                result = self._run_managed(
                    stage,
                    transfer,
                    interactive=interactive,
                    prompt=prompt,
                )
            record(
                "runtime.operation.result",
                "completed GWAY operation",
                operation=operation,
                result=result,
                frame_id=frame.id,
                parent_frame_id=frame.parent_id,
            )
            return result

    def _run_recipe_stage(
        self,
        argv: Sequence[str],
        *,
        previous_result: object,
        has_previous_result: bool,
        interactive: bool,
        prompt: Callable[[str], str] | None = None,
    ) -> object:
        from .recipe import child_recipe_context, run_recipe
        from .recipe.params import parse_recipe_invocation, seed_recipe_parameters

        invocation = parse_recipe_invocation(argv)
        path = invocation.path
        with self.frame_scope("recipe", recipe_path=path) as frame:
            child_context = child_recipe_context(
                current_chain_context(),
                incoming=previous_result,
                has_incoming=has_previous_result,
            )
            parameter_provenance = self.frames.value_provenance(frame)
            seed_recipe_parameters(
                child_context,
                invocation.parameters,
                provenance=parameter_provenance,
            )
            record(
                "recipe.frame.enter",
                "entering child recipe frame",
                path=path,
                inherited_keys=sorted(
                    key
                    for key in child_context
                    if key != "result" and key not in invocation.parameters
                ),
                parameter_keys=sorted(invocation.parameters),
                incoming=previous_result if has_previous_result else None,
                has_incoming=has_previous_result,
                frame_id=frame.id,
                parent_frame_id=frame.parent_id,
            )
            try:
                result = run_recipe(
                    path,
                    self.dispatcher,
                    interactive=interactive,
                    prompt=prompt,
                    context=child_context,
                    runtime=self,
                )
            except Exception as exc:
                record(
                    "recipe.frame.failure",
                    "child recipe frame failed",
                    path=path,
                    error=str(exc),
                    frame_id=frame.id,
                    parent_frame_id=frame.parent_id,
                )
                raise
            record(
                "recipe.frame.exit",
                "leaving child recipe frame",
                path=path,
                result=result,
                frame_id=frame.id,
                parent_frame_id=frame.parent_id,
            )
            return result

    def _publish_progress(self, result: dict[str, object]) -> None:
        if self.on_progress is not None:
            self.on_progress(result)

    def _run_core(self, tokens: Sequence[str]) -> object:
        operation = tokens[0]
        if operation == "install":
            return self._run_install(tokens[1:])
        if operation == "upgrade":
            return self._run_upgrade(tokens[1:])
        if operation == "uninstall":
            return self._run_uninstall(tokens[1:])
        if operation == "log":
            return run_log(
                tokens[1:],
                dispatch=self.dispatcher.run,
                paths=self.registry.paths,
                resolve_consumer=self.registry.get,
            )
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
        return install_project(
            self.registry,
            namespace.project,
            arguments=passthrough,
            service=namespace.service,
            installer_factory=Installer,
            manager_factory=ServiceManager,
        )

    def _run_uninstall(self, argv: Sequence[str]) -> object:
        parser = _RuntimeParser(prog="gway uninstall", add_help=False)
        parser.add_argument("project")
        namespace = parser.parse_args(list(argv))
        return uninstall_project(
            self.registry,
            namespace.project,
            installer_factory=Installer,
        )

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
        force_mode = parser.add_mutually_exclusive_group()
        force_mode.add_argument("--force", action="store_true")
        force_mode.add_argument("--try-force", action="store_true")
        parser.add_argument("--reload", action="store_true")
        parser.add_argument("--detail", action="store_true")
        namespace, passthrough = parser.parse_known_args(list(argv))
        return _shared_run_upgrade(
            self.registry,
            projects=namespace.projects,
            all_projects=namespace.all,
            upgrade_self=namespace.upgrade_self,
            force=namespace.force,
            try_force=namespace.try_force,
            reload=namespace.reload,
            arguments=passthrough,
            upgrader_factory=Upgrader,
            on_completed=self._publish_progress,
        )

    def _run_managed(
        self,
        stage: Stage,
        transfer: Sequence[object],
        *,
        interactive: bool,
        prompt: Callable[[str], str] | None = None,
    ) -> object:
        project_name, project_args = normalize_managed_args(stage.tokens)
        _, raw_project_args = normalize_managed_args(stage.raw_tokens)
        if project_name == MANAGED_EXPRESSION_PROJECT:
            if transfer:
                raise DispatchError("fallback expressions cannot receive chain positionals")
            if prompt is None:
                return self.dispatcher.run(
                    project_name,
                    project_args,
                    interactive=interactive,
                )
            return self.dispatcher.run(
                project_name,
                project_args,
                interactive=interactive,
                prompt=prompt,
            )
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
        dispatched = [*command.path, *encoded]
        if prompt is None:
            return self.dispatcher.run(
                project.name,
                dispatched,
                interactive=interactive,
                preserve_outcome=True,
            )
        return self.dispatcher.run(
            project.name,
            dispatched,
            interactive=interactive,
            prompt=prompt,
            preserve_outcome=True,
        )


__all__ = ["GwayRuntime"]