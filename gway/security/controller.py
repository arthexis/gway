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
        from .django_publication import collect_django_publications

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

        collect_django_publications(self.gateway)
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
        """Converge one local or Git artifact installation toward requested state.

        Args:
            source: Local product or extension path, Git source, GitHub shorthand, or known installation identity.
            ref: Branch, tag, or commit requested for Git sources.
            upgrade: Replace an existing installation when the requested source state changes.
            force: Discard drift in a dirty managed installation before reconciliation.
            stash: Preserve a dirty managed installation before reconciliation.
            system: Use system-wide data and launcher locations instead of user locations.
        """
        result = self.gateway._install(
            source,
            ref=ref,
            upgrade=upgrade,
            force=force,
            stash=stash,
            system=system,
        )
        # Installing Gway itself can cross a reload/process boundary.  The
        # successor runtime owns its own bootstrap state, and forcing project
        # rediscovery in the predecessor can disturb reload acknowledgement and
        # rollback semantics.  Gway is an extension rather than a product scope
        # publisher, so there is no project publication to reconcile here.
        if getattr(result, "name", None) != "gway":
            self._refresh_publications()
        return result

    def _uninstall(self, project, *, system=False):
        """Converge one managed project toward absence.

        Args:
            project: Installed project identity to remove.
            system: Remove the project from the system-wide installation scope.
        """
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
