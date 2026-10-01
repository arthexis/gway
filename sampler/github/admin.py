"""GitHub repository-administration operations.

The policy validators remain behavior-identical to the pre-split controller for
this refactor. Only these administration methods are retained from the staged
legacy implementation; ordinary repository, collaboration, Actions, and release
operations live in their domain modules.
"""

from __future__ import annotations

from ._legacy import Controller as _LegacyController


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


class AdminOperations:
    """Administration-only slice of the former GitHub controller."""

    rulesets = _LegacyController.rulesets
    ruleset = _LegacyController.ruleset
    _ruleset_policy = staticmethod(_LegacyController._ruleset_policy)
    create_ruleset = _LegacyController.create_ruleset
    update_ruleset = _LegacyController.update_ruleset
    delete_ruleset = _LegacyController.delete_ruleset
    branch_protection = _LegacyController.branch_protection
    _branch_protection_policy = staticmethod(_LegacyController._branch_protection_policy)
    update_branch_protection = _LegacyController.update_branch_protection
    delete_branch_protection = _LegacyController.delete_branch_protection
    collaborators = _LegacyController.collaborators
    collaborator_permission = _LegacyController.collaborator_permission
    webhooks = _LegacyController.webhooks
    webhook = _LegacyController.webhook
    actions_permissions = _LegacyController.actions_permissions
    actions_workflow_permissions = _LegacyController.actions_workflow_permissions
    set_actions_permissions = _LegacyController.set_actions_permissions
    set_actions_workflow_permissions = _LegacyController.set_actions_workflow_permissions
