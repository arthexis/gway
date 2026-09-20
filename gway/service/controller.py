"""Gateway-bound service lifecycle operations for generic launchables."""

from dataclasses import replace
from pathlib import Path

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
    def _service_name(launchable):
        """Return the default stable service identity for one launchable."""
        return launchable.name.replace(".", "-")

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
                name or self._service_name(launchable),
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
        return replace(definition, **policy) if policy else definition

    def list(self, project=None):
        """List named service presets.

        Ordinary operations and recipes are serviceable without appearing here.
        """
        services = self.gateway._service_presets.values()
        if project is not None:
            services = (
                service
                for service in services
                if service.project == project
            )
        return [
            {
                "project": service.project,
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

    def inspect(self, *target):
        """Inspect service policy inferred for an operation or recipe invocation."""
        definition = self._definition(target)
        return {
            "project": definition.project,
            "service": definition.name,
            "description": definition.description,
            "launchable": {
                "name": definition.launchable.name,
                "kind": definition.launchable.kind,
                "command": list(definition.launchable.command),
            },
            "working_directory": definition.working_directory,
            "restart": definition.restart,
            "attempts": definition.attempts,
            "restart_sec": definition.restart_sec,
        }

    def _installed_target(self, definition, *, system=False):
        if self.backend is not None:
            return self.backend, definition

        from ..install.service import get as get_backend
        from ..install.paths import install_paths
        from ..install.service.state import ServiceInstallState

        installation = getattr(self.gateway, "_installed", {}).get(
            definition.project
        )
        use_system = (
            installation.scope == "system"
            if installation is not None
            else system
        )
        paths = install_paths(system=use_system)
        records = ServiceInstallState(
            paths.root / "services-installed"
        ).get(definition.project)
        record = next(
            (
                current
                for current in records
                if current.service == definition.name
            ),
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
        if record.command:
            definition = replace(
                definition,
                launchable=replace(
                    definition.launchable,
                    command=tuple(record.command),
                ),
            )

        policy = {}
        if record.restart is not None:
            policy["restart"] = record.restart
        if record.attempts is not None:
            policy["attempts"] = record.attempts
        if record.restart_sec is not None:
            policy["restart_sec"] = record.restart_sec
        if policy:
            definition = replace(definition, **policy)

        return (
            runtime(
                record=record,
                installations=getattr(self.gateway, "_installed", {}),
                state_root=paths.root / "services",
            ),
            definition,
        )

    def install(
        self,
        *target,
        backend="systemd",
        system=False,
        name=None,
        restart=None,
        attempts=None,
        restart_sec=None,
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
        """
        definition = self._definition(
            target,
            name=name,
            restart=restart,
            attempts=attempts,
            restart_sec=restart_sec,
        )

        from ..install.service import get as get_backend
        from ..install.paths import install_paths

        selected = get_backend(backend)
        paths = install_paths(system=system)
        return selected.install_units(
            definition.project,
            (definition,),
            state_root=paths.root / "services-installed",
            system=system,
        )

    def start(
        self,
        *target,
        system=False,
        name=None,
    ):
        """Start any resolvable operation/recipe under service supervision."""
        definition = self._definition(target, name=name)
        backend, definition = self._installed_target(
            definition,
            system=system,
        )
        return backend.start(definition)

    def stop(
        self,
        *target,
        system=False,
        name=None,
    ):
        """Stop service supervision for an operation/recipe invocation."""
        definition = self._definition(target, name=name)
        backend, definition = self._installed_target(
            definition,
            system=system,
        )
        return backend.stop(definition)

    def restart(
        self,
        *target,
        system=False,
        name=None,
    ):
        """Restart service supervision for an operation/recipe invocation."""
        definition = self._definition(target, name=name)
        backend, definition = self._installed_target(
            definition,
            system=system,
        )
        return backend.restart(definition)

    def status(
        self,
        *target,
        system=False,
        name=None,
    ):
        """Return service status for an operation/recipe invocation."""
        definition = self._definition(target, name=name)
        backend, definition = self._installed_target(
            definition,
            system=system,
        )
        return backend.status(definition)
