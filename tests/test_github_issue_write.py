import pytest

from gway.githubops import Controller


def test_create_issue_posts_collaboration_fields(github_client):
    client = github_client([{"number": 42, "state": "open"}])
    target = Controller(None, client=client)

    result = target.create_issue("arthexis/gway", "New issue", body="Details")

    assert result["number"] == 42
    assert client.calls[-1] == {
        "method": "POST",
        "path": "/repos/arthexis/gway/issues",
        "params": None,
        "json": {"title": "New issue", "body": "Details"},
    }


def test_update_issue_rejects_empty_or_invalid_updates(github_client):
    target = Controller(None, client=github_client())

    with pytest.raises(ValueError, match="requires"):
        target.update_issue("arthexis/gway", 42)
    with pytest.raises(ValueError, match="open or closed"):
        target.update_issue("arthexis/gway", 42, state="pending")


@pytest.mark.parametrize(
    ("method", "state"),
    [("close_issue", "closed"), ("reopen_issue", "open")],
)
def test_issue_state_helpers_use_update(github_client, method, state):
    client = github_client([{"number": 42, "state": state}])
    target = Controller(None, client=client)

    result = getattr(target, method)("arthexis/gway", 42)

    assert result["state"] == state
    assert client.calls[-1]["method"] == "PATCH"
    assert client.calls[-1]["json"] == {"state": state}


def test_comment_issue_posts_comment(github_client):
    client = github_client([{"id": 7, "body": "Done"}])
    target = Controller(None, client=client)

    result = target.comment_issue("arthexis/gway", 42, "Done")

    assert result["id"] == 7
    assert client.calls[-1]["path"].endswith("/issues/42/comments")
    assert client.calls[-1]["json"] == {"body": "Done"}


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("create_issue", ("repo/name", "Title")),
        ("update_issue", ("repo/name", 1)),
        ("close_issue", ("repo/name", 1)),
        ("reopen_issue", ("repo/name", 1)),
        ("comment_issue", ("repo/name", 1, "body")),
    ],
)
def test_issue_mutations_reject_no_mutate_before_http(
    github_client, method, args
):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises((PermissionError, ValueError)):
        getattr(target, method)(*args, mutate=False)

    assert client.calls == []


def test_issue_mutations_are_source_write(gateway):
    names = {
        "github.create_issue",
        "github.update_issue",
        "github.close_issue",
        "github.reopen_issue",
        "github.comment_issue",
    }
    for name in names:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "write"} <= topics
        assert "read" not in topics
