"""GitHub repository-administration operations."""

from __future__ import annotations

from ._legacy import Controller as _LegacyController
from .admin_protection import BranchProtectionAdminOperations
from .admin_rulesets import RulesetAdminOperations


ADMIN_OPERATIONS = frozenset({
    "rulesets",
    "ruleset",
    "create_ruleset",
    "update_ruleset",
    "delete_ruleset",
    "branch_protection",
    "update_branch_protection",
    "delete_branch_protection",
    "collaborators",
    "collaborator_permission",
    "webhooks",
    "webhook",
    "actions_permissions",
    "actions_workflow_permissions",
    "set_actions_permissions",
    "set_actions_workflow_permissions",
})


class AdminOperations(RulesetAdminOperations, BranchProtectionAdminOperations):
    """Repository-administration surface composed from explicit domains."""

    collaborators = _LegacyController.collaborators
    collaborator_permission = _LegacyController.collaborator_permission
    webhooks = _LegacyController.webhooks
    webhook = _LegacyController.webhook
    actions_permissions = _LegacyController.actions_permissions
    actions_workflow_permissions = _LegacyController.actions_workflow_permissions
    set_actions_permissions = _LegacyController.set_actions_permissions
    set_actions_workflow_permissions = _LegacyController.set_actions_workflow_permissions
