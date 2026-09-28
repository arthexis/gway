from types import SimpleNamespace

import pytest

from gway.authorization import AuthorizationError
from gway.github import GitHubError
from gway.githubops import Controller


WRITE_OPERATIONS = {
    "github.create_issue",
    "github.update_issue",
    "github.close_issue",
    "github.reopen_issue",
    "github.comment_issue",
    "github.create_pull",
    "github.update_pull",
    "github.close_pull",
    "github.reopen_pull",
    "github.reply_review_comment",
    "github.add_labels",
    "github.remove_label",
    "github.ready_pull",
    "github.draft_pull",
    "github.merge_pull",
}


class CollaborationClient:
    def __init__(self):
        self.issue = None
        self.pull = None
        self.comments = []
        self.labels = set()
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, json))
        if path.endswith("/issues") and method == "POST":
            self.issue = {"number": 1, "title": json["title"], "state": "open"}
            return SimpleNamespace(data=dict(self.issue))
        if path.endswith("/issues/1/comments") and method == "POST":
            self.comments.append(json["body"])
            return SimpleNamespace(data={"id": len(self.comments), "body": json["body"]})
        if path.endswith("/issues/1/labels") and method == "POST":
            self.labels.update(json["labels"])
            return SimpleNamespace(data=[{"name": name} for name in sorted(self.labels)])
        if path.endswith("/issues/1") and method == "PATCH":
            self.issue.update(json)
            return SimpleNamespace(data=dict(self.issue))
        if path.endswith("/pulls") and method == "POST":
            self.pull = {
                "number": 2,
                "node_id": "PR_node",
                "head": {"sha": "expected-head"},
                "draft": json["draft"],
                "state": "open",
            }
            return SimpleNamespace(data=dict(self.pull))
        if path.endswith("/pulls/2") and method == "GET":
            return SimpleNamespace(data=dict(self.pull))
        if path.endswith("/pulls/2/merge") and method == "PUT":
            if json["sha"] != self.pull["head"]["sha"]:
                raise GitHubError(409, "Head branch was modified")
            self.pull["state"] = "closed"
            return SimpleNamespace(data={"merged": True, "sha": "merge-sha"})
        raise AssertionError((method, path, json))

    def graphql(self, query, variables):
        self.calls.append(("GRAPHQL", query, variables))
        assert variables == {"id": "PR_node"}
        ready = "markPullRequestReadyForReview" in query
        self.pull["draft"] = not ready
        field = (
            "markPullRequestReadyForReview"
            if ready
            else "convertPullRequestToDraft"
        )
        return SimpleNamespace(
            data={
                "data": {
                    field: {
                        "pullRequest": {
                            "id": "PR_node",
                            "number": 2,
                            "isDraft": self.pull["draft"],
                        }
                    }
                }
            }
        )


@pytest.mark.parametrize("operation", sorted(WRITE_OPERATIONS))
def test_read_authority_rejects_collaboration_writes(gateway, operation):
    with gateway.authorized(operations={"github.pull", "github.issue"}):
        with pytest.raises(AuthorizationError, match=operation):
            gateway.authorization.authorize_operation(operation)


def test_collaboration_lifecycle_rehearsal():
    client = CollaborationClient()
    target = Controller(None, client=client)

    issue = target.create_issue("repo/name", "Investigate")
    target.comment_issue("repo/name", issue["number"], "Reproduced")
    target.add_labels("repo/name", issue["number"], "bug", "ready")
    closed = target.close_issue("repo/name", issue["number"])

    pull = target.create_pull(
        "repo/name", "Fix", "feature/fix", "main", draft=True
    )
    ready = target.ready_pull("repo/name", pull["number"])
    merged = target.merge_pull(
        "repo/name", pull["number"], pull["head"]["sha"], method="squash"
    )

    assert closed["state"] == "closed"
    assert client.comments == ["Reproduced"]
    assert client.labels == {"bug", "ready"}
    assert ready["isDraft"] is False
    assert merged["merged"] is True


def test_merge_rehearsal_rejects_stale_head():
    client = CollaborationClient()
    target = Controller(None, client=client)
    pull = target.create_pull("repo/name", "Fix", "feature/fix", "main")
    client.pull["head"]["sha"] = "changed-head"

    with pytest.raises(GitHubError) as caught:
        target.merge_pull("repo/name", pull["number"], "expected-head")

    assert caught.value.status == 409
    assert "Head branch was modified" in str(caught.value)


@pytest.mark.parametrize("status", [401, 403, 404, 409, 422])
def test_collaboration_github_errors_remain_actionable(github_client, status):
    error = GitHubError(status, "collaboration failed", request_id="request-1")
    target = Controller(None, client=github_client([error]))

    with pytest.raises(GitHubError) as caught:
        target.create_issue("repo/name", "Title")

    assert caught.value.status == status
    assert "collaboration failed" in str(caught.value)
    assert "request-1" in str(caught.value)
