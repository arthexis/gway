import pytest

from gway.githubops import Controller


def test_dispatch_workflow_posts_ref_and_inputs(github_client):
    client = github_client([None])
    target = Controller(None, client=client)

    result = target.dispatch_workflow(
        "arthexis/gway",
        "deploy.yml",
        "main",
        inputs={"remote": "true"},
    )

    assert result == {
        "repository": "arthexis/gway",
        "workflow": "deploy.yml",
        "ref": "main",
        "dispatched": True,
    }
    assert client.calls[-1] == {
        "method": "POST",
        "path": "/repos/arthexis/gway/actions/workflows/deploy.yml/dispatches",
        "params": None,
        "json": {"ref": "main", "inputs": {"remote": "true"}},
    }


def test_dispatch_workflow_requires_mapping_inputs(github_client):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(TypeError, match="mapping"):
        target.dispatch_workflow("repo/name", "ci.yml", "main", inputs=["bad"])

    assert client.calls == []


def test_dispatch_repository_posts_event_and_payload(github_client):
    client = github_client([None])
    target = Controller(None, client=client)

    result = target.dispatch_repository(
        "arthexis/gway",
        "refresh",
        payload={"target": "watchtower"},
    )

    assert result == {
        "repository": "arthexis/gway",
        "event": "refresh",
        "dispatched": True,
    }
    assert client.calls[-1] == {
        "method": "POST",
        "path": "/repos/arthexis/gway/dispatches",
        "params": None,
        "json": {
            "event_type": "refresh",
            "client_payload": {"target": "watchtower"},
        },
    }


def test_dispatch_repository_validates_event_and_payload(github_client):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(ValueError, match="event"):
        target.dispatch_repository("repo/name", "")
    with pytest.raises(TypeError, match="mapping"):
        target.dispatch_repository("repo/name", "refresh", payload="bad")

    assert client.calls == []


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("dispatch_workflow", ("repo/name", "ci.yml", "main")),
        ("dispatch_repository", ("repo/name", "refresh")),
    ],
)
def test_dispatch_rejects_no_mutate_before_http(github_client, method, args):
    client = github_client()
    target = Controller(None, client=client)

    with pytest.raises(PermissionError):
        getattr(target, method)(*args, mutate=False)

    assert client.calls == []


def test_dispatch_operations_are_source_write(gateway):
    for name in {"github.dispatch_workflow", "github.dispatch_repository"}:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "write"} <= topics
        assert "read" not in topics
