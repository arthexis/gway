import pytest

from gway.githubops import Controller


class LifecycleClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append({"kind": "request", "method": method, "path": path, "json": json})
        if method == "GET":
            return type("Response", (), {"data": {"node_id": "PR_node"}})()
        return type("Response", (), {"data": {"merged": True, "sha": "merge-sha"}})()

    def graphql(self, query, variables):
        self.calls.append({"kind": "graphql", "query": query, "variables": variables})
        ready = "markPullRequestReadyForReview" in query
        field = "markPullRequestReadyForReview" if ready else "convertPullRequestToDraft"
        return type(
            "Response",
            (),
            {
                "data": {
                    "data": {
                        field: {
                            "pullRequest": {
                                "id": "PR_node",
                                "number": 51,
                                "isDraft": not ready,
                                "url": "https://example.invalid/pr/51",
                            }
                        }
                    }
                }
            },
        )()


@pytest.mark.parametrize(
    ("method", "expected_draft"),
    [("ready_pull", False), ("draft_pull", True)],
)
def test_pull_lifecycle_uses_graphql_mutation(method, expected_draft):
    client = LifecycleClient()
    target = Controller(None, client=client)

    result = getattr(target, method)("arthexis/gway", 51)

    assert result["isDraft"] is expected_draft
    assert client.calls[0]["method"] == "GET"
    assert client.calls[1]["kind"] == "graphql"
    assert client.calls[1]["variables"] == {"id": "PR_node"}


def test_pull_lifecycle_requires_node_id(github_client):
    target = Controller(None, client=github_client([{"number": 51}]))

    with pytest.raises(ValueError, match="node_id"):
        target.ready_pull("arthexis/gway", 51)


def test_merge_pull_sends_expected_head_sha(github_client):
    client = github_client([{"merged": True, "sha": "merge-sha"}])
    target = Controller(None, client=client)

    result = target.merge_pull(
        "arthexis/gway",
        51,
        "expected-head",
        method="squash",
        title="Merge feature",
    )

    assert result["merged"] is True
    assert client.calls[-1] == {
        "method": "PUT",
        "path": "/repos/arthexis/gway/pulls/51/merge",
        "params": None,
        "json": {
            "sha": "expected-head",
            "merge_method": "squash",
            "commit_title": "Merge feature",
        },
    }


@pytest.mark.parametrize("sha", ["", None])
def test_merge_pull_requires_expected_sha(github_client, sha):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(ValueError, match="head sha"):
        target.merge_pull("arthexis/gway", 51, sha)

    assert client.calls == []


def test_merge_pull_validates_method_before_http(github_client):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(ValueError, match="merge method"):
        target.merge_pull("arthexis/gway", 51, "head", method="fast")

    assert client.calls == []


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("ready_pull", ("repo/name", 1)),
        ("draft_pull", ("repo/name", 1)),
        ("merge_pull", ("repo/name", 1, "head")),
    ],
)
def test_pull_lifecycle_rejects_no_mutate_before_http(method, args):
    client = LifecycleClient()
    target = Controller(None, client=client)

    with pytest.raises(PermissionError):
        getattr(target, method)(*args, mutate=False)

    assert client.calls == []


def test_pull_lifecycle_mutations_are_source_write(gateway):
    for name in {
        "github.ready_pull",
        "github.draft_pull",
        "github.merge_pull",
    }:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "write"} <= topics
        assert "read" not in topics
