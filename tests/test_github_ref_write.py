import pytest

from gway.githubops import Controller


def test_create_ref_uses_explicit_sha(github_client):
    client = github_client([{"ref": "refs/tags/test", "object": {"sha": "abc123"}}])
    target = Controller(None, client=client)

    result = target.create_ref("arthexis/gway", "tags/test", "abc123")

    assert result["ref"] == "refs/tags/test"
    assert client.calls[-1] == {
        "method": "POST",
        "path": "/repos/arthexis/gway/git/refs",
        "params": None,
        "json": {"ref": "refs/tags/test", "sha": "abc123"},
    }


def test_create_branch_is_heads_ref_convenience(github_client):
    client = github_client([{"ref": "refs/heads/feature/test"}])
    target = Controller(None, client=client)

    target.create_branch("repo/name", "feature/test", "abc123")

    assert client.calls[-1]["json"] == {
        "ref": "refs/heads/feature/test",
        "sha": "abc123",
    }


@pytest.mark.parametrize(
    ("ref", "sha", "message"),
    [
        ("", "abc123", "reference"),
        ("heads/main", "", "SHA"),
    ],
)
def test_create_ref_validates_identity_before_http(
    github_client, ref, sha, message
):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(ValueError, match=message):
        target.create_ref("repo/name", ref, sha)

    assert client.calls == []


def test_delete_ref_encodes_ref_and_returns_acknowledgement(github_client):
    client = github_client([None])
    target = Controller(None, client=client)

    result = target.delete_ref("arthexis/gway", "refs/heads/feature/test")

    assert result == {
        "repository": "arthexis/gway",
        "ref": "refs/heads/feature/test",
        "deleted": True,
    }
    assert client.calls[-1]["method"] == "DELETE"
    assert client.calls[-1]["path"] == (
        "/repos/arthexis/gway/git/refs/heads/feature/test"
    )


def test_delete_branch_is_heads_ref_convenience(github_client):
    client = github_client([None])
    target = Controller(None, client=client)

    result = target.delete_branch("repo/name", "feature/test")

    assert result["ref"] == "refs/heads/feature/test"
    assert client.calls[-1]["path"].endswith(
        "/git/refs/heads/feature/test"
    )


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("create_ref", ("repo/name", "tags/test", "abc123")),
        ("create_branch", ("repo/name", "feature/test", "abc123")),
        ("delete_ref", ("repo/name", "tags/test")),
        ("delete_branch", ("repo/name", "feature/test")),
    ],
)
def test_ref_mutations_reject_no_mutate_before_http(
    github_client, method, args
):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(PermissionError):
        getattr(target, method)(*args, mutate=False)

    assert client.calls == []


def test_ref_mutations_are_source_write(gateway):
    names = {
        "github.create_ref",
        "github.create_branch",
        "github.delete_ref",
        "github.delete_branch",
    }
    for name in names:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "write"} <= topics
        assert "read" not in topics
