"""Gateway-bound public service operations."""

from .runtime import ProcessBackend


class Controller:
    """Public service lifecycle facade bound to one Gateway runtime."""

    def __init__(self, gateway, *, backend=None):
        self.gateway = gateway
        self.backend = backend or ProcessBackend(
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
            "command": list(definition.command),
            "working_directory": definition.working_directory,
            "writable_paths": list(definition.writable_paths),
            "profiles": list(definition.profiles),
            "environment": dict(definition.environment),
            "restart": definition.restart,
            "restart_sec": definition.restart_sec,
            "autostart": definition.autostart,
        }

    def start(self, project, service):
        """Start one discovered service in the current Gateway runtime."""
        return self.backend.start(self._service(project, service))

    def stop(self, project, service):
        """Stop one service owned by the current Gateway runtime."""
        return self.backend.stop(self._service(project, service))

    def restart(self, project, service):
        """Restart one service owned by the current Gateway runtime."""
        definition = self._service(project, service)
        return self.backend.restart(definition)

    def status(self, project, service):
        """Return runtime status for one discovered service."""
        return self.backend.status(self._service(project, service))
