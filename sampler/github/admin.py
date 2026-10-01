"""GitHub repository-administration operations."""

from __future__ import annotations

from .admin_access import AccessAdminOperations
from .admin_actions_policy import ActionsPolicyAdminOperations
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


class AdminOperations(
    RulesetAdminOperations,
    BranchProtectionAdminOperations,
    AccessAdminOperations,
    ActionsPolicyAdminOperations,
):
    """Repository-administration surface composed from explicit domains."""
