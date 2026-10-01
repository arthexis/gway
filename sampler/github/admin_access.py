"""Read-only GitHub repository administration access inspection."""

from __future__ import annotations

from .base import BaseOperations, segment


class AccessAdminOperations(BaseOperations):
    """Collaborator permission and webhook metadata operations."""

    def collaborators(self, repository, affiliation=None, permission=None):
        """List repository collaborators and visible permission metadata."""
        params = {"per_page": 100}
        if affiliation is not None:
            params["affiliation"] = str(affiliation)
        if permission is not None:
            params["permission"] = str(permission)
        return self._all(
            f"{self._repo(repository)}/collaborators",
            params=params,
        )

    def collaborator_permission(self, repository, username):
        """Return one collaborator's effective repository permission."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/collaborators/{segment(username)}/permission",
        ).data

    def webhooks(self, repository):
        """List repository webhook metadata without exposing hook secrets."""
        return self._all(
            f"{self._repo(repository)}/hooks",
            params={"per_page": 100},
        )

    def webhook(self, repository, hook):
        """Return one repository webhook's metadata."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/hooks/{int(hook)}",
        ).data
