"""Gateway-bound security self-introspection and lifecycle integration."""


__all__ = ()


class Controller:
    """Expose caller identity and keep discovered scope policy converged."""

    def __init__(self, gateway):
        self.gateway = gateway
        self._bind_install_lifecycle()

    def _bind_install_lifecycle(self):
        """Rebind managed install operations with post-discovery convergence."""
        self.gateway.install = self.gateway.wrap("install", self._install)
        self.gateway.uninstall = self.gateway.wrap("uninstall", self._uninstall)

    def _refresh_publications(self):
        """Rediscover installed/local publishers before durable convergence."""
        from ..config import (
            _publish_project_capabilities,
            discover_managed_projects,
        )

        discover_managed_projects(self.gateway)

        project_file = getattr(self.gateway, "_project_path", None)
        if project_file is not None and project_file.is_file():
            from .. import toml

            data = toml.load(project_file)
            project_data = data.get("project") if isinstance(data, dict) else None
            project_name = (
                project_data.get("name") if isinstance(project_data, dict) else None
            )
            source = (
                project_name.strip()
                if isinstance(project_name, str) and project_name.strip()
                else str(project_file.parent)
            )
            _publish_project_capabilities(self.gateway, data, source=source)

        return self.gateway.converge_security_scopes()

    def _install(
        self,
        source,
        *,
        ref=None,
        upgrade=True,
        force=False,
        stash=False,
        system=False,
    ):
        """Install or upgrade one artifact, then converge discovered scope policy."""
        result = self.gateway._install(
            source,
            ref=ref,
            upgrade=upgrade,
            force=force,
            stash=stash,
            system=system,
        )
        self._refresh_publications()
        return result

    def _uninstall(self, project, *, system=False):
        """Uninstall one artifact, then retire no-longer-published scope policy."""
        result = self.gateway._uninstall(project, system=system)
        self._refresh_publications()
        return result

    def whoami(self, *, mutate=False):
        """Return the current caller identity and effective authority."""
        del mutate
        authority = self.gateway.authorization
        if authority is None:
            return {
                "kind": "local",
                "principal": None,
                "client_id": None,
                "scopes": [],
                "constrained": False,
                "operations": None,
                "environment": None,
            }
        return {
            "kind": authority.kind or "external",
            "principal": authority.principal,
            "client_id": authority.client_id,
            "scopes": sorted(authority.scopes),
            "constrained": True,
            "operations": sorted(authority.operations),
            "environment": (
                []
                if authority.environment is None
                else sorted(authority.environment)
            ),
        }
