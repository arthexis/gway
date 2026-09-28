import pytest

from gway.github import GitHubError
from gway.githubops import Controller


def test_set_variable_creates_when_missing(github_client):
    client = github_client([GitHubError(404, "Not Found"), None])
    target = Controller(None, client=client)

    result = target.set_variable("arthexis/gway", "DEPLOY_ENV", "production")

    assert result == {
        "name": "DEPLOY_ENV",
        "value": "production",
        "created": True,
    }
    assert client.calls[-1] == {
        "method": "POST",
        "path": "/repos/arthexis/gway/actions/variables",
        "params": None,
        "json": {"name": "DEPLOY_ENV", "value": "production"},
    }


def test_set_variable_updates_when_present(github_client):
    client = github_client([None, None])
    target = Controller(None, client=client)

    result = target.set_variable("arthexis/gway", "DEPLOY_ENV", "staging")

    assert result["created"] is False
    assert client.calls[-1] == {
        "method": "PATCH",
        "path": "/repos/arthexis/gway/actions/variables/DEPLOY_ENV",
        "params": None,
        "json": {"name": "DEPLOY_ENV", "value": "staging"},
    }


def test_delete_variable_uses_delete(github_client):
    client = github_client()
    target = Controller(None, client=client)

    assert target.delete_variable("arthexis/gway", "DEPLOY_ENV") == {
        "name": "DEPLOY_ENV",
        "deleted": True,
    }
    assert client.calls[-1]["method"] == "DELETE"
    assert client.calls[-1]["path"].endswith("/actions/variables/DEPLOY_ENV")


def test_variable_mutations_are_source_write(gateway):
    for name in {"github.set_variable", "github.delete_variable"}:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "write"} <= topics
        assert "read" not in topics
