import pytest

from gway.githubops import Controller


def test_reply_review_comment_uses_reply_endpoint(github_client):
    client = github_client([{"id": 88, "body": "Agreed"}])
    target = Controller(None, client=client)

    result = target.reply_review_comment("arthexis/gway", 51, 77, "Agreed")

    assert result["id"] == 88
    assert client.calls[-1] == {
        "method": "POST",
        "path": "/repos/arthexis/gway/pulls/51/comments/77/replies",
        "params": None,
        "json": {"body": "Agreed"},
    }


def test_add_labels_uses_shared_issue_endpoint(github_client):
    client = github_client([[{"name": "approved"}, {"name": "release"}]])
    target = Controller(None, client=client)

    result = target.add_labels("arthexis/gway", 51, "approved", "release")

    assert [label["name"] for label in result] == ["approved", "release"]
    assert client.calls[-1] == {
        "method": "POST",
        "path": "/repos/arthexis/gway/issues/51/labels",
        "params": None,
        "json": {"labels": ["approved", "release"]},
    }


def test_add_labels_requires_at_least_one_label(github_client):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(ValueError, match="at least one label"):
        target.add_labels("arthexis/gway", 51)

    assert client.calls == []


def test_remove_label_encodes_label_name(github_client):
    client = github_client([None])
    target = Controller(None, client=client)

    target.remove_label("arthexis/gway", 51, "needs update")

    assert client.calls[-1]["method"] == "DELETE"
    assert client.calls[-1]["path"].endswith("/labels/needs%20update")


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("reply_review_comment", ("repo/name", 1, 2, "reply")),
        ("add_labels", ("repo/name", 1, "label")),
        ("remove_label", ("repo/name", 1, "label")),
    ],
)
def test_collaboration_mutations_reject_no_mutate_before_http(
    github_client, method, args
):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(PermissionError):
        getattr(target, method)(*args, mutate=False)

    assert client.calls == []


def test_collaboration_mutations_are_source_write(gateway):
    names = {
        "github.comment_issue",
        "github.reply_review_comment",
        "github.add_labels",
        "github.remove_label",
    }
    for name in names:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "write"} <= topics
        assert "read" not in topics
