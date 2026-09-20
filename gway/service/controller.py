"""Gateway-bound public service operations."""

from dataclasses import replace

from .runtime import ProcessBackend


class Controller:
    """Public service lifecycle facade bound to one Gateway runtime."""

    def __init__(self, gateway, *, backend=None):
        self.gateway = gateway
        self.backend = backend
        self._fallback = ProcessBackend(
            installations=getattr(gateway, "_installed", {}),
        )

    def _service(self, project, service):
        try:
            return self.gateway._services[(project, service)]
        except KeyError as exc:
            raise LookupError(
                f"Unknown service {project!r}/{service!r}"
            ) from exc

    def list(self, project=None):
        """List discovered service definitions.

        Args:
            project: Optional project identity used to filter services.
        """
        services = self.gateway._services.values()
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
                "profiles": list(service.profiles),
            }
            for service in sorted(
                services,
                key=lambda item: item.identity,
            )
        ]

    def inspect(self, project, service):
        """Return one discovered service definition."""
        definition = self._service(project, service)
        return {
            "project": definition.project,
            "service": definition.name,
            "description": definition.description,
            "launchable": {
                "name": definition.launchable.name,
                "kind": definition.launchable.kind,
                "command": list(definition.launchable.command),
            },
            "command": list(definition.launchable.command),
            "working_directory": definition.working_directory,
            "writable_paths": list(definition.writable_paths),
            "profiles": list(definition.profiles),
            "environment": dict(definition.environment),
            "restart": definition.restart,
            "attempts": definition.attempts,
            "restart_sec": definition.restart_sec,
            "autostart": definition.autostart,
        }

    def _installed_backend(self, definition):
        if self.backend is not None:
            return self.backend

        installation = getattr(self.gateway, "_installed", {}).get(
            definition.project
        )
        if installation is None:
            return self._fallback

        from ..install.backends import get as get_backend
        from ..install.paths import install_paths
        from ..install.systemd import UnitState

        paths = install_paths(system=installation.scope == "system")
        records = UnitState(paths.root / "systemd").get(definition.project)
        record = next(
            (
                current
                for current in records
                if current.service == definition.name
            ),
            None,
        )
        if record is None:
            return self._fallback

        backend = get_backend(record.backend)
        runtime = getattr(backend, "runtime", None)
        if runtime is None:
            raise RuntimeError(
                f"Service backend {record.backend!r} has no runtime adapter"
            )
        return runtime(
            record=record,
            installations=getattr(self.gateway, "_installed", {}),
            state_root=paths.root / "services",
        )


    def install(
        self,
        project,
        service,
        *,
        backend="systemd",
        system=False,
        name=None,
        restart=None,
        attempts=None,
        restart_sec=None,
    ):
        """Install supervision for one service launchable.

        Args:
            project: Owning project identity.
            service: Service identity.
            backend: Supervision backend, normally systemd.
            system: Install as a system service instead of a user service.
            name: Optional backend-specific service name.
            restart: Restart policy override.
            attempts: Automatic retry attempts after failure.
            restart_sec: Delay between restart attempts in seconds.
        """
        definition = self._service(project, service)
        policy = {}
        if restart is not None:
            policy["restart"] = restart
        if attempts is not None:
            policy["attempts"] = attempts
        if restart_sec is not None:
            policy["restart_sec"] = restart_sec
        if policy:
            definition = replace(definition, **policy)

        from ..install.backends import get as get_backend
        from ..install.paths import install_paths

        selected = get_backend(backend)
        paths = install_paths(system=system)
        return selected.install_units(
            project,
            (definition,),
            state_root=paths.root / "systemd",
            system=system,
            name=name,
        )

    def start(self, project, service):
        """Start one discovered service through its installed backend."""
        definition = self._service(project, service)
        return self._installed_backend(definition).start(definition)

    def stop(self, project, service):
        """Stop one discovered service through its installed backend."""
        definition = self._service(project, service)
        return self._installed_backend(definition).stop(definition)

    def restart(self, project, service):
        """Restart one discovered service through its installed backend."""
        definition = self._service(project, service)
        return self._installed_backend(definition).restart(definition)

    def status(self, project, service):
        """Return runtime status through the service's installed backend."""
        definition = self._service(project, service)
        return self._installed_backend(definition).status(definition)
