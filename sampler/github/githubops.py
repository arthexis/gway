"""Composite GitHub operation surface assembled from domain modules."""

from __future__ import annotations

from .actions import ActionsOperations
from .admin import ADMIN_OPERATIONS, AdminOperations
from .base import BaseOperations, segment
from .issues import IssueOperations
from .pulls import PullOperations
from .releases import ReleaseOperations
from .repository import RepositoryOperations
from .reviews import ReviewOperations


_segment = segment


WRITE_OPERATIONS = frozenset({
    "drive",
    "create_ruleset",
    "update_ruleset",
    "delete_ruleset",
    "update_branch_protection",
    "delete_branch_protection",
    "set_actions_permissions",
    "set_actions_workflow_permissions",
    "set_variable",
    "delete_variable",
    "set_secret",
    "delete_secret",
    "create_issue",
    "update_issue",
    "close_issue",
    "reopen_issue",
    "comment_issue",
    "create_pull",
    "update_pull",
    "close_pull",
    "reopen_pull",
    "reply_review_comment",
    "add_labels",
    "remove_label",
    "ready_pull",
    "draft_pull",
    "merge_pull",
    "dispatch_workflow",
    "dispatch_repository",
    "create_release",
    "update_release",
    "create_ref",
    "create_branch",
    "delete_ref",
    "delete_branch",
    "create_file",
    "update_file",
    "delete_file",
})


class Controller(
    AdminOperations,
    RepositoryOperations,
    PullOperations,
    IssueOperations,
    ReviewOperations,
    ActionsOperations,
    ReleaseOperations,
    BaseOperations,
):
    """GitHub capability composed from domain-specific operation mixins."""


__all__ = ["ADMIN_OPERATIONS", "Controller", "WRITE_OPERATIONS"]
