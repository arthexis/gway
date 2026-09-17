from __future__ import annotations

import argparse
from collections.abc import Sequence
from importlib.metadata import version as distribution_version

from ..dispatcher import Dispatcher
from ..install import Installer
from ..operations.install import install_project
from ..operations.project import (
    managed_status as _shared_managed_status,
    runtime_component_record as _shared_runtime_component_record,
    upgrade_status as _shared_upgrade_status,
)
from ..operations.service import (
    install_project_service as _shared_install_project_service,
    run_service as _shared_run_service,
)
from ..operations.upgrade import run_upgrade as _shared_run_upgrade
from ..project import Project
from ..registry import Registry
from ..runtime import GwayRuntime
from ..service import ServiceManager
from ..shell import (
    install_shell,
    integration_snippet,
    launch_shell,
    shell_status,
    uninstall_shell,
)
from ..solve import solve_values
from ..upgrade import UpgradeResult, Upgrader
from .errors import (
    _can_suggest_sudo,
    _extract_global_flags,
    _handle_cli_exception,
    _known_cli_error,
    _managed_result_name,
    _permission_failure,
    _prompt_required_value,
    _report_error,
)
from .help import _print_project_help
from .main import CliDependencies, run_main
from .parser import CORE_COMMANDS, build_parser
from .render import _render_result, _render_upgrade_record

RUNTIME_COMPONENTS = {"sigils": "gway-sigils"}


def _project_record(project: Project) -> dict[str, object]:
    record: dict[str, object] = {
        "name": project.name,
        "path": project.path,
        "adapter": project.adapter_type,
    }
    if project.aliases:
        record["aliases"] = list(project.aliases)
    if project.repository:
        record["repository"] = project.repository
    if project.revision:
        record["revision"] = project.revision
    if project.service_config is not None:
        record["service"] = project.service_config
    return record


def _runtime_component_record(name: str) -> dict[str, object] | None:
    return _shared_runtime_component_record(name, version_resolver=distribution_version)


def _managed_status(status: str, project: Project) -> dict[str, object]:
    return _shared_managed_status(status, project)


def _upgrade_status(status: str, result: UpgradeResult) -> dict[str, object]:
    return _shared_upgrade_status(status, result)


def _install_project_service(project: Project) -> dict[str, object]:
    return _shared_install_project_service(project, manager_factory=ServiceManager)


def _run_upgrade(
    namespace: argparse.Namespace,
    registry: Registry,
    *,
    json_output: bool,
    arguments: Sequence[str] = (),
) -> object:
    on_completed = None
    if not json_output:
        on_completed = lambda record: _render_upgrade_record(record, detail=namespace.detail)
    result = _shared_run_upgrade(
        registry,
        projects=namespace.projects,
        all_projects=namespace.all,
        upgrade_self=namespace.upgrade_self,
        force=namespace.force,
        try_force=namespace.try_force,
        reload=namespace.reload,
        arguments=arguments,
        upgrader_factory=Upgrader,
        on_completed=on_completed,
    )
    return result if json_output else None


def _run_service(namespace: argparse.Namespace, registry: Registry) -> object:
    return _shared_run_service(
        registry,
        action=namespace.action,
        project_name=namespace.project,
        user=namespace.user,
        enable=namespace.enable,
        start=namespace.start,
        manager_factory=ServiceManager,
    )


def main(argv: Sequence[str] | None = None, *, dispatcher: Dispatcher | None = None) -> int:
    """Compatibility entrypoint delegating orchestration to :mod:`gway.cli.main`."""
    dependencies = CliDependencies(
        solve_values=solve_values,
        prompt_required_value=_prompt_required_value,
        render_result=_render_result,
        handle_cli_exception=_handle_cli_exception,
        print_project_help=_print_project_help,
        project_record=_project_record,
        runtime_component_record=_runtime_component_record,
        managed_status=_managed_status,
        run_upgrade=_run_upgrade,
        run_service=_run_service,
        runtime_factory=GwayRuntime,
        installer_factory=Installer,
        install_project_op=install_project,
        service_manager_factory=ServiceManager,
        install_shell=install_shell,
        uninstall_shell=uninstall_shell,
        shell_status=shell_status,
        launch_shell=launch_shell,
        integration_snippet=integration_snippet,
    )
    return run_main(argv, dispatcher=dispatcher, dependencies=dependencies)


__all__ = ["build_parser", "main"]
