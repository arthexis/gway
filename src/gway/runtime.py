from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import runtime_base as _base
from .event_command import run_event

# Preserve the established runtime dependency patch points. Tests and callers
# have historically replaced these names on gway.runtime, so the compatibility
# facade must execute core operations through these module-level bindings rather
# than bypassing them through runtime_base.
Installer = _base.Installer
Upgrader = _base.Upgrader
run_log = _base.run_log

# Extend the established core-operation registry without changing routing for
# existing operations.
_base._CORE_OPERATIONS = frozenset((*_base._CORE_OPERATIONS, "event"))


def _service_not_provided(project_name: str) -> dict[str, object]:
    return {
        "status": "not-provided",
        "message": f"{project_name} does not provide a service",
    }


def _install_project_service(
    project: _base.Project,
    *,
    profile: str | None = None,
) -> dict[str, object]:
    if profile is None:
        return _base._install_project_service(project)
    try:
        manager = _base.ServiceManager(project, profile=profile)
    except _base.ServiceError as exc:
        if "does not declare [service] or [services]" not in str(exc):
            raise
        return _service_not_provided(project.name)
    unit = manager.install()
    return {"status": "installed", "unit": unit, "profile": profile}


def _quiesce_project_services(project: _base.Project) -> tuple[str, ...]:
    """Stop active installed units before mutating a managed project."""
    try:
        manager = _base.ServiceManager(project, all_services=True)
    except _base.ServiceError as exc:
        if "does not declare [service] or [services]" not in str(exc):
            raise
        return ()

    statuses = manager.status()
    if isinstance(statuses, dict):
        records = [statuses]
    else:
        records = statuses
    active = tuple(
        str(record["service"])
        for record in records
        if record.get("active") is True and record.get("service")
    )
    for service in reversed(active):
        _base.ServiceManager(project, service=service).stop()
    return active


def _restore_project_services(project: _base.Project, services: Sequence[str]) -> None:
    """Restart the exact units that were active before a rolled-back upgrade."""
    for service in services:
        _base.ServiceManager(project, service=service).start()


class GwayRuntime(_base.GwayRuntime):
    """Gway runtime with the core event operation enabled."""

    def _run_core(self, tokens: Sequence[str]) -> object:
        operation = tokens[0]
        if operation == "event":
            return run_event(tokens[1:], dispatch=self.dispatcher.run)
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
        raise _base.DispatchError(f"unknown GWAY core operation: {operation}")

    def _run_install(self, argv: Sequence[str]) -> object:
        parser = _base._RuntimeParser(prog="gway install", add_help=False)
        parser.add_argument("project", nargs="?")
        parser.add_argument("--service", action="store_true")
        parser.add_argument("--service-profile")
        parser.add_argument("--self", dest="install_self", action="store_true")
        parser.add_argument(
            "--clean",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
        namespace, passthrough = parser.parse_known_args(list(argv))
        if namespace.service_profile is not None and not namespace.service:
            raise _base.DispatchError("--service-profile requires --service")
        if namespace.install_self:
            if namespace.project is not None:
                raise _base.DispatchError("--self cannot be combined with PROJECT")
            if passthrough:
                raise _base.DispatchError(
                    "GWAY self-install does not accept project arguments"
                )
            return self._run_upgrade(["gway"])
        if namespace.project is None:
            raise _base.DispatchError("the following arguments are required: project")
        if namespace.project == "gway":
            if passthrough:
                raise _base.DispatchError(
                    "GWAY self-install does not accept project arguments"
                )
            return self._run_upgrade(["gway"])
        result = _base._runtime_component_record(namespace.project)
        if result is not None:
            if passthrough:
                raise _base.DispatchError(
                    "built-in runtime component install does not accept arguments"
                )
            if namespace.service:
                result["service"] = _service_not_provided(namespace.project)
            return result

        previous_project = self.registry.get(namespace.project)
        active_services: tuple[str, ...] = ()
        if namespace.service and previous_project is not None:
            active_services = _quiesce_project_services(previous_project)

        installer = Installer(self.registry)
        install_kwargs = {"clean": False} if not namespace.clean else {}
        try:
            project = installer.install(
                namespace.project,
                arguments=passthrough,
                **install_kwargs,
            )
        except Exception:
            if previous_project is not None and active_services:
                restored_project = self.registry.get(namespace.project) or previous_project
                _restore_project_services(restored_project, active_services)
            raise

        result = _base._managed_status("installed", project)
        if namespace.service:
            result["service"] = _install_project_service(
                project,
                profile=namespace.service_profile,
            )
        return result

    def _run_uninstall(self, argv: Sequence[str]) -> object:
        parser = _base._RuntimeParser(prog="gway uninstall", add_help=False)
        parser.add_argument("project")
        namespace = parser.parse_args(list(argv))
        project = Installer(self.registry).uninstall(namespace.project)
        return _base._managed_status("uninstalled", project)

    def _run_upgrade(self, argv: Sequence[str]) -> object:
        parser = _base._RuntimeParser(prog="gway upgrade", add_help=False)
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
        parser.add_argument("--install", action="store_true")
        parser.add_argument("--service", action="store_true")
        parser.add_argument("--service-profile")
        parser.add_argument("--detail", action="store_true")
        parser.add_argument(
            "--clean",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
        namespace, passthrough = parser.parse_known_args(list(argv))
        if namespace.service_profile is not None and not namespace.service:
            raise _base.UpgradeError("--service-profile requires --service")
        targets = list(dict.fromkeys(namespace.projects))
        if targets and (namespace.all or namespace.upgrade_self is not None):
            raise _base.UpgradeError(
                "PROJECTS cannot be combined with --all, --self, or --no-self"
            )
        include_self_target = "gway" in targets
        managed_targets = [target for target in targets if target != "gway"]
        if namespace.install and not managed_targets:
            raise _base.UpgradeError("--install requires an explicit managed PROJECT")
        if namespace.service and not managed_targets:
            raise _base.UpgradeError("--service requires an explicit managed PROJECT")
        if passthrough and len(managed_targets) != 1:
            raise _base.UpgradeError(
                "installer arguments require exactly one managed PROJECT"
            )
        upgrader = Upgrader(self.registry)
        results: list[dict[str, object]] = []
        if targets:
            if include_self_target:
                upgrader.upgrade_self()
                result = {
                    "status": "upgraded",
                    "name": "gway",
                    "repository": "arthexis/gway",
                    "revision": "main",
                }
                results.append(result)
                self._publish_progress(result)
            for target in managed_targets:
                upgrade_kwargs: dict[str, object] = {}
                if namespace.try_force:
                    upgrade_kwargs["try_force"] = True
                if namespace.install:
                    upgrade_kwargs["install"] = True
                if not namespace.clean:
                    upgrade_kwargs["clean"] = False

                previous_project = self.registry.get(target)
                active_services: tuple[str, ...] = ()
                if namespace.service and previous_project is not None:
                    active_services = _quiesce_project_services(previous_project)
                try:
                    changed = upgrader.project_result(
                        target,
                        force=namespace.force,
                        reload=namespace.reload,
                        arguments=passthrough if len(managed_targets) == 1 else (),
                        **upgrade_kwargs,
                    )
                except Exception:
                    if previous_project is not None and active_services:
                        restored_project = self.registry.get(target) or previous_project
                        _restore_project_services(restored_project, active_services)
                    raise

                if getattr(changed, "installed", False):
                    status = "installed"
                else:
                    status = "upgraded" if changed.changed else "skipped"
                result = _base._upgrade_status(status, changed)
                if namespace.service:
                    result["service"] = _install_project_service(
                        changed.project,
                        profile=namespace.service_profile,
                    )
                results.append(result)
                self._publish_progress(result)
            if len(managed_targets) == 1 and not include_self_target:
                return results[0]
            return results
        default_mode = not namespace.all and namespace.upgrade_self is None
        include_self = namespace.upgrade_self is True or (
            namespace.upgrade_self is None and (default_mode or namespace.all)
        )
        include_projects = (
            namespace.all or default_mode or namespace.upgrade_self is False
        )
        if include_self:
            upgrader.upgrade_self()
            result = {
                "status": "upgraded",
                "name": "gway",
                "repository": "arthexis/gway",
                "revision": "main",
            }
            results.append(result)
            self._publish_progress(result)
        if include_projects:
            upgrade_kwargs = {"try_force": True} if namespace.try_force else {}
            if not namespace.clean:
                upgrade_kwargs["clean"] = False
            for changed in upgrader.all_project_results(
                force=namespace.force,
                reload=namespace.reload,
                **upgrade_kwargs,
            ):
                status = "upgraded" if changed.changed else "skipped"
                result = _base._upgrade_status(status, changed)
                results.append(result)
                self._publish_progress(result)
        return results


def __getattr__(name: str) -> object:
    return getattr(_base, name)


__all__ = ["GwayRuntime"]
