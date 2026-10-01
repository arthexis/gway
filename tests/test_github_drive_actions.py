from types import SimpleNamespace

import pytest

from sampler.github.drive import Controller as DriveController
from tests.github_support import REPOSITORY, pull_request


class ActionClient:
    def __init__(self):
        self.requests = []
        self.graphql_calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.requests.append((method, path, json))
        return SimpleNamespace(data={"message": "branch update scheduled"})

    def graphql(self, query, variables=None):
        variables = dict(variables or {})
        self.graphql_calls.append((query, variables))
        if "disablePullRequestAutoMerge" in query:
            data = {
                "disablePullRequestAutoMerge": {
                    "pullRequest": {
                        "id": "PR_node",
                        "number": 10,
                        "autoMergeRequest": None,
                    }
                }
            }
        else:
            data = {
                "enablePullRequestAutoMerge": {
                    "pullRequest": {
                        "id": "PR_node",
                        "number": 10,
                        "autoMergeRequest": {
                            "enabledAt": "2026-10-01T00:00:00Z",
                            "mergeMethod": variables.get("method"),
                        },
                    }
                }
            }
        return SimpleNamespace(data={"data": data})


class ActionController(DriveController):
    def __init__(self, pr=None, repo=None):
        self.client = ActionClient()
        super().__init__(None, client=self.client)
        self.pr_data = pr or pull_request(node_id="PR_node")
        self.repo_data = repo or {
            "allow_squash_merge": True,
            "allow_merge_commit": True,
            "allow_rebase_merge": True,
        }
        self.merge_calls = []

    def pull(self, repository, number):
        return dict(self.pr_data)

    def repository(self, repository):
        return dict(self.repo_data)

    def merge_pull(
        self, repository, number, sha, method=None, title=None, message=None,
        mutate=True,
    ):
        self.merge_calls.append((repository, number, sha, method, mutate))
        return {"merged": True, "sha": "merge-sha"}


def test_update_branch_uses_expected_head_compare_and_swap():
    controller = ActionController()

    result = controller._execute_drive_action(
        REPOSITORY,
        10,
        {"kind": "update-branch", "expected_head_sha": "head"},
    )

    assert result["result"] == "changed"
    assert controller.client.requests == [
        (
            "PUT",
            "/repos/arthexis/gway/pulls/10/update-branch",
            {"expected_head_sha": "head"},
        )
    ]


def test_stale_head_declines_mutation_and_reports_current_head():
    controller = ActionController(pr=pull_request(head={"ref": "feature", "sha": "new-head"}))

    result = controller._execute_drive_action(
        REPOSITORY,
        10,
        {"kind": "update-branch", "expected_head_sha": "old-head"},
    )

    assert result == {
        "kind": "update-branch",
        "result": "stale",
        "expected_head_sha": "old-head",
        "actual_head_sha": "new-head",
    }
    assert controller.client.requests == []


def test_ensure_auto_merge_is_convergent_when_already_enabled():
    controller = ActionController(
        pr=pull_request(
            node_id="PR_node",
            auto_merge={"merge_method": "SQUASH"},
        )
    )

    result = controller._execute_drive_action(
        REPOSITORY,
        10,
        {"kind": "enable-auto-merge", "expected_head_sha": "head"},
    )

    assert result["kind"] == "ensure-auto-merge"
    assert result["result"] == "already"
    assert controller.client.graphql_calls == []


def test_ensure_auto_merge_enables_native_state_with_repository_method():
    controller = ActionController()

    result = controller._execute_drive_action(
        REPOSITORY,
        10,
        {"kind": "enable-auto-merge", "expected_head_sha": "head"},
    )

    assert result["result"] == "changed"
    assert result["merge_method"] == "squash"
    assert controller.client.graphql_calls[0][1] == {
        "id": "PR_node",
        "method": "SQUASH",
    }


def test_ensure_auto_merge_disabled_is_convergent_when_already_disabled():
    controller = ActionController(pr=pull_request(node_id="PR_node", auto_merge=None))

    result = controller._execute_drive_action(
        REPOSITORY,
        10,
        {"kind": "ensure-auto-merge-disabled", "expected_head_sha": "head"},
    )

    assert result["kind"] == "ensure-auto-merge-disabled"
    assert result["result"] == "already"
    assert controller.client.graphql_calls == []


def test_ensure_auto_merge_disabled_disarms_native_authorization():
    controller = ActionController(
        pr=pull_request(
            node_id="PR_node",
            auto_merge={"merge_method": "SQUASH"},
        )
    )

    result = controller._execute_drive_action(
        REPOSITORY,
        10,
        {"kind": "ensure-auto-merge-disabled", "expected_head_sha": "head"},
    )

    assert result["result"] == "changed"
    query, variables = controller.client.graphql_calls[0]
    assert "disablePullRequestAutoMerge" in query
    assert variables == {"id": "PR_node"}


def test_guarded_merge_forwards_expected_head_to_merge_primitive():
    controller = ActionController()

    result = controller._execute_drive_action(
        REPOSITORY,
        10,
        {"kind": "merge-pull", "expected_head_sha": "head"},
    )

    assert result["result"] == "changed"
    assert controller.merge_calls == [(REPOSITORY, 10, "head", None, True)]


def test_drive_action_respects_no_mutate_before_provider_write():
    controller = ActionController()

    with pytest.raises(PermissionError, match="Drive mutation is disabled"):
        controller._execute_drive_action(
            REPOSITORY,
            10,
            {"kind": "update-branch", "expected_head_sha": "head"},
            mutate=False,
        )

    assert controller.client.requests == []
    assert controller.client.graphql_calls == []
    assert controller.merge_calls == []


def test_guarded_actions_require_expected_head_sha():
    controller = ActionController()

    with pytest.raises(ValueError, match="expected_head_sha"):
        controller._execute_drive_action(
            REPOSITORY,
            10,
            {"kind": "merge-pull"},
        )
