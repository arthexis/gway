import base64

import pytest

from gway.githubops import Controller


def test_create_file_encodes_content_and_branch(github_client):
    client = github_client([{"content": {"sha": "new-sha"}}])
    target = Controller(None, client=client)

    result = target.create_file(
        "arthexis/gway",
        "docs/new file.md",
        "hello",
        "Add documentation",
        branch="feature/docs",
    )

    assert result["content"]["sha"] == "new-sha"
    assert client.calls[-1] == {
        "method": "PUT",
        "path": "/repos/arthexis/gway/contents/docs/new%20file.md",
        "params": None,
        "json": {
            "message": "Add documentation",
            "content": base64.b64encode(b"hello").decode(),
            "branch": "feature/docs",
        },
    }


def test_create_file_accepts_bytes(github_client):
    client = github_client([{}])
    target = Controller(None, client=client)

    target.create_file("repo/name", "data.bin", b"\x00\xff", "Add data")

    assert client.calls[-1]["json"]["content"] == base64.b64encode(
        b"\x00\xff"
    ).decode()


def test_update_file_requires_expected_sha(github_client):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(ValueError, match="SHA"):
        target.update_file("repo/name", "README.md", "new", "Update", "")

    assert client.calls == []


def test_update_file_sends_expected_sha(github_client):
    client = github_client([{"content": {"sha": "next-sha"}}])
    target = Controller(None, client=client)

    target.update_file(
        "repo/name",
        "README.md",
        "new",
        "Update README",
        "expected-sha",
        branch="main",
    )

    assert client.calls[-1]["json"] == {
        "message": "Update README",
        "content": base64.b64encode(b"new").decode(),
        "sha": "expected-sha",
        "branch": "main",
    }


def test_delete_file_requires_expected_sha_and_sends_branch(github_client):
    client = github_client([{"commit": {"sha": "commit-sha"}}])
    target = Controller(None, client=client)

    target.delete_file(
        "repo/name",
        "old.txt",
        "Remove old file",
        "expected-sha",
        branch="cleanup",
    )

    assert client.calls[-1] == {
        "method": "DELETE",
        "path": "/repos/repo/name/contents/old.txt",
        "params": None,
        "json": {
            "message": "Remove old file",
            "sha": "expected-sha",
            "branch": "cleanup",
        },
    }


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("create_file", ("repo/name", "a.txt", "a", "Create")),
        ("update_file", ("repo/name", "a.txt", "b", "Update", "sha")),
        ("delete_file", ("repo/name", "a.txt", "Delete", "sha")),
    ],
)
def test_file_mutations_reject_no_mutate_before_http(
    github_client, method, args
):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(PermissionError):
        getattr(target, method)(*args, mutate=False)

    assert client.calls == []


@pytest.mark.parametrize("method", ["create_file", "update_file", "delete_file"])
def test_file_mutations_require_path_and_message(github_client, method):
    client = github_client()
    target = Controller(None, client=client)
    if method == "create_file":
        args = ("repo/name", "", "content", "message")
        message_args = ("repo/name", "a.txt", "content", "")
    elif method == "update_file":
        args = ("repo/name", "", "content", "message", "sha")
        message_args = ("repo/name", "a.txt", "content", "", "sha")
    else:
        args = ("repo/name", "", "message", "sha")
        message_args = ("repo/name", "a.txt", "", "sha")

    with pytest.raises(ValueError, match="path"):
        getattr(target, method)(*args)
    with pytest.raises(ValueError, match="message"):
        getattr(target, method)(*message_args)

    assert client.calls == []


def test_file_mutations_are_source_write(gateway):
    for name in {"github.create_file", "github.update_file", "github.delete_file"}:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "write"} <= topics
        assert "read" not in topics
