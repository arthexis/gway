from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from ..runner import RunnerError


@dataclass(frozen=True)
class HandlerResult:
    value: object = None
    exit_code: int | None = None
    render: bool = True
    show_help: bool = False


def handle_core_command(
    namespace: argparse.Namespace,
    passthrough: Sequence[str],
    *,
    dispatcher: object,
    registry: object,
    interactive: bool,
    json_output: bool,
    prompt: Callable[[str], str],
    project_record: Callable[[object], dict[str, object]],
    runtime_component_record: Callable[[str], dict[str, object] | None],
    managed_status: Callable[[str, object], dict[str, object]],
    run_upgrade: Callable[..., object],
    run_service: Callable[..., object],
    solve: Callable[..., object],
    runtime_factory: Callable[[object], Any],
    installer_factory: Callable[[object], Any],
    install_project_op: Callable[..., dict[str, object]],
    service_manager_factory: Callable[[object], Any],
    install_shell_fn: Callable[[str | None], object],
    uninstall_shell_fn: Callable[[str | None], object],
    shell_status_fn: Callable[[str | None], object],
    launch_shell_fn: Callable[[str | None], int],
    integration_snippet_fn: Callable[[str | None], str],
) -> HandlerResult:
    command = namespace.command

    if command == "list":
        projects = registry.list()
        value = (
            [project_record(project) for project in projects]
            if namespace.detail
            else [project.name for project in projects]
        )
        return HandlerResult(value=value)

    if command == "info":
        return HandlerResult(value=project_record(registry.require(namespace.project)))

    if command == "path":
        return HandlerResult(value=registry.require(namespace.project).path)

    if command == "solve":
        return HandlerResult(
            value=solve(
                namespace.value,
                interactive=interactive,
                prompt=prompt,
            )
        )

    if command == "recipe":
        recipe_tokens = ["recipe"]
        if namespace.path.startswith("-"):
            recipe_tokens.append("--")
        recipe_tokens.extend([namespace.path, *passthrough])
        return HandlerResult(
            value=runtime_factory(dispatcher).execute(
                recipe_tokens,
                interactive=interactive,
                prompt=prompt if interactive else None,
            )
        )

    if command == "register":
        project = registry.register_path(namespace.path)
        return HandlerResult(value=managed_status("registered", project))

    if command == "install":
        if namespace.adopt_from and not namespace.adopt:
            raise RunnerError("--from requires --adopt")
        if namespace.dry_run and not namespace.adopt:
            raise RunnerError("--dry-run requires --adopt")
        if namespace.adopt and not namespace.adopt_from:
            raise RunnerError("--adopt requires --from PATH")
        if namespace.adopt and not namespace.dry_run:
            raise RunnerError(
                "managed adoption execution is not available yet; rerun with --dry-run"
            )
        if namespace.adopt and namespace.service:
            raise RunnerError("--service cannot be combined with --adopt --dry-run")

        result = runtime_component_record(namespace.project)
        if result is not None and namespace.adopt:
            raise RunnerError("built-in runtime components cannot be adopted")
        if result is not None and passthrough:
            raise RunnerError("built-in runtime component install does not accept project arguments")
        if result is not None and namespace.service:
            result["service"] = {
                "status": "not-provided",
                "message": f"{namespace.project} does not provide a service",
            }
        if result is not None:
            return HandlerResult(value=result)

        if namespace.adopt:
            installer = installer_factory(registry)
            lifecycle_arguments = (
                "--adopt",
                "--from",
                namespace.adopt_from,
                "--dry-run",
                *passthrough,
            )
            preview = installer.preview_adoption(
                namespace.project,
                namespace.adopt_from,
                arguments=lifecycle_arguments,
            )
            return HandlerResult(
                value={
                    "status": "preflight",
                    "name": preview.name,
                    "source": preview.source,
                    "target": preview.target,
                    "revision": preview.revision,
                    "adopt": True,
                    "dry_run": True,
                }
            )

        return HandlerResult(
            value=install_project_op(
                registry,
                namespace.project,
                arguments=passthrough,
                service=namespace.service,
                installer_factory=installer_factory,
                manager_factory=service_manager_factory,
            )
        )

    if command == "upgrade":
        return HandlerResult(
            value=run_upgrade(
                namespace,
                registry,
                json_output=json_output,
                arguments=passthrough,
            )
        )

    if command == "service":
        return HandlerResult(value=run_service(namespace, registry))

    if command == "shell":
        if namespace.action is None:
            return HandlerResult(exit_code=launch_shell_fn(namespace.shell_name), render=False)
        if namespace.action == "print":
            print(integration_snippet_fn(namespace.shell_name), end="")
            return HandlerResult(exit_code=0, render=False)
        if namespace.action == "install":
            return HandlerResult(value=install_shell_fn(namespace.shell_name))
        if namespace.action == "uninstall":
            return HandlerResult(value=uninstall_shell_fn(namespace.shell_name))
        return HandlerResult(value=shell_status_fn(namespace.shell_name))

    return HandlerResult(render=False, show_help=True)
