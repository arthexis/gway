import pytest

from gway.githubops import Controller


def test_create_release_posts_release_fields(github_client):
    client = github_client([{"id": 7, "tag_name": "v1.2.3", "draft": True}])
    target = Controller(None, client=client)

    result = target.create_release(
        "arthexis/gway",
        "v1.2.3",
        target="main",
        name="Gway 1.2.3",
        body="Notes",
        draft=True,
    )

    assert result["id"] == 7
    assert client.calls[-1] == {
        "method": "POST",
        "path": "/repos/arthexis/gway/releases",
        "params": None,
        "json": {
            "tag_name": "v1.2.3",
            "draft": True,
            "prerelease": False,
            "target_commitish": "main",
            "name": "Gway 1.2.3",
            "body": "Notes",
        },
    }


def test_create_release_requires_tag_before_http(github_client):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(ValueError, match="tag"):
        target.create_release("repo/name", "")

    assert client.calls == []


def test_update_release_targets_explicit_id(github_client):
    client = github_client([{"id": 7, "draft": False, "prerelease": True}])
    target = Controller(None, client=client)

    result = target.update_release(
        "arthexis/gway",
        7,
        body="Updated notes",
        draft=False,
        prerelease=True,
    )

    assert result["id"] == 7
    assert client.calls[-1] == {
        "method": "PATCH",
        "path": "/repos/arthexis/gway/releases/7",
        "params": None,
        "json": {
            "body": "Updated notes",
            "draft": False,
            "prerelease": True,
        },
    }


def test_update_release_requires_a_field(github_client):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(ValueError, match="at least one field"):
        target.update_release("repo/name", 7)

    assert client.calls == []


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("create_release", ("repo/name", "v1")),
        ("update_release", ("repo/name", 7)),
    ],
)
def test_release_mutations_reject_no_mutate_before_http(
    github_client, method, args
):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(PermissionError):
        getattr(target, method)(*args, mutate=False)

    assert client.calls == []


def test_release_mutations_are_source_write(gateway):
    for name in {"github.create_release", "github.update_release"}:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "write"} <= topics
        assert "read" not in topics
