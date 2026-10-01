"""Gateway-bound service lifecycle operations for generic launchables."""

from dataclasses import replace
from pathlib import Path
import math

from .model import Service
from .runtime import ProcessBackend


class Controller:
    """Service lifecycle facade over ordinary Gway operations and recipes."""

    def __init__(self, gateway, *, backend=None):
        self.gateway = gateway
        self.backend = backend
        self._fallback = ProcessBackend(
            installations=getattr(gateway, "_installed", {}),
        )

    @staticmethod
    def _timeout(value):
        if value is None:
            return None
        timeout = float(value)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("service timeout must be a finite positive number")
        return timeout

    @staticmethod
    def _service_name(project, launchable):
        """Return a project-relative stable service role for one launchable."""
        metadata_service = launchable.metadata.get("service")
        if metadata_service:
            return str(metadata_service).replace(".", "-")

        parts = [part for part in launchable.name.split(".") if part]
        while len(parts) > 1 and parts[0] == project:
            parts.pop(0)
        return "-".join(parts)

    def _project_identity(self, launchable):
        """Infer project identity/root from launchable and current runtime."""
        metadata = launchable.metadata
        project = metadata.get("project")
        root = launchable.root

        if project:
            if root is None:
                project_file = getattr(self.gateway, "_project_path", None)
                root = (
                    Path(project_file).parent
                    if project_file is not None
                    else Path.cwd()
                )
            return str(project), Path(root).expanduser().resolve()

        if root is None:
            # Rootless launchables are Gway-owned builtins/controllers rather
            # than project-ingested operations.
            root = Path(__file__).resolve().parents[2]
            return "gway", root

        try:
            from ..install.source import project_name

            project = project_name(root)
        except Exception:
            project = None

        return str(project or "gway"), Path(root).expanduser().resolve()

    def _preset(self, launchable):
        """Return optional built-in policy associated with a launchable."""
        matches = [
            service
            for service in self.gateway._service_presets.values()
            if service.launchable.name == launchable.name
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def _definition(
        self,
        target,
        *,
        name=None,
        restart=None,
        attempts=None,
        restart_sec=None,
        environment=None,
    ):
        """Resolve an arbitrary invocation into service policy."""
        from ..launchable import resolve_launchable

        launchable = resolve_launchable(self.gateway, target)
        preset = self._preset(launchable)
        if preset is not None:
            definition = replace(preset, launchable=launchable)
        else:
            project, root = self._project_identity(launchable)
            definition = Service.from_launchable(
                project,
                name or self._service_name(project, launchable),
                root,
                launchable,
            )

        policy = {}
        if name is not None:
            policy["name"] = name
        if restart is not None:
            policy["restart"] = restart
        if attempts is not None:
            policy["attempts"] = attempts
        if restart_sec is not None:
            policy["restart_sec"] = restart_sec
        if environment is not None:
            requested_environment = (
                (environment,)
                if isinstance(environment, str)
                else tuple(environment)
            )
            protected = {
                assignment.partition("=")[0]
                for assignment in definition.environment
            }
            requested_environment = tuple(
                assignment
                for assignment in requested_environment
                if str(assignment).partition("=")[0] not in protected
            )
            policy["environment"] = (
                *definition.environment,
                *requested_environment,
            )
        return replace(definition, **policy) if policy else definition

    def list(self, project=None, *, mutate=False):
        """List named service presets.

        Ordinary operations and recipes are serviceable without appearing here.
        """
        services = self.gateway._service_presets.values()
        if project is not None:
            services = (service for service in services if service.project == project)
        return [
            {
                "project": service.project,
                "kind": getattr(
                    getattr(self.gateway, "_installed", {}).get(service.project),
                    "kind",
                    "extension",
                ),
                "service": service.name,
                "description": service.description,
                "launchable": service.launchable.kind,
                "target": service.launchable.name,
            }
            for service in sorted(
                services,
                key=lambda item: item.identity,
            )
        ]

    def statuses(self, project=None, *, timeout: float = None, mutate=False):
        """Return runtime status for all installed managed services.

        Args:
            project: Optional project name filter.
            timeout: Maximum seconds for each systemd status probe.
        """
        del mutate
        timeout = self._timeout(timeout)

        from ..install.service import ServiceInstallState, get as get_backend
        from ..launchable import Launchable

        rows = []
        for system in (False, True):
            paths = self.gateway.install_paths(system=system)
            state = ServiceInstallState(paths.root / "services-installed")
            try:
                records = state.all()
            except (OSError, PermissionError):
                continue

            for record in records:
                if project is not None and record.project != project:
                    continue

                preset = self.gateway._service_presets.get(
                    (record.project, record.service)
                )
                if preset is not None:
                    definition = replace(preset)
                else:
                    installation = getattr(
                        self.gateway,
                        "_installed",
                        {},
                    ).get(record.project)
                    root = getattr(installation, "install_path", None) or Path.cwd()
                    command = tuple(record.command) or ("true",)
                    launchable = Launchable(
                        name=f"{record.project}.{record.service}",
                        kind="service",
                        command=command,
                        root=root,
                        metadata={
                            "project": record.project,
                            "service": record.service,
                        },
                    )
                    definition = Service.from_launchable(
                        record.project,
                        record.service,
                        root,
                        launchable,
                    )

                backend = get_backend(record.backend)
                runtime = getattr(backend, "runtime", None)
                if runtime is None:
                    raise RuntimeError(
                        f"Service backend {record.backend!r} has no runtime adapter"
                    )
                runtime_kwargs = {
                    "record": record,
                    "installations": getattr(self.gateway, "_installed", {}),
                    "state_root": paths.root / "services",
                }
                if record.backend == "systemd" and timeout is not None:
                    runtime_kwargs["timeout"] = timeout
                status = runtime(**runtime_kwargs).status(definition)
                rows.append(
                    {
                        "project": record.project,
                        "service": record.service,
                        "backend": record.backend,
                        "system": bool(record.system),
                        **dict(status),
                    }
                )

        return sorted(
            rows,
            key=lambda item: (
                item["project"],
                item["service"],
                item["system"],
            ),
        )

    def inspect(self, *target, mutate=False):
        """Inspect service policy inferred for an operation or recipe invocation."""
        definition = self._definition(target)
        installation = getattr(self.gateway, "_installed", {}).get(definition.project)
        return {
            "project": definition.project,
            "kind": getattr(installation, "kind", "extension"),
            "service": definition.name,
            "description": definition.description,
            "launchable": {
                "name": definition.launchable.name,
                "kind": definition.launchable.kind,
                "command": list(definition.launchable.command),
            },
            "working_directory": definition.working_directory,
            "environment": list(definition.environment),
            "restart": definition.restart,
            "attempts": definition.attempts,
            "restart_sec": definition.restart_sec,
        }

    def _installed_target(self, definition, *, system=False, timeout=None):
        if self.backend is not None:
            return self.backend, definition

        from ..install.service import get as get_backend
        from ..install.service import ServiceInstallState

        installation = getattr(self.gateway, "_installed", {}).get(definition.project)
        use_system = (
            installation.scope == "system" if installation is not None else system
        )
        paths = self.gateway.install_paths(system=use_system)
        records = ServiceInstallState(paths.root / "services-installed").get(
            definition.project
        )
        record = next(
            (current for current in records if current.service == definition.name),
            None,
        )
        if record is None:
            return self._fallback, definition

        backend = get_backend(record.backend)
        runtime = getattr(backend, "runtime", None)
        if runtime is None:
            raise RuntimeError(
                f"Service backend {record.backend!r} has no runtime adapter"
            )
        updates = {}
        if record.command:
            updates["launchable"] = replace(
                definition.launchable,
                command=tuple(record.command),
            )
        if record.environment:
            updates["environment"] = tuple(record.environment)
        if updates:
            definition = replace(definition, **updates)

        policy = {}
        if record.restart is not None:
            policy["restart"] = record.restart
        if record.attempts is not None:
            policy["attempts"] = record.attempts
        if record.restart_sec is not None:
            policy["restart_sec"] = record.restart_sec
        if policy:
            definition = replace(definition, **policy)

        runtime_kwargs = {
            "record": record,
            "installations": getattr(self.gateway, "_installed", {}),
            "state_root": paths.root / "services",
        }
        if record.backend == "systemd" and timeout is not None:
            runtime_kwargs["timeout"] = timeout
        return (
            runtime(**runtime_kwargs),
            definition,
        )

    def install(
        self,
        *target,
        backend: str = "systemd",
        system: bool = False,
        name: str = None,
        restart: str = None,
        attempts: int = None,
        restart_sec: float = None,
        environment=None,
        timeout: float = None,
    ):
        """Install supervision for any resolvable Gway operation or recipe.

        Args:
            target: Operation/recipe invocation to supervise.
            backend: Supervision backend, normally systemd.
            system: Install as a system service instead of a user service.
            name: Optional service identity override.
            restart: Restart policy override.
            attempts: Automatic retry attempts after failure.
            restart_sec: Delay between restart attempts in seconds.
            environment: Optional NAME=value environment assignment(s).
            timeout: Maximum seconds for each systemd operation; defaults to 40.
        """
        definition = self._definition(
            target,
            name=name,
            restart=restart,
            attempts=attempts,
            restart_sec=restart_sec,
            environment=environment,
        )

        from ..install.service import get as get_backend

        selected = get_backend(backend)
        paths = self.gateway.install_paths(system=system)
        timeout = self._timeout(timeout)
        install_kwargs = {}
        if backend == "systemd" and timeout is not None:
            install_kwargs["timeout"] = timeout
        return selected.install_units(
            definition.project,
            (definition,),
            state_root=paths.root / "services-installed",
            system=system,
            **install_kwargs,
        )

    def start(
        self,
        *target,
        system=False,
        name=None,
        timeout: float = None,
    ):
        """Start any resolvable operation/recipe under service supervision."""
        timeout = self._timeout(timeout)
        definition = self._definition(target, name=name)
        backend, definition = self._installed_target(
            definition,
            system=system,
            timeout=timeout,
        )
        return backend.start(definition)

    def stop(
        self,
        *target,
        system=False,
        name=None,
        timeout: float = None,
    ):
        """Stop service supervision for an operation/recipe invocation."""
        timeout = self._timeout(timeout)
        definition = self._definition(target, name=name)
        backend, definition = self._installed_target(
            definition,
            system=system,
            timeout=timeout,
        )
        return backend.stop(definition)

    def restart(
        self,
        *target,
        system=False,
        name=None,
        timeout: float = None,
    ):
        """Restart service supervision for an operation/recipe invocation."""
        timeout = self._timeout(timeout)
        definition = self._definition(target, name=name)
        backend, definition = self._installed_target(
            definition,
            system=system,
            timeout=timeout,
        )
        return backend.restart(definition)

    def status(
        self,
        *target,
        system=False,
        name=None,
        timeout: float = None,
        mutate=False,
    ):
        """Return service status for an operation/recipe invocation."""
        del mutate
        timeout = self._timeout(timeout)
        definition = self._definition(target, name=name)
        backend, definition = self._installed_target(
            definition,
            system=system,
            timeout=timeout,
        )
        return backend.status(definition)
