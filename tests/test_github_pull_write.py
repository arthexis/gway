import pytest

from gway.githubops import Controller


def test_create_pull_posts_required_fields(github_client):
    client = github_client([{"number": 51, "state": "open", "draft": True}])
    target = Controller(None, client=client)

    result = target.create_pull(
        "arthexis/gway",
        "Feature",
        "feature/topic",
        "main",
        body="Details",
        draft=True,
    )

    assert result["number"] == 51
    assert client.calls[-1] == {
        "method": "POST",
        "path": "/repos/arthexis/gway/pulls",
        "params": None,
        "json": {
            "title": "Feature",
            "head": "feature/topic",
            "base": "main",
            "draft": True,
            "body": "Details",
        },
    }


def test_update_pull_supports_collaboration_fields(github_client):
    client = github_client([{"number": 51, "base": {"ref": "stable"}}])
    target = Controller(None, client=client)

    target.update_pull(
        "arthexis/gway", 51, title="Updated", body="", base="stable"
    )

    assert client.calls[-1]["method"] == "PATCH"
    assert client.calls[-1]["json"] == {
        "title": "Updated",
        "body": "",
        "base": "stable",
    }


def test_update_pull_rejects_empty_or_invalid_updates(github_client):
    target = Controller(None, client=github_client())

    with pytest.raises(ValueError, match="requires"):
        target.update_pull("arthexis/gway", 51)
    with pytest.raises(ValueError, match="open or closed"):
        target.update_pull("arthexis/gway", 51, state="merged")


@pytest.mark.parametrize(
    ("method", "state"),
    [("close_pull", "closed"), ("reopen_pull", "open")],
)
def test_pull_state_helpers_use_update(github_client, method, state):
    client = github_client([{"number": 51, "state": state}])
    target = Controller(None, client=client)

    result = getattr(target, method)("arthexis/gway", 51)

    assert result["state"] == state
    assert client.calls[-1]["method"] == "PATCH"
    assert client.calls[-1]["json"] == {"state": state}


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("create_pull", ("repo/name", "Title", "head", "main")),
        ("update_pull", ("repo/name", 1)),
        ("close_pull", ("repo/name", 1)),
        ("reopen_pull", ("repo/name", 1)),
    ],
)
def test_pull_mutations_reject_no_mutate_before_http(github_client, method, args):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises((PermissionError, ValueError)):
        getattr(target, method)(*args, mutate=False)

    assert client.calls == []


def test_pull_mutations_are_source_write(gateway):
    names = {
        "github.create_pull",
        "github.update_pull",
        "github.close_pull",
        "github.reopen_pull",
    }
    for name in names:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "write"} <= topics
        assert "read" not in topics
