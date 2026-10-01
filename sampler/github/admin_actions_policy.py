"""Repository-level GitHub Actions administration policy."""

from __future__ import annotations

from .base import BaseOperations


class ActionsPolicyAdminOperations(BaseOperations):
    """Repository Actions enablement and workflow-token policy operations."""

    def actions_permissions(self, repository):
        """Return repository-level GitHub Actions policy."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/actions/permissions",
        ).data

    def actions_workflow_permissions(self, repository):
        """Return default workflow-token and PR approval permissions."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/actions/permissions/workflow",
        ).data

    def set_actions_permissions(
        self,
        repository,
        enabled: bool,
        allowed_actions,
        sha_pinning_required: bool,
        mutate=True,
    ):
        """Replace repository GitHub Actions enablement and allow policy."""
        if not mutate:
            raise PermissionError("GitHub Actions policy mutation is disabled")
        if not isinstance(enabled, bool):
            raise TypeError("GitHub Actions enabled must be boolean")
        allowed_actions = str(allowed_actions)
        if allowed_actions not in {"all", "local_only", "selected"}:
            raise ValueError(
                "GitHub Actions allowed_actions must be all, local_only, or selected"
            )
        if not isinstance(sha_pinning_required, bool):
            raise TypeError("GitHub Actions sha_pinning_required must be boolean")
        self._github().request(
            "PUT",
            f"{self._repo(repository)}/actions/permissions",
            json={
                "enabled": enabled,
                "allowed_actions": allowed_actions,
                "sha_pinning_required": sha_pinning_required,
            },
        )
        return {
            "repository": str(repository),
            "enabled": enabled,
            "allowed_actions": allowed_actions,
            "sha_pinning_required": sha_pinning_required,
            "updated": True,
        }

    def set_actions_workflow_permissions(
        self,
        repository,
        default_workflow_permissions,
        can_approve_pull_request_reviews: bool,
        mutate=True,
    ):
        """Replace repository default GITHUB_TOKEN and PR approval policy."""
        if not mutate:
            raise PermissionError(
                "GitHub Actions workflow permission mutation is disabled"
            )
        default_workflow_permissions = str(default_workflow_permissions)
        if default_workflow_permissions not in {"read", "write"}:
            raise ValueError("default_workflow_permissions must be read or write")
        if not isinstance(can_approve_pull_request_reviews, bool):
            raise TypeError("can_approve_pull_request_reviews must be boolean")
        self._github().request(
            "PUT",
            f"{self._repo(repository)}/actions/permissions/workflow",
            json={
                "default_workflow_permissions": default_workflow_permissions,
                "can_approve_pull_request_reviews": can_approve_pull_request_reviews,
            },
        )
        return {
            "repository": str(repository),
            "default_workflow_permissions": default_workflow_permissions,
            "can_approve_pull_request_reviews": can_approve_pull_request_reviews,
            "updated": True,
        }
